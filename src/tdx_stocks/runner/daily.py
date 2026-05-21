from __future__ import annotations

from datetime import date

from ..daily import run_daily_workflow
from .config import LoadedRunConfig
from .models import RunResult
from ..progress import ProgressCallback, emit_progress


def run_daily_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取每日任务配置")
    data = run_config.config
    strategies = data.get("strategies") or {}
    consensus = data.get("consensus") or {}
    portfolio = data.get("portfolio") or {}
    rebalance = data.get("rebalance") or {}
    macro_filter = data.get("macro_filter") if isinstance(data.get("macro_filter"), dict) else {}
    event_calendar = data.get("event_calendar") if isinstance(data.get("event_calendar"), dict) else {}
    as_of_value = (data.get("data") or {}).get("as_of") or "latest"
    as_of = None if str(as_of_value).lower() in {"latest", "auto"} else date.fromisoformat(str(as_of_value))
    report = run_daily_workflow(
        run_config.app_config,
        as_of=as_of,
        strategies=list(strategies.get("enabled") or []) or None,
        strategy_limit=strategies.get("limit"),
        min_score=strategies.get("min_score"),
        min_hit=consensus.get("min_hit"),
        portfolio_top=portfolio.get("top"),
        portfolio_weighting=portfolio.get("weighting"),
        portfolio_max_weight=portfolio.get("max_weight"),
        current_holdings=rebalance.get("current_holdings"),
        skip_strategies=not bool(strategies.get("enabled", True)),
        skip_portfolio=not bool(portfolio.get("enabled", True)),
        skip_rebalance=not bool(rebalance.get("enabled", False)),
        skip_report=dry_run,
        build_data=False,
        macro_filter=macro_filter,
        event_calendar=event_calendar,
        progress=progress,
    )
    summary = report.report.summary
    emit_progress(progress, "准备每日报告输出")
    return RunResult(
        task_type="daily",
        name=run_config.task_name,
        status=report.report.status,
        summary={"daily": summary, "daily_report": report.report.to_dict()},
        outputs=report.outputs,
        steps=[],
        warnings=list(report.report.warnings),
        errors=list(report.report.errors),
    )
