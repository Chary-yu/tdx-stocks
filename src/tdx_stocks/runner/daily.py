from __future__ import annotations

from datetime import date

from ..daily import run_daily_workflow
from .config import LoadedRunConfig
from .models import RunResult


def run_daily_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    strategies = data.get("strategies") or {}
    consensus = data.get("consensus") or {}
    portfolio = data.get("portfolio") or {}
    rebalance = data.get("rebalance") or {}
    as_of_value = (data.get("data") or {}).get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else date.fromisoformat(str(as_of_value))
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
    )
    summary = report.report.summary
    return RunResult(
        task_type="daily",
        name=run_config.task_name,
        status=report.report.status,
        summary={"daily": summary},
        outputs=report.outputs,
        steps=[],
        warnings=list(report.report.warnings),
        errors=list(report.report.errors),
    )
