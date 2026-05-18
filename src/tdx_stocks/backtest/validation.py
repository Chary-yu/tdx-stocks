from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Any

from ..config import AppConfig
from ..query import open_query_context
from .engine import run_backtest
from .models import BacktestParams
from .monte_carlo import run_monte_carlo_simulation


@dataclass(frozen=True)
class WalkForwardPhase:
    train_from: str
    train_to: str
    test_from: str
    test_to: str
    best_params: dict[str, Any]
    train_summary: dict[str, Any]
    test_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_walk_forward_validation(
    config: AppConfig,
    strategy_name: str,
    base_params: BacktestParams,
    train_years: int = 3,
    test_years: int = 1,
    *,
    min_scores: list[float] | None = None,
    tops: list[int] | None = None,
    hold_days: list[int] | None = None,
) -> dict[str, Any]:
    from .research import tune_strategy_parameters

    min_scores = min_scores or [55.0, 60.0, 65.0]
    tops = tops or [10, 20, 30]
    hold_days = hold_days or [5, 10, 20]

    phases: list[WalkForwardPhase] = []
    stitched_equity_curve: list[dict[str, Any]] = []
    stitched_periods: list[dict[str, Any]] = []
    stitched_trades: list[dict[str, Any]] = []
    current_equity = 1.0
    current_year = base_params.from_date.year

    while True:
        train_from = max(base_params.from_date, date(current_year, 1, 1))
        train_to = min(base_params.to_date, date(current_year + train_years - 1, 12, 31))
        test_from = max(base_params.from_date, date(current_year + train_years, 1, 1))
        test_to = min(base_params.to_date, date(current_year + train_years + test_years - 1, 12, 31))
        if train_from > train_to or test_from > test_to:
            break

        train_params = _replace_dates(base_params, train_from, train_to)
        scan = tune_strategy_parameters(
            config,
            strategy_name,
            train_params,
            min_scores=min_scores,
            tops=tops,
            hold_days=hold_days,
        )
        best_row = scan["rows"][0] if scan["rows"] else {}
        best_params = {
            "min_score": best_row.get("min_score", train_params.min_score),
            "top": int(best_row.get("top", train_params.top)),
            "hold_days": int(best_row.get("hold_days", train_params.hold_days)),
        }
        test_params = BacktestParams(
            from_date=test_from,
            to_date=test_to,
            top=best_params["top"],
            hold_days=best_params["hold_days"],
            fee_rate=base_params.fee_rate,
            slippage=base_params.slippage,
            market=base_params.market,
            candidate_type=base_params.candidate_type,
            min_score=float(best_params["min_score"]) if best_params["min_score"] is not None else None,
            min_amount_ma20=base_params.min_amount_ma20,
            portfolio=base_params.portfolio,
        )
        test_report = run_backtest(config, strategy_name, test_params)
        stitched_equity_curve.extend(_stitch_equity_curve(test_report.equity_curve, current_equity))
        stitched_periods.extend(test_report.periods)
        stitched_trades.extend(test_report.trades)
        current_equity = stitched_equity_curve[-1]["equity"] if stitched_equity_curve else current_equity
        phases.append(
            WalkForwardPhase(
                train_from=train_from.isoformat(),
                train_to=train_to.isoformat(),
                test_from=test_from.isoformat(),
                test_to=test_to.isoformat(),
                best_params=best_params,
                train_summary=_summarize_scan(scan),
                test_summary={
                    "total_return": test_report.total_return,
                    "annual_return": test_report.annual_return,
                    "max_drawdown": test_report.max_drawdown,
                    "win_rate": test_report.win_rate,
                    "trade_count": test_report.trade_count,
                },
            )
        )
        current_year += test_years
        if date(current_year, 1, 1) > base_params.to_date:
            break

    total_return = round(current_equity - 1.0, 6)
    return {
        "schema_version": "walk-forward-validation-v1",
        "strategy_name": strategy_name,
        "params": base_params.to_dict(),
        "train_years": train_years,
        "test_years": test_years,
        "phases": [phase.to_dict() for phase in phases],
        "equity_curve": stitched_equity_curve,
        "periods": stitched_periods,
        "trades": stitched_trades,
        "summary": {
            "phase_count": len(phases),
            "total_return": total_return,
            "final_equity": round(current_equity, 6),
            "max_drawdown": _equity_curve_max_drawdown(stitched_equity_curve),
        },
    }


def run_stress_test_suite(
    config: AppConfig,
    strategy_name: str,
    base_params: BacktestParams,
    stress_periods: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, (from_value, to_value) in stress_periods.items():
        params = _replace_dates(
            base_params,
            date.fromisoformat(from_value),
            date.fromisoformat(to_value),
        )
        report = run_backtest(config, strategy_name, params)
        rows.append(
            {
                "period": name,
                "from_date": from_value,
                "to_date": to_value,
                "trade_count": report.trade_count,
                "period_count": report.period_count,
                "total_return": report.total_return,
                "annual_return": report.annual_return,
                "max_drawdown": report.max_drawdown,
                "win_rate": report.win_rate,
                "turnover": getattr(report, "turnover", None),
            }
        )
    return {
        "schema_version": "stress-test-v1",
        "strategy_name": strategy_name,
        "params": base_params.to_dict(),
        "rows": rows,
    }


def run_monte_carlo_from_report(
    report: dict[str, Any],
    *,
    iterations: int = 1000,
    seed: int | None = None,
) -> dict[str, Any]:
    trades = report.get("trades") or []
    initial_cash = 1.0
    portfolio = (report.get("params") or {}).get("portfolio") or {}
    if isinstance(portfolio, dict) and portfolio.get("initial_cash") is not None:
        initial_cash = float(portfolio["initial_cash"])
    return run_monte_carlo_simulation(trades, initial_cash, iterations=iterations, seed=seed)


def _replace_dates(params: BacktestParams, from_date: date, to_date: date) -> BacktestParams:
    return BacktestParams(
        from_date=from_date,
        to_date=to_date,
        top=params.top,
        hold_days=params.hold_days,
        fee_rate=params.fee_rate,
        slippage=params.slippage,
        market=params.market,
        candidate_type=params.candidate_type,
        min_score=params.min_score,
        min_amount_ma20=params.min_amount_ma20,
        portfolio=params.portfolio,
    )


def _summarize_scan(scan: dict[str, Any]) -> dict[str, Any]:
    rows = scan.get("rows") or []
    return {
        "row_count": len(rows),
        "best_research_score": rows[0]["research_score"] if rows else None,
    }


def _stitch_equity_curve(entries: list[dict[str, Any]], current_equity: float) -> list[dict[str, Any]]:
    if not entries:
        return []
    base = float(entries[0].get("equity") or 0.0) or 1.0
    scale = current_equity / base
    stitched: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        row["equity"] = round(float(entry.get("equity") or 0.0) * scale, 6)
        if "cash" in row:
            row["cash"] = round(float(row["cash"]) * scale, 6)
        if "market_value" in row:
            row["market_value"] = round(float(row["market_value"]) * scale, 6)
        stitched.append(row)
    return stitched


def _equity_curve_max_drawdown(entries: list[dict[str, Any]]) -> float:
    peak = 0.0
    max_dd = 0.0
    for entry in entries:
        equity = float(entry.get("equity") or 0.0)
        if equity > peak:
            peak = equity
        if peak > 0:
            drawdown = (peak - equity) / peak
            if drawdown > max_dd:
                max_dd = drawdown
    return round(max_dd, 6)
