from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from statistics import mean
from typing import Any

from .. import __version__ as APP_VERSION
from ..config import AppConfig
from ..exit_codes import NoDataError
from ..query import open_query_context
from ..strategies.base import StrategyParams
from ..strategies.registry import get_strategy
from .metrics import annualize_return, max_drawdown
from .models import BacktestParams, BacktestPeriod, BacktestReport, BacktestTrade
from .prices import load_adj_open_price, load_trading_dates

OpenQueryContextFn = Callable[[AppConfig], Any]
StrategyRunnerFn = Callable[[AppConfig, StrategyParams], Any]
PriceLoaderFn = Callable[[Any, str, str, date], float | None]
TradingDatesFn = Callable[[Any, date, date, str | None], list[date]]


@dataclass(frozen=True)
class BacktestContext:
    con: Any
    manifest: dict[str, Any]

    def close(self) -> None:
        self.con.close()


def run_backtest(
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    *,
    open_query_context_fn: OpenQueryContextFn | None = None,
    strategy_runner_fn: StrategyRunnerFn | None = None,
    price_loader_fn: PriceLoaderFn | None = None,
    trading_dates_fn: TradingDatesFn | None = None,
) -> BacktestReport:
    open_query_context_fn = open_query_context_fn or open_query_context
    price_loader_fn = price_loader_fn or load_adj_open_price
    trading_dates_fn = trading_dates_fn or load_trading_dates
    if strategy_runner_fn is None:
        strategy_runner_fn = get_strategy(strategy_name).runner

    ctx = open_query_context_fn(config)
    try:
        trading_dates = trading_dates_fn(ctx.con, params.from_date, params.to_date, params.market)
        if not trading_dates:
            raise NoDataError("no trading dates found for the selected backtest range")
        periods: list[BacktestPeriod] = []
        trades: list[BacktestTrade] = []
        equity_curve: list[dict[str, Any]] = []
        equity = 1.0
        empty_period_count = 0

        for index, signal_date in enumerate(trading_dates):
            buy_index = index + 1
            sell_index = buy_index + params.hold_days
            if buy_index >= len(trading_dates) or sell_index >= len(trading_dates):
                periods.append(
                    BacktestPeriod(
                        signal_date=signal_date.isoformat(),
                        buy_date=None,
                        sell_date=None,
                        trade_count=0,
                        empty=True,
                        period_return=0.0,
                        equity=equity,
                        skipped_reasons=["insufficient_future_dates"],
                    )
                )
                empty_period_count += 1
                continue

            buy_date = trading_dates[buy_index]
            sell_date = trading_dates[sell_index]
            report = strategy_runner_fn(
                config,
                StrategyParams(
                    limit=params.top,
                    min_score=params.min_score or 60.0,
                    min_amount_ma20=params.min_amount_ma20 or 50_000_000.0,
                    market=params.market,
                    candidate_type=params.candidate_type,
                    as_of=signal_date,
                ),
            )
            period_trades: list[float] = []
            skipped_reasons: list[str] = []
            for candidate in report.picks[: params.top]:
                market = str(candidate.get("market") or "").lower()
                symbol = str(candidate.get("symbol") or "")
                buy_price = price_loader_fn(ctx.con, market, symbol, buy_date)
                sell_price = price_loader_fn(ctx.con, market, symbol, sell_date)
                if buy_price is None or sell_price is None:
                    skipped_reasons.append(f"missing_price:{market}:{symbol}")
                    trades.append(
                        BacktestTrade(
                            signal_date=signal_date.isoformat(),
                            buy_date=buy_date.isoformat(),
                            sell_date=sell_date.isoformat(),
                            market=market,
                            symbol=symbol,
                            display_symbol=str(candidate.get("display_symbol") or f"{symbol}.{market.upper()}"),
                            score=_float(candidate.get("score")),
                            candidate_type=str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None,
                            buy_price=buy_price,
                            sell_price=sell_price,
                            gross_return=None,
                            net_return=None,
                            skipped_reason="missing_price",
                        )
                    )
                    continue
                gross_return = sell_price / buy_price - 1.0
                net_return = gross_return - 2.0 * (params.fee_rate + params.slippage)
                period_trades.append(net_return)
                trades.append(
                    BacktestTrade(
                        signal_date=signal_date.isoformat(),
                        buy_date=buy_date.isoformat(),
                        sell_date=sell_date.isoformat(),
                        market=market,
                        symbol=symbol,
                        display_symbol=str(candidate.get("display_symbol") or f"{symbol}.{market.upper()}"),
                        score=_float(candidate.get("score")),
                        candidate_type=str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        gross_return=round(gross_return, 6),
                        net_return=round(net_return, 6),
                    )
                )

            if not period_trades:
                empty_period_count += 1
                period_return = 0.0
            else:
                period_return = round(mean(period_trades), 6)
            equity = round(equity * (1.0 + period_return), 6)
            equity_curve.append(
                {
                    "signal_date": signal_date.isoformat(),
                    "buy_date": buy_date.isoformat(),
                    "sell_date": sell_date.isoformat(),
                    "period_return": period_return,
                    "equity": equity,
                }
            )
            periods.append(
                BacktestPeriod(
                    signal_date=signal_date.isoformat(),
                    buy_date=buy_date.isoformat(),
                    sell_date=sell_date.isoformat(),
                    trade_count=len(period_trades),
                    empty=not period_trades,
                    period_return=period_return,
                    equity=equity,
                    skipped_reasons=skipped_reasons,
                )
            )

        period_returns = [period.period_return for period in periods]
        total_return = round(equity - 1.0, 6)
        trade_returns = [trade.net_return for trade in trades if trade.net_return is not None]
        win_rate = round(
            sum(1 for value in trade_returns if value > 0) / len(trade_returns),
            6,
        ) if trade_returns else 0.0
        start = trading_dates[0]
        end = trading_dates[-1] if trading_dates else params.to_date
        days = (end - start).days if end and start else 0
        return BacktestReport(
            schema_version="backtest-report-v1",
            app_version=APP_VERSION,
            strategy_name=strategy_name,
            params=params.to_dict(),
            start_date=start.isoformat(),
            end_date=end.isoformat() if end else params.to_date.isoformat(),
            trade_count=len(trade_returns),
            period_count=len(periods),
            empty_period_count=empty_period_count,
            total_return=total_return,
            annual_return=annualize_return(total_return, days),
            max_drawdown=max_drawdown([entry["equity"] for entry in equity_curve]),
            win_rate=win_rate,
            avg_period_return=round(mean(period_returns), 6) if period_returns else 0.0,
            best_period_return=round(max(period_returns), 6) if period_returns else 0.0,
            worst_period_return=round(min(period_returns), 6) if period_returns else 0.0,
            turnover=round(len(trade_returns) / len(periods), 6) if periods else 0.0,
            equity_curve=equity_curve,
            periods=[period.to_dict() for period in periods],
            trades=[trade.to_dict() for trade in trades],
        )
    finally:
        ctx.close()


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
