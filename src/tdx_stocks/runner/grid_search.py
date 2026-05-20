from __future__ import annotations

from ..backtest import BacktestParams, tune_strategy_parameters
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult


def run_grid_search_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    strategy = data.get("strategy") or {}
    backtest = data.get("backtest") or {}
    grid = data.get("grid") or {}
    params = BacktestParams(
        from_date=parse_iso_date(backtest.get("from_date")),
        to_date=parse_iso_date(backtest.get("to_date")),
        top=int(backtest.get("top") or 20),
        hold_days=int(backtest.get("hold_days") or 5),
        fee_rate=float(backtest.get("fee_rate") or 0.0),
        slippage=float(backtest.get("slippage") or 0.0),
        market=backtest.get("market"),
        candidate_type=backtest.get("candidate_type"),
        min_score=backtest.get("min_score") or strategy.get("min_score"),
        min_amount_ma20=backtest.get("min_amount_ma20") or strategy.get("min_amount_ma20"),
    )
    report = tune_strategy_parameters(
        run_config.app_config,
        str(strategy.get("name") or data.get("strategy_name") or "trend-strength"),
        params,
        min_scores=list(grid.get("strategy.min_score") or [55, 60, 65]),
        tops=list(grid.get("backtest.top") or [10, 20, 30]),
        hold_days=list(grid.get("backtest.hold_days") or [5, 10, 20]),
    )
    return RunResult(
        task_type="grid_search",
        name=run_config.task_name,
        status="success",
        summary=report,
        outputs={"grid_markdown": (run_config.app_config.paths.data_root / "reports" / "grid_markdown.md").as_posix()},
    )
