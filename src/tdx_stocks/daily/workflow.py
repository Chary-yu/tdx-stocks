from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime
from time import perf_counter
from typing import Any

from .. import __version__ as APP_VERSION
from ..config import AppConfig
from ..pipeline import build_dataset
from ..portfolio import (
    build_portfolio,
    build_rebalance_plan,
    check_portfolio_risk,
    load_current_holdings_csv,
    save_portfolio_report,
    save_rebalance_plan,
)
from ..config_validators import optional_str
from ..query import open_query_context
from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
from ..strategies.registry import get_strategy
from ..strategies.storage import build_report_document, save_report_document
from .config import DailyRunConfig
from .diagnostics import collect_warnings_errors
from .models import DailyRunReport, DailyStepResult
from ..reports.renderers import render_daily_markdown
from ..reports.stock_names import build_stock_name_map, collect_stock_keys
from ..progress import ProgressCallback, emit_progress
from .store import save_daily_report, write_daily_json_file


@dataclass(frozen=True)
class DailyWorkflowResult:
    report: DailyRunReport
    markdown: str
    outputs: dict[str, str]


def run_daily_workflow(
    config: AppConfig,
    *,
    as_of: date | None = None,
    strategies: list[str] | None = None,
    strategy_limit: int | None = None,
    min_score: float | None = None,
    min_hit: int | None = None,
    portfolio_top: int | None = None,
    portfolio_weighting: str | None = None,
    portfolio_max_weight: float | None = None,
    current_holdings: str | None = None,
    skip_strategies: bool = False,
    skip_portfolio: bool = False,
    skip_rebalance: bool = False,
    skip_report: bool = False,
    build_data: bool = False,
    progress: ProgressCallback | None = None,
) -> DailyWorkflowResult:
    emit_progress(progress, "准备每日综合报告参数")
    run_started = datetime.now()
    resolved_as_of = as_of or _load_latest_trade_date(config)
    daily_config = DailyRunConfig.from_app_config(config)
    strategy_names = strategies or list(daily_config.enabled_strategies)
    strategy_limit = daily_config.strategy_limit if strategy_limit is None else strategy_limit
    min_score = min_score if min_score is not None else daily_config.strategy_min_score
    min_hit = daily_config.consensus_min_hit if min_hit is None else min_hit
    portfolio_top = daily_config.portfolio_top if portfolio_top is None else portfolio_top
    portfolio_weighting = daily_config.portfolio_weighting if portfolio_weighting is None else portfolio_weighting
    portfolio_max_weight = (
        portfolio_max_weight if portfolio_max_weight is not None else daily_config.portfolio_max_weight
    )

    outputs: dict[str, str] = {}
    steps: list[DailyStepResult] = []
    warnings: list[str] = []
    errors: list[str] = []

    if skip_strategies and not skip_portfolio:
        skip_portfolio = True
        warnings.append("portfolio skipped because strategies were skipped")

    if build_data:
        build_result = build_dataset(config)
        steps.append(
            DailyStepResult(
                step_name="load_data",
                status="success",
                message="dataset rebuilt",
                output_paths=[],
                metrics={"run_id": build_result.get("run_id")},
                duration_seconds=0.0,
            )
        )

    emit_progress(progress, "打开本地数据集")
    ctx = open_query_context(config)
    try:
        manifest = ctx.manifest
        data_run_id = optional_str(manifest.get("run_id"))
        latest_trade_date = resolved_as_of or _load_latest_trade_date(config)
        data_quality = manifest.get("summary", {}).get("checks", [])
        if not skip_strategies:
            emit_progress(progress, "运行策略并保存策略报告")
            strategy_payloads, strategy_outputs = _run_strategies(
                config,
                strategy_names,
                latest_trade_date,
                strategy_limit=strategy_limit,
                min_score=min_score,
            )
            outputs.update(strategy_outputs)
            steps.extend(strategy_payloads["steps"])
            warnings.extend(strategy_payloads["warnings"])
            errors.extend(strategy_payloads["errors"])
            emit_progress(progress, "生成策略对比")
            compare_payload = _run_compare(config, strategy_names, latest_trade_date)
            emit_progress(progress, "生成共振股票")
            consensus_payload = _run_consensus(config, strategy_names, latest_trade_date, min_hit=min_hit)
            compare_path = write_daily_json_file(config.paths.data_root, latest_trade_date, "compare.json", compare_payload)
            consensus_path = write_daily_json_file(config.paths.data_root, latest_trade_date, "consensus.json", consensus_payload)
            outputs["compare_json"] = compare_path.as_posix()
            outputs["consensus_json"] = consensus_path.as_posix()
            steps.append(
                DailyStepResult(
                    step_name="strategy_compare",
                    status="success",
                    message="compare generated",
                    output_paths=[compare_path.as_posix()],
                    metrics={"strategy_count": len(strategy_names)},
                    duration_seconds=0.0,
                )
            )
            steps.append(
                DailyStepResult(
                    step_name="strategy_consensus",
                    status="success",
                    message="consensus generated",
                    output_paths=[consensus_path.as_posix()],
                    metrics={"min_hit": min_hit, "row_count": len(consensus_payload.get("rows") or [])},
                    duration_seconds=0.0,
                )
            )
        else:
            compare_payload = {"rows": [], "summary": "skipped"}
            consensus_payload = {"rows": [], "summary": "skipped"}
            steps.append(
                DailyStepResult(
                    step_name="strategy_compare",
                    status="skipped",
                    message="strategies skipped",
                    output_paths=[],
                    metrics={},
                    duration_seconds=0.0,
                )
            )
            steps.append(
                DailyStepResult(
                    step_name="strategy_consensus",
                    status="skipped",
                    message="strategies skipped",
                    output_paths=[],
                    metrics={},
                    duration_seconds=0.0,
                )
            )

        portfolio_payload = {"summary": "skipped", "holdings": [], "risk_summary": {}}
        rebalance_payload = {"summary": "skipped"}
        if not skip_portfolio:
            emit_progress(progress, "构建目标组合")
            portfolio_report = build_portfolio(
                config,
                source="consensus",
                top=portfolio_top,
                weighting=portfolio_weighting,
                max_weight=portfolio_max_weight,
                as_of=latest_trade_date,
                exclude_risk_tags=tuple(daily_config.exclude_risk_tags),
            )
            portfolio_saved = save_portfolio_report(config.paths.data_root, portfolio_report)
            if isinstance(portfolio_saved, dict):
                portfolio_outputs = {f"portfolio:{key}": str(value) for key, value in portfolio_saved.items()}
            else:
                portfolio_outputs = {"portfolio:portfolio_json": portfolio_saved.as_posix()}
            portfolio_payload = portfolio_report.to_dict()
            outputs.update(portfolio_outputs)
            steps.append(
                DailyStepResult(
                    step_name="portfolio_build",
                    status="success",
                    message="portfolio built",
                    output_paths=list(portfolio_outputs.values()),
                    metrics={"holding_count": len(portfolio_report.holdings)},
                    duration_seconds=0.0,
                )
            )
            risk_result = check_portfolio_risk([_holding_from_dict(row) for row in portfolio_report.holdings])
            steps.append(
                DailyStepResult(
                    step_name="portfolio_risk",
                    status="success" if risk_result.passed else "warning",
                    message="portfolio risk checked",
                    output_paths=[],
                    metrics=risk_result.summary,
                    duration_seconds=0.0,
                )
            )
            if current_holdings:
                if not skip_rebalance:
                    emit_progress(progress, "读取当前持仓并生成调仓计划")
                    current = load_current_holdings_csv(current_holdings)
                    plan = build_rebalance_plan(
                        current,
                        [_holding_from_dict(row) for row in portfolio_report.holdings],
                        as_of=portfolio_report.as_of,
                    )
                    rebalance_json, rebalance_csv = save_rebalance_plan(config.paths.data_root, plan)
                    outputs.update({"rebalance_json": rebalance_json.as_posix(), "rebalance_csv": rebalance_csv.as_posix()})
                    rebalance_payload = plan.to_dict()
                    steps.append(
                        DailyStepResult(
                            step_name="rebalance_plan",
                            status="success",
                            message="rebalance plan generated",
                            output_paths=[rebalance_json.as_posix(), rebalance_csv.as_posix()],
                            metrics={"turnover": plan.turnover},
                            duration_seconds=0.0,
                        )
                    )
                else:
                    warnings.append("rebalance plan skipped by --skip-rebalance")
        else:
            portfolio_report = None
            steps.append(
                DailyStepResult(
                    step_name="portfolio_build",
                    status="skipped",
                    message="portfolio skipped",
                    output_paths=[],
                    metrics={},
                    duration_seconds=0.0,
                )
            )
            steps.append(
                DailyStepResult(
                    step_name="portfolio_risk",
                    status="skipped",
                    message="portfolio skipped",
                    output_paths=[],
                    metrics={},
                    duration_seconds=0.0,
                )
            )

        if skip_report:
            steps.append(
                DailyStepResult(
                    step_name="daily_report",
                    status="skipped",
                    message="report skipped",
                    output_paths=[],
                    metrics={},
                    duration_seconds=0.0,
                )
            )
            report = _build_report(
                as_of=latest_trade_date,
                run_started=run_started,
                data_run_id=data_run_id,
                steps=steps,
                data_quality=data_quality,
                strategy_summary={"status": "skipped"},
                consensus_summary={"status": "skipped"},
                portfolio_summary=portfolio_payload,
                rebalance_summary=rebalance_payload,
                outputs=outputs,
                warnings=warnings,
                errors=errors,
            )
            stock_names = build_stock_name_map(config.paths.tdx_export, collect_stock_keys(report.to_dict()))
            markdown = render_daily_markdown(report, stock_names=stock_names)
            return DailyWorkflowResult(report=report, markdown=markdown, outputs=outputs)

        report = _build_report(
            as_of=latest_trade_date,
            run_started=run_started,
            data_run_id=data_run_id,
            steps=steps,
            data_quality=data_quality,
            strategy_summary={"strategies": strategy_names, "limit": strategy_limit, "min_score": min_score},
            consensus_summary={"min_hit": min_hit, "row_count": len(consensus_payload.get("rows") or []), "rows": consensus_payload.get("rows") or []},
            portfolio_summary=portfolio_payload,
            rebalance_summary=rebalance_payload,
            outputs=outputs,
            warnings=warnings,
            errors=errors,
        )
        emit_progress(progress, "生成每日 Markdown 报告")
        stock_names = build_stock_name_map(config.paths.tdx_export, collect_stock_keys(report.to_dict()))
        markdown = render_daily_markdown(report, stock_names=stock_names)
        saved = save_daily_report(config.paths.data_root, report, markdown)
        outputs.update(saved)
        steps.append(
            DailyStepResult(
                step_name="daily_report",
                status="success",
                message="daily report generated",
                output_paths=list(saved.values()),
                metrics={"warning_count": len(report.warnings), "error_count": len(report.errors)},
                duration_seconds=0.0,
            )
        )
        steps.append(
            DailyStepResult(
                step_name="save_manifest",
                status="success",
                message="manifest saved",
                output_paths=[saved["manifest"]],
                metrics={"data_run_id": data_run_id},
                duration_seconds=0.0,
            )
        )
        return DailyWorkflowResult(report=report, markdown=markdown, outputs=outputs)
    finally:
        ctx.close()


def _run_step(name: str, fn: Callable[[], Any], success_status: str = "success") -> DailyStepResult:
    start = perf_counter()
    result = fn()
    duration = perf_counter() - start
    return DailyStepResult(step_name=name, status=success_status, message="ok", metrics={"result": result}, duration_seconds=duration)


def _run_strategies(
    config: AppConfig,
    strategy_names: list[str],
    as_of: date,
    *,
    strategy_limit: int,
    min_score: float,
) -> tuple[dict[str, Any], dict[str, str]]:
    steps: list[DailyStepResult] = []
    outputs: dict[str, str] = {}
    warnings: list[str] = []
    errors: list[str] = []
    for strategy_name in strategy_names:
        definition = get_strategy(strategy_name)
        params = definition.default_params
        if hasattr(params, "__dataclass_fields__"):
            params = replace(params, limit=strategy_limit, min_score=min_score, as_of=as_of)
        report = definition.runner(config, params)
        outputs.update(
            save_report_document(
                config.paths.data_root,
                definition.name,
                build_report_document(
                    strategy_name=definition.name,
                    as_of=as_of,
                    generated_at=datetime.now(),
                    data_run_id=optional_str(report.summary.get("dataset_run_id")),
                    factor_version=optional_str(report.summary.get("factor_version")),
                    params=params,
                    report=report,
                ),
            )
        )
        steps.append(
            DailyStepResult(
                step_name=f"strategy:{definition.name}",
                status="success",
                message="saved",
                output_paths=list(outputs.values()),
                metrics={"picked": len(report.picks)},
                duration_seconds=0.0,
            )
        )
    warnings2, errors2 = collect_warnings_errors([step.to_dict() for step in steps])
    warnings.extend(warnings2)
    errors.extend(errors2)
    return {"steps": steps, "warnings": warnings, "errors": errors}, outputs


def _run_compare(config: AppConfig, strategy_names: list[str], as_of: date) -> dict[str, Any]:
    result = compare_strategies(config, strategy_names, as_of=as_of)
    return result.to_dict()


def _run_consensus(config: AppConfig, strategy_names: list[str], as_of: date, *, min_hit: int) -> dict[str, Any]:
    result = build_consensus(config, strategy_names, as_of=as_of, min_hit=min_hit)
    return result.to_dict()


def _load_latest_trade_date(config: AppConfig) -> date:
    ctx = open_query_context(config)
    try:
        row = ctx.con.execute("SELECT max(trade_date) FROM factors").fetchone()
        if row is None or row[0] is None:
            raise FileNotFoundError("latest dataset does not contain any factors rows")
        return row[0]
    finally:
        ctx.close()


def _holding_from_dict(row: dict[str, Any]):
    from ..portfolio.models import Holding

    return Holding(
        market=str(row.get("market") or "").lower(),
        symbol=str(row.get("symbol") or ""),
        weight=float(row.get("weight") or 0.0),
        score=float(row.get("score")) if row.get("score") is not None else None,
        source_strategy=str(row.get("source_strategy") or ""),
        source_strategies=[str(item) for item in row.get("source_strategies") or []],
        candidate_type=str(row.get("candidate_type") or "") or None,
        risk_flags=[str(item) for item in row.get("risk_flags") or []],
        tags=[str(item) for item in row.get("tags") or []],
        reason=str(row.get("reason") or ""),
        risk_score=float(row.get("risk_score")) if row.get("risk_score") is not None else None,
        factor_values=dict(row.get("factor_values") or {}),
    )


def _build_report(
    *,
    as_of: date,
    run_started: datetime,
    data_run_id: str | None,
    steps: list[DailyStepResult],
    data_quality: Any,
    strategy_summary: dict[str, Any],
    consensus_summary: dict[str, Any],
    portfolio_summary: dict[str, Any],
    rebalance_summary: dict[str, Any],
    outputs: dict[str, Any],
    warnings: list[str],
    errors: list[str],
) -> DailyRunReport:
    step_warnings, step_errors = collect_warnings_errors([step.to_dict() for step in steps])
    warnings = list(warnings) + step_warnings
    errors = list(errors) + step_errors
    return DailyRunReport(
        schema_version="daily-report-v1",
        app_version=APP_VERSION,
        as_of=as_of.isoformat(),
        generated_at=run_started.isoformat(timespec="seconds"),
        data_run_id=data_run_id,
        status="success" if not errors else "failed",
        steps=[step.to_dict() for step in steps],
        summary={
            "step_count": len(steps),
            "warning_count": len(warnings),
            "error_count": len(errors),
        },
        data_quality={"checks": data_quality},
        strategy_summary=strategy_summary,
        consensus_summary=consensus_summary,
        portfolio_summary=portfolio_summary,
        rebalance_summary=rebalance_summary,
        warnings=warnings,
        errors=errors,
        outputs=outputs,
    )
