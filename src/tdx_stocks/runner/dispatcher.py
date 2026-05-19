from __future__ import annotations

from .config import LoadedRunConfig
from .backtest import run_backtest_task
from .daily import run_daily_task
from .grid_search import run_grid_search_task
from .models import RunResult
from .portfolio import run_portfolio_task
from .rebalance import run_rebalance_task
from .signal import run_signal_task


def dispatch_run(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    if run_config.task_type == "daily":
        return run_daily_task(run_config, dry_run=dry_run)
    if run_config.task_type == "signal":
        return run_signal_task(run_config, dry_run=dry_run)
    if run_config.task_type == "backtest":
        return run_backtest_task(run_config, dry_run=dry_run)
    if run_config.task_type == "grid_search":
        return run_grid_search_task(run_config, dry_run=dry_run)
    if run_config.task_type == "portfolio":
        return run_portfolio_task(run_config, dry_run=dry_run)
    if run_config.task_type == "rebalance":
        return run_rebalance_task(run_config, dry_run=dry_run)
    raise ValueError(f"unsupported task_type: {run_config.task_type}")
