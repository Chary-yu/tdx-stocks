from __future__ import annotations

from ..backtest import BacktestParams, run_backtest
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult


def run_backtest_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    strategy = data.get("strategy") or {}
    backtest = data.get("backtest") or {}
    params = BacktestParams(
        from_date=parse_iso_date(backtest.get("from_date")),
        to_date=parse_iso_date(backtest.get("to_date")),
        top=int(backtest.get("top") or strategy.get("limit") or 20),
        hold_days=int(backtest.get("hold_days") or 5),
        fee_rate=float(backtest.get("fee_rate") or (backtest.get("fee_bps") or 0.0) / 10_000),
        slippage=float(backtest.get("slippage") or (backtest.get("slippage_bps") or 0.0) / 10_000),
        market=backtest.get("market"),
        candidate_type=backtest.get("candidate_type"),
        min_score=backtest.get("min_score") or strategy.get("min_score"),
        min_amount_ma20=backtest.get("min_amount_ma20") or strategy.get("min_amount_ma20"),
    )
    report = run_backtest(run_config.app_config, str(strategy.get("name") or data.get("strategy_name") or "trend-strength"), params)
    return RunResult(
        task_type="backtest",
        name=str((data.get("task") or {}).get("name") or "backtest"),
        status="success",
        summary=report.to_dict(),
    )
