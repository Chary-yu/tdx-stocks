from __future__ import annotations

from pathlib import Path
from typing import Any

from ..portfolio import Holding, build_rebalance_plan, load_current_holdings_csv
from ..portfolio.loader import load_portfolio_target
from ..portfolio.risk_controls import DEFAULT_EXCLUDE_RISK_TAGS, normalize_exclude_risk_tags
from ..execution.plan import build_execution_plan
from ..events.bus import publish
from ..events.types import Event
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
    macro_filter = data.get("macro_filter") if isinstance(data.get("macro_filter"), dict) else {}
    event_calendar = data.get("event_calendar") if isinstance(data.get("event_calendar"), dict) else {}
    target_source = str(rebalance.get("target_source") or "portfolio")
    if not (target_source in {"portfolio", "portfolio_report"} or target_source.startswith("file:")):
        publish(Event.create("RISK_INTERCEPTED", {"task": "rebalance", "reason": "invalid_target_source"}))
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

    emit_progress(progress, "读取目标组合")
    target_doc = load_portfolio_target(data_root=run_config.app_config.paths.data_root, source=target_source)
    require_risk_filtered = bool(rebalance.get("require_risk_filtered_target", True))
    target_dict = dict(target_doc)
    target_diagnostics = target_dict.get("diagnostics") if isinstance(target_dict.get("diagnostics"), dict) else {}
    if require_risk_filtered and not target_diagnostics.get("risk_filter_applied"):
        publish(Event.create("RISK_INTERCEPTED", {"task": "rebalance", "reason": "risk_filter_required"}))
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
    target_holdings = [_holding_from_dict(row) for row in target_dict.get("holdings") or []]
    plan = build_rebalance_plan(
        current,
        target_holdings,
        as_of=str(target_dict.get("as_of") or resolve_report_as_of(run_config.app_config, as_of_value)),
        min_trade_weight=float(_pick(rebalance.get("min_trade_weight"), 0.0)),
        max_turnover=rebalance.get("max_turnover"),
        cost_model=rebalance.get("cost_model") if isinstance(rebalance.get("cost_model"), dict) else None,
        capital=float(portfolio.get("capital") or 10_000_000),
        target_risk_filter={
            "risk_filter_applied": True,
            "exclude_risk_tags": list(normalize_exclude_risk_tags(portfolio.get("exclude_risk_tags") or DEFAULT_EXCLUDE_RISK_TAGS)),
            "risk_interceptions": target_diagnostics.get("risk_interceptions") or [],
            "market_regime": target_diagnostics.get("market_regime") or {},
        },
    )
    plan_dict = plan.to_dict()
    execution_cfg = data.get("order_execution") if isinstance(data.get("order_execution"), dict) else {}
    rebalance_cfg = data.get("rebalance") if isinstance(data.get("rebalance"), dict) else {}
    if isinstance(rebalance_cfg.get("cost_model"), dict):
        execution_cfg = {**execution_cfg, "cost_model": rebalance_cfg.get("cost_model")}
    execution_plan = build_execution_plan(plan_dict.get("weight_changes") or [], execution_cfg)
    plan_dict["execution_plan"] = execution_plan.to_dict()
    plan_dict["estimated_impact_bps"] = execution_plan.estimated_impact_bps
    plan_dict["execution_advice"] = "建议分批执行" if execution_plan.to_dict().get("batch_execution_recommended") else "可一次执行"
    diagnostics = plan_dict.get("diagnostics") if isinstance(plan_dict.get("diagnostics"), dict) else {}
    regime = diagnostics.get("market_regime") if isinstance(diagnostics.get("market_regime"), dict) else {}
    if regime.get("action") == "pause_open":
        publish(Event.create("MACRO_PAUSE_OPEN", {"task": "rebalance", "as_of": plan_dict.get("as_of")}))
    if str(diagnostics.get("turnover_check", "")).startswith("turnover"):
        publish(Event.create("TURNOVER_EXCEEDED", {"task": "rebalance", "check": diagnostics.get("turnover_check")}))
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
