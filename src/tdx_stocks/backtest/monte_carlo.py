from __future__ import annotations

from dataclasses import dataclass, asdict
from random import Random
from statistics import mean
from typing import Any

from .models import BacktestTrade


@dataclass(frozen=True)
class MonteCarloSummary:
    iterations: int
    trade_count: int
    initial_cash: float
    final_equity_p05: float
    final_equity_p50: float
    final_equity_p95: float
    max_drawdown_p05: float
    max_drawdown_p50: float
    max_drawdown_p95: float
    average_final_equity: float
    average_max_drawdown: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_monte_carlo_simulation(
    trades: list[BacktestTrade | dict[str, Any]],
    initial_cash: float,
    iterations: int = 1000,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    rng = Random(seed)
    returns = [float(_trade_return(trade)) for trade in trades if _trade_return(trade) is not None]
    if not returns:
        summary = MonteCarloSummary(
            iterations=iterations,
            trade_count=0,
            initial_cash=initial_cash,
            final_equity_p05=initial_cash,
            final_equity_p50=initial_cash,
            final_equity_p95=initial_cash,
            max_drawdown_p05=0.0,
            max_drawdown_p50=0.0,
            max_drawdown_p95=0.0,
            average_final_equity=initial_cash,
            average_max_drawdown=0.0,
        )
        return {
            "schema_version": "monte-carlo-v1",
            "iterations": iterations,
            "trade_count": 0,
            "initial_cash": initial_cash,
            "summary": summary.to_dict(),
            "runs": [],
        }

    runs: list[dict[str, float]] = []
    for _ in range(iterations):
        sampled_returns = rng.choices(returns, k=len(returns))
        cash = initial_cash
        peak = initial_cash
        max_dd = 0.0
        for trade_return in sampled_returns:
            cash *= 1.0 + trade_return
            if cash > peak:
                peak = cash
            drawdown = (peak - cash) / peak if peak > 0 else 0.0
            if drawdown > max_dd:
                max_dd = drawdown
        runs.append({"final_equity": cash, "max_drawdown": max_dd})

    final_equities = [run["final_equity"] for run in runs]
    max_drawdowns = [run["max_drawdown"] for run in runs]
    summary = MonteCarloSummary(
        iterations=iterations,
        trade_count=len(returns),
        initial_cash=initial_cash,
        final_equity_p05=_percentile(final_equities, 0.05),
        final_equity_p50=_percentile(final_equities, 0.50),
        final_equity_p95=_percentile(final_equities, 0.95),
        max_drawdown_p05=_percentile(max_drawdowns, 0.05),
        max_drawdown_p50=_percentile(max_drawdowns, 0.50),
        max_drawdown_p95=_percentile(max_drawdowns, 0.95),
        average_final_equity=round(mean(final_equities), 6),
        average_max_drawdown=round(mean(max_drawdowns), 6),
    )
    return {
        "schema_version": "monte-carlo-v1",
        "iterations": iterations,
        "trade_count": len(returns),
        "initial_cash": initial_cash,
        "summary": summary.to_dict(),
        "runs": runs,
    }


def _trade_return(trade: BacktestTrade | dict[str, Any]) -> float | None:
    if isinstance(trade, BacktestTrade):
        return trade.net_return
    value = trade.get("net_return") if isinstance(trade, dict) else None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 6)
    position = pct * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return round(ordered[lower], 6)
    weight = position - lower
    return round(ordered[lower] * (1 - weight) + ordered[upper] * weight, 6)
