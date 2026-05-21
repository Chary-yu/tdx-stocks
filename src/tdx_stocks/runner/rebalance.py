from __future__ import annotations

from pathlib import Path
from typing import Any

from ..portfolio import Holding, build_portfolio, build_rebalance_plan, load_current_holdings_csv
from ..portfolio.risk_controls import DEFAULT_EXCLUDE_RISK_TAGS, normalize_exclude_risk_tags
from ..execution.plan import build_execution_plan
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress
from .dates import resolve_report_as_of


def run_rebalance_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取调仓任务配置")
    data = run_config.config
    portfolio = data.get("portfolio") or {}
    rebalance = data.get("rebalance") or {}
    target_source = str(rebalance.get("target_source") or "portfolio")
    if target_source not in {"portfolio", "portfolio_report"}:
        return RunResult(
            task_type="rebalance",
            name=run_config.task_name,
            status="failed",
            summary={"summary": "failed", "error": "调仓输入未经过组合风控过滤，已拒绝生成调仓计划"},
            outputs={},
            errors=["调仓输入未经过组合风控过滤，已拒绝生成调仓计划"],
        )
    task_data = data.get("data") or {}
    as_of_value = task_data.get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else parse_iso_date(as_of_value)

    def _pick(value: Any, fallback: Any) -> Any:
        return fallback if value is None else value

    emit_progress(progress, "构建目标组合")
    target = build_portfolio(
        run_config.app_config,
        source=str(portfolio.get("source") or "consensus"),
        top=int(_pick(portfolio.get("top"), 20)),
        weighting=str(portfolio.get("weighting") or "liquidity-risk"),
        max_weight=float(_pick(portfolio.get("max_weight"), 0.10)),
        min_weight=float(_pick(portfolio.get("min_weight"), 0.0)),
        max_risk_score=portfolio.get("max_risk_score"),
        exclude_risk_tags=normalize_exclude_risk_tags(portfolio.get("exclude_risk_tags") or DEFAULT_EXCLUDE_RISK_TAGS),
        market=portfolio.get("market"),
        capital=float(portfolio.get("capital") or 10_000_000),
        max_adv_participation=float(portfolio.get("max_adv_participation") or 0.10),
        max_liquidation_days=float(portfolio.get("max_liquidation_days") or 0.5),
        market_regime_enabled=bool(portfolio.get("market_regime_enabled", True)),
        sector_max_weight=float(portfolio.get("max_sector_weight") or 0.25),
        as_of=as_of,
    )
    require_risk_filtered = bool(rebalance.get("require_risk_filtered_target", True))
    target_dict = target.to_dict()
    target_diagnostics = target_dict.get("diagnostics") if isinstance(target_dict.get("diagnostics"), dict) else {}
    if require_risk_filtered and not target_diagnostics.get("risk_filter_applied"):
        return RunResult(
            task_type="rebalance",
            name=run_config.task_name,
            status="failed",
            summary={
                "summary": "failed",
                "error": "调仓输入未经过组合风控过滤，已拒绝生成调仓计划",
                "risk_filter_required": True,
            },
            outputs={},
            errors=["调仓输入未经过组合风控过滤，已拒绝生成调仓计划"],
        )
    emit_progress(progress, "读取当前持仓")
    holdings_path = rebalance.get("current_holdings")
    current = load_current_holdings_csv(Path(holdings_path)) if holdings_path else []
    emit_progress(progress, "生成调仓计划")
    target_holdings = [_holding_from_dict(row) for row in target.holdings]
    plan = build_rebalance_plan(
        current,
        target_holdings,
        as_of=target.as_of,
        min_trade_weight=float(_pick(rebalance.get("min_trade_weight"), 0.0)),
        max_turnover=rebalance.get("max_turnover"),
        target_risk_filter={
            "risk_filter_applied": True,
            "exclude_risk_tags": list(normalize_exclude_risk_tags(portfolio.get("exclude_risk_tags") or DEFAULT_EXCLUDE_RISK_TAGS)),
            "risk_interceptions": target_diagnostics.get("risk_interceptions") or [],
            "market_regime": target_diagnostics.get("market_regime") or {},
        },
    )
    plan_dict = plan.to_dict()
    execution_cfg = data.get("order_execution") if isinstance(data.get("order_execution"), dict) else {}
    execution_plan = build_execution_plan(plan_dict.get("weight_changes") or [], execution_cfg)
    plan_dict["execution_plan"] = execution_plan.to_dict()
    plan_dict["estimated_impact_bps"] = execution_plan.estimated_impact_bps
    plan_dict["execution_advice"] = "建议分批执行" if execution_plan.to_dict().get("batch_execution_recommended") else "可一次执行"
    emit_progress(progress, "准备调仓报告输出")
    return RunResult(
        task_type="rebalance",
        name=run_config.task_name,
        status="success",
        summary=plan_dict,
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "rebalance", as_of=resolve_report_as_of(run_config.app_config, plan.as_of)),
    )


def _holding_from_dict(row: dict[str, Any]) -> Holding:
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
