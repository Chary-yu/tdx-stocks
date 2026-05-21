from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev
from time import perf_counter
from typing import Any

from .. import __version__ as APP_VERSION
from ..config import AppConfig
from ..exit_codes import NoDataError
from ..query import open_query_context
from ..progress import ProgressCallback, emit_progress
from ..strategies.base import StrategyParams
from ..strategies.registry import get_strategy
from .metrics import annualize_return, max_drawdown
from .models import BacktestParams, BacktestPeriod, BacktestReport, BacktestTrade, PortfolioParams, Position
from .prices import (
    AdjDailyPrice,
    PriceLike,
    coerce_adj_daily_price,
    coerce_adj_open_price,
    load_adj_daily_price,
    load_trading_dates,
)
from .exits import ExitEngine
from .sizing import calc_target_shares

OpenQueryContextFn = Callable[[AppConfig], Any]
StrategyRunnerFn = Callable[[AppConfig, StrategyParams], Any]
PriceLoaderFn = Callable[[Any, str, str, date], PriceLike | None]
DailyPriceLoaderFn = Callable[[Any, str, str, date], AdjDailyPrice | dict[str, Any] | None]
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
    progress: ProgressCallback | None = None,
    progress_prefix: str = "回测进度",
) -> BacktestReport:
    if params.portfolio is not None:
        return run_portfolio_backtest(
            config,
            strategy_name,
            params,
            open_query_context_fn=open_query_context_fn,
            strategy_runner_fn=strategy_runner_fn,
            trading_dates_fn=trading_dates_fn,
        )
    open_query_context_fn = open_query_context_fn or open_query_context
    trading_dates_fn = trading_dates_fn or load_trading_dates
    if strategy_runner_fn is None:
        strategy_runner_fn = get_strategy(strategy_name).runner

    ctx = open_query_context_fn(config)
    try:
        trading_dates = trading_dates_fn(ctx.con, params.from_date, params.to_date, params.market)
        if not trading_dates:
            raise NoDataError("no trading dates found for the selected backtest range")
        if price_loader_fn is not None:
            return _run_backtest_loop(
                ctx.con,
                config,
                strategy_name,
                params,
                trading_dates,
                strategy_runner_fn,
                price_loader_fn,
                progress=progress,
                progress_prefix=progress_prefix,
            )
        return _run_backtest_vectorized(
            ctx.con,
            config,
            strategy_name,
            params,
            trading_dates,
            strategy_runner_fn,
            progress=progress,
            progress_prefix=progress_prefix,
        )
    finally:
        ctx.close()


def run_portfolio_backtest(
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    *,
    open_query_context_fn: OpenQueryContextFn | None = None,
    strategy_runner_fn: StrategyRunnerFn | None = None,
    daily_price_loader_fn: DailyPriceLoaderFn | None = None,
    trading_dates_fn: TradingDatesFn | None = None,
) -> BacktestReport:
    open_query_context_fn = open_query_context_fn or open_query_context
    trading_dates_fn = trading_dates_fn or load_trading_dates
    daily_price_loader_fn = daily_price_loader_fn or load_adj_daily_price
    if strategy_runner_fn is None:
        strategy_runner_fn = get_strategy(strategy_name).runner
    portfolio_params = params.portfolio or PortfolioParams()

    ctx = open_query_context_fn(config)
    try:
        trading_dates = trading_dates_fn(ctx.con, params.from_date, params.to_date, params.market)
        if not trading_dates:
            raise NoDataError("no trading dates found for the selected backtest range")

        signal_map = _collect_portfolio_signals(config, params, trading_dates, strategy_runner_fn)
        cash = portfolio_params.initial_cash
        reserved_margin = 0.0
        active_positions: dict[str, Position] = {}
        trades: list[BacktestTrade] = []
        periods: list[BacktestPeriod] = []
        equity_curve: list[dict[str, Any]] = []
        empty_period_count = 0

        for index, today in enumerate(trading_dates):
            today_bar_cache: dict[tuple[str, str, date], AdjDailyPrice | None] = {}
            activity_count = 0
            skipped_reasons: list[str] = []
            buy_date = None
            sell_date = None
            signal_date = trading_dates[index - 1] if index > 0 else None
            score_map: dict[tuple[str, str], float] = {}
            if signal_date is not None:
                for candidate in signal_map.get(signal_date, []):
                    market = str(candidate.get("market") or "").lower()
                    symbol = str(candidate.get("symbol") or "")
                    score = _float(candidate.get("score"))
                    if market and symbol and score is not None:
                        score_map[(market, symbol)] = score

            for symbol, pos in list(active_positions.items()):
                latest_score = score_map.get((str(pos.market or "").lower(), symbol))
                if latest_score is not None:
                    pos.score = latest_score
                bar = _load_daily_bar(
                    ctx.con,
                    daily_price_loader_fn,
                    today_bar_cache,
                    pos.market or "",
                    symbol,
                    today,
                )
                if pos.direction == "SHORT":
                    if bar is None or bar.is_suspended or bar.is_limit_up:
                        continue
                elif bar is None or bar.is_suspended or bar.is_limit_down:
                    continue
                hold_days = (today - pos.buy_date).days
                exit_reason = None
                exit_trigger = None
                if pos.direction != "SHORT":
                    exit_reason, exit_trigger = ExitEngine.check(pos, bar, portfolio_params, hold_days=hold_days)
                if exit_reason is None and portfolio_params.exit_when_score_below is not None and pos.score is not None:
                    if float(pos.score) < float(portfolio_params.exit_when_score_below):
                        exit_reason, exit_trigger = "score_below_threshold", "signal_exit"
                if exit_reason is None and portfolio_params.max_hold_days is not None and hold_days >= portfolio_params.max_hold_days:
                    exit_reason, exit_trigger = "max_holding_days", "max_hold"
                if exit_reason is None and hold_days >= params.hold_days:
                    exit_reason, exit_trigger = "hold_days", "legacy_hold_days"
                if exit_reason is None:
                    continue
                if pos.direction == "SHORT":
                    cover_cost = pos.shares * bar.open_price * (1 + params.fee_rate + params.slippage)
                    cash -= cover_cost
                    reserved_margin = max(0.0, reserved_margin - pos.margin_locked)
                    gross_return = pos.buy_price / bar.open_price - 1.0
                    net_return = gross_return - 2.0 * (params.fee_rate + params.slippage)
                else:
                    sell_proceeds = pos.shares * bar.open_price * (1 - params.fee_rate - params.slippage)
                    cash += sell_proceeds
                    gross_return = bar.open_price / pos.buy_price - 1.0
                    net_return = sell_proceeds / (pos.shares * pos.buy_price * (1 + params.fee_rate + params.slippage)) - 1.0
                trades.append(
                    BacktestTrade(
                        signal_date=pos.signal_date.isoformat() if pos.signal_date else pos.buy_date.isoformat(),
                        buy_date=pos.buy_date.isoformat(),
                        sell_date=today.isoformat(),
                        market=pos.market or "",
                        symbol=symbol,
                        display_symbol=pos.display_symbol or symbol,
                        score=pos.score,
                        candidate_type=pos.candidate_type,
                        buy_price=pos.buy_price,
                        sell_price=bar.open_price,
                        gross_return=round(gross_return, 6),
                        net_return=round(net_return, 6),
                        direction=pos.direction,
                        shares=pos.shares,
                        exit_reason=exit_reason,
                        exit_trigger=exit_trigger,
                        actual_hold_days=hold_days,
                    )
                )
                del active_positions[symbol]
                activity_count += 1
                sell_date = today

            for candidate in signal_map.get(signal_date, []):
                if len(active_positions) >= portfolio_params.max_positions:
                    skipped_reasons.append("max_positions")
                    break
                symbol = str(candidate.get("symbol") or "")
                market = str(candidate.get("market") or "").lower()
                if not symbol or symbol in active_positions:
                    continue
                bar = _load_daily_bar(
                    ctx.con,
                    daily_price_loader_fn,
                    today_bar_cache,
                    market,
                    symbol,
                    today,
                )
                direction = _normalize_direction(candidate.get("direction"))
                if direction == "SHORT":
                    if bar is None or bar.is_limit_down or bar.is_suspended:
                        skipped_reasons.append("limit_down/suspended")
                        continue
                elif bar is None or bar.is_limit_up or bar.is_suspended:
                    skipped_reasons.append("limit_up/suspended")
                    continue
                available_cash = max(0.0, cash - reserved_margin)
                shares = calc_target_shares(available_cash, bar.open_price, portfolio_params)
                if shares < 100:
                    skipped_reasons.append("insufficient_cash")
                    continue
                notional = shares * bar.open_price
                if direction == "SHORT":
                    margin_locked = notional * portfolio_params.margin_rate
                    if margin_locked > available_cash:
                        skipped_reasons.append("insufficient_margin")
                        continue
                    short_proceeds = notional * (1 - params.fee_rate - params.slippage)
                    cash += short_proceeds
                    reserved_margin += margin_locked
                else:
                    buy_cost = notional * (1 + params.fee_rate + params.slippage)
                    if buy_cost > available_cash:
                        skipped_reasons.append("insufficient_cash")
                        continue
                    cash -= buy_cost
                    margin_locked = 0.0
                position = Position(
                    symbol=symbol,
                    shares=shares,
                    buy_price=bar.open_price,
                    buy_date=today,
                    direction=direction,
                    market=market,
                    display_symbol=str(candidate.get("display_symbol") or f"{symbol}.{market.upper()}"),
                    score=_float(candidate.get("score")),
                    candidate_type=str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None,
                    signal_date=signal_date,
                    margin_locked=margin_locked,
                    highest_price=float(bar.high_price),
                )
                active_positions[symbol] = position
                activity_count += 1
                buy_date = today

            daily_market_value = 0.0
            for symbol, pos in active_positions.items():
                bar = _load_daily_bar(
                    ctx.con,
                    daily_price_loader_fn,
                    today_bar_cache,
                    pos.market or "",
                    symbol,
                    today,
                )
                close_price = bar.close_price if bar is not None else pos.buy_price
                if pos.direction == "SHORT":
                    daily_market_value -= pos.shares * close_price
                else:
                    daily_market_value += pos.shares * close_price
            equity = cash + daily_market_value
            prev_equity = equity_curve[-1]["equity"] if equity_curve else portfolio_params.initial_cash
            period_return = round(equity / prev_equity - 1.0, 6) if prev_equity > 0 else 0.0
            equity_curve.append(
                {
                    "trade_date": today.isoformat(),
                    "cash": round(cash, 6),
                    "market_value": round(daily_market_value, 6),
                    "equity": round(equity, 6),
                }
            )
            periods.append(
                BacktestPeriod(
                    signal_date=today.isoformat(),
                    buy_date=buy_date.isoformat() if buy_date else None,
                    sell_date=sell_date.isoformat() if sell_date else None,
                    trade_count=activity_count,
                    empty=activity_count == 0 and not active_positions,
                    period_return=period_return,
                    equity=round(equity, 6),
                    skipped_reasons=skipped_reasons,
                )
            )
            if activity_count == 0 and not active_positions:
                empty_period_count += 1

        return _build_report(
            strategy_name,
            params,
            trading_dates,
            periods,
            trades,
            equity_curve,
            empty_period_count,
            equity_curve[-1]["equity"] if equity_curve else portfolio_params.initial_cash,
            base_equity=portfolio_params.initial_cash,
        )
    finally:
        ctx.close()


def _run_backtest_vectorized(
    con,
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    trading_dates: list[date],
    strategy_runner_fn: StrategyRunnerFn,
    *,
    progress: ProgressCallback | None = None,
    progress_prefix: str = "回测进度",
) -> BacktestReport:
    periods_input: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    signal_indices = _signal_period_indices(trading_dates, params)
    started_at = perf_counter()
    for period_number, index in enumerate(signal_indices, start=1):
        signal_date = trading_dates[index]
        _emit_backtest_period_progress(progress, progress_prefix, period_number, len(signal_indices), signal_date, started_at)
        buy_index = index + 1
        sell_index = buy_index + params.hold_days
        if buy_index >= len(trading_dates) or sell_index >= len(trading_dates):
            periods_input.append(
                {
                    "signal_date": signal_date,
                    "buy_date": None,
                    "sell_date": None,
                    "signals": [],
                    "skipped_reasons": ["insufficient_future_dates"],
                }
            )
            continue

        buy_date = trading_dates[buy_index]
        sell_date = trading_dates[sell_index]
        report = strategy_runner_fn(config, _strategy_params(params, signal_date))
        period_signals = []
        for signal_rank, candidate in enumerate(report.picks[: params.top]):
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            signal = {
                "signal_date": signal_date,
                "signal_rank": signal_rank,
                "market": market,
                "symbol": symbol,
                "display_symbol": str(candidate.get("display_symbol") or f"{symbol}.{market.upper()}"),
                "score": _float(candidate.get("score")),
                "candidate_type": (
                    str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None
                ),
                "direction": _normalize_direction(candidate.get("direction")),
            }
            signals.append(signal)
            period_signals.append(signal)
        periods_input.append(
            {
                "signal_date": signal_date,
                "buy_date": buy_date,
                "sell_date": sell_date,
                "signals": period_signals,
                "skipped_reasons": [],
            }
        )

    matches = _match_signal_prices(con, signals, params.hold_days)
    benchmark = _benchmark_summary(con, trading_dates, periods_input)
    return _build_report_from_matches(strategy_name, params, trading_dates, periods_input, matches, benchmark=benchmark)


def _run_backtest_loop(
    con,
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    trading_dates: list[date],
    strategy_runner_fn: StrategyRunnerFn,
    price_loader_fn: PriceLoaderFn,
    *,
    progress: ProgressCallback | None = None,
    progress_prefix: str = "回测进度",
) -> BacktestReport:
    periods_input: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    matches: dict[tuple[str, int], dict[str, Any]] = {}
    signal_indices = _signal_period_indices(trading_dates, params)
    started_at = perf_counter()
    for period_number, index in enumerate(signal_indices, start=1):
        signal_date = trading_dates[index]
        _emit_backtest_period_progress(progress, progress_prefix, period_number, len(signal_indices), signal_date, started_at)
        buy_index = index + 1
        sell_index = buy_index + params.hold_days
        if buy_index >= len(trading_dates) or sell_index >= len(trading_dates):
            periods_input.append(
                {
                    "signal_date": signal_date,
                    "buy_date": None,
                    "sell_date": None,
                    "signals": [],
                    "skipped_reasons": ["insufficient_future_dates"],
                }
            )
            continue

        buy_date = trading_dates[buy_index]
        sell_date = trading_dates[sell_index]
        report = strategy_runner_fn(config, _strategy_params(params, signal_date))
        period_signals = []
        for signal_rank, candidate in enumerate(report.picks[: params.top]):
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            signal = {
                "signal_date": signal_date,
                "signal_rank": signal_rank,
                "market": market,
                "symbol": symbol,
                "display_symbol": str(candidate.get("display_symbol") or f"{symbol}.{market.upper()}"),
                "score": _float(candidate.get("score")),
                "candidate_type": (
                    str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None
                ),
                "direction": _normalize_direction(candidate.get("direction")),
            }
            signals.append(signal)
            period_signals.append(signal)
            matches[_signal_key(signal)] = _match_signal_prices_with_loader(
                con,
                signal,
                trading_dates,
                buy_index,
                sell_index,
                price_loader_fn,
            )
        periods_input.append(
            {
                "signal_date": signal_date,
                "buy_date": buy_date,
                "sell_date": sell_date,
                "signals": period_signals,
                "skipped_reasons": [],
            }
        )

    benchmark = _benchmark_summary(con, trading_dates, periods_input)
    return _build_report_from_matches(strategy_name, params, trading_dates, periods_input, matches, benchmark=benchmark)


def _signal_period_indices(trading_dates: list[date], params: BacktestParams) -> list[int]:
    if params.rolling:
        return list(range(len(trading_dates)))
    step = max(1, int(params.hold_days or 1))
    return list(range(0, len(trading_dates), step))


def _emit_backtest_period_progress(
    progress: ProgressCallback | None,
    progress_prefix: str,
    period_number: int,
    total_periods: int,
    signal_date: date,
    started_at: float,
) -> None:
    if progress is None:
        return
    if period_number != 1 and period_number != total_periods and period_number % 10 != 0:
        return
    elapsed = perf_counter() - started_at
    emit_progress(
        progress,
        f"{progress_prefix}：第 {period_number} / {total_periods} 个周期，信号日 {signal_date.isoformat()}，已用时 {elapsed:.1f} 秒",
    )


def _strategy_params(params: BacktestParams, signal_date: date) -> StrategyParams:
    return StrategyParams(
        limit=params.top,
        min_score=params.min_score or 60.0,
        min_amount_ma20=params.min_amount_ma20 or 150_000_000.0,
        market=params.market,
        candidate_type=params.candidate_type,
        as_of=signal_date,
    )


def _build_report_from_matches(
    strategy_name: str,
    params: BacktestParams,
    trading_dates: list[date],
    periods_input: list[dict[str, Any]],
    matches: dict[tuple[str, int], dict[str, Any]],
    *,
    benchmark: dict[str, Any] | None = None,
) -> BacktestReport:
    periods: list[BacktestPeriod] = []
    trades: list[BacktestTrade] = []
    equity_curve: list[dict[str, Any]] = []
    equity = 1.0
    empty_period_count = 0

    for period in periods_input:
        signal_date = period["signal_date"]
        buy_date = period["buy_date"]
        sell_date = period["sell_date"]
        if buy_date is None or sell_date is None:
            periods.append(
                BacktestPeriod(
                    signal_date=signal_date.isoformat(),
                    buy_date=None,
                    sell_date=None,
                    trade_count=0,
                    empty=True,
                    period_return=0.0,
                    equity=equity,
                    skipped_reasons=period["skipped_reasons"],
                )
            )
            empty_period_count += 1
            continue

        period_trades: list[float] = []
        skipped_reasons: list[str] = []
        for signal in period["signals"]:
            match = matches.get(_signal_key(signal))
            trade, net_return = _build_trade_from_match(signal, match, params)
            trades.append(trade)
            if trade.skipped_reason is not None:
                skipped_reasons.append(f"{trade.skipped_reason}:{trade.market}:{trade.symbol}")
            if net_return is not None:
                period_trades.append(net_return)

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

    return _build_report(strategy_name, params, trading_dates, periods, trades, equity_curve, empty_period_count, equity, benchmark=benchmark)


def _build_trade_from_match(
    signal: dict[str, Any],
    match: dict[str, Any] | None,
    params: BacktestParams,
) -> tuple[BacktestTrade, float | None]:
    buy_date = _date_or_none(match.get("buy_date")) if match is not None else None
    sell_date = _date_or_none(match.get("sell_date")) if match is not None else None
    buy_price = _float(match.get("buy_price")) if match is not None else None
    sell_price = _float(match.get("sell_price")) if match is not None else None
    direction = _normalize_direction(signal.get("direction"))
    exit_reason = str(match.get("exit_reason") or "max_holding_days") if match is not None else None

    skipped_reason = None
    if match is None or buy_price is None or buy_date is None:
        skipped_reason = "missing_price"
    elif direction == "SHORT" and (bool(match.get("buy_is_limit_down")) or bool(match.get("buy_is_suspended"))):
        skipped_reason = "limit_down/suspended"
        sell_date = None
        sell_price = None
    elif direction != "SHORT" and (bool(match.get("buy_is_limit_up")) or bool(match.get("buy_is_suspended"))):
        skipped_reason = "limit_up/suspended"
        sell_date = None
        sell_price = None
    elif sell_price is None or sell_date is None:
        skipped_reason = "missing_price"

    if skipped_reason is not None:
        return (
            BacktestTrade(
                signal_date=signal["signal_date"].isoformat(),
                buy_date=buy_date.isoformat() if buy_date is not None else None,
                sell_date=sell_date.isoformat() if sell_date is not None else None,
                market=signal["market"],
                symbol=signal["symbol"],
                display_symbol=signal["display_symbol"],
                score=signal["score"],
                candidate_type=signal["candidate_type"],
                buy_price=buy_price,
                sell_price=sell_price,
                gross_return=None,
                net_return=None,
                direction=direction,
                skipped_reason=skipped_reason,
                exit_reason=exit_reason,
            ),
            None,
        )

    gross_return = buy_price / sell_price - 1.0 if direction == "SHORT" else sell_price / buy_price - 1.0
    net_return = gross_return - 2.0 * (params.fee_rate + params.slippage)
    return (
        BacktestTrade(
            signal_date=signal["signal_date"].isoformat(),
            buy_date=buy_date.isoformat(),
            sell_date=sell_date.isoformat(),
            market=signal["market"],
            symbol=signal["symbol"],
            display_symbol=signal["display_symbol"],
            score=signal["score"],
            candidate_type=signal["candidate_type"],
            buy_price=buy_price,
            sell_price=sell_price,
            gross_return=round(gross_return, 6),
            net_return=round(net_return, 6),
            direction=direction,
            exit_reason=exit_reason,
        ),
        net_return,
    )


def _match_signal_prices(con, signals: list[dict[str, Any]], hold_days: int) -> dict[tuple[str, int], dict[str, Any]]:
    if not signals:
        return {}
    _register_tmp_signals(con, signals)
    adj = _adj_daily_expressions(con)
    con.execute(
        f"""
        CREATE OR REPLACE TEMP TABLE tmp_backtest_price_matches AS
        WITH adj_base AS (
            SELECT
                market,
                symbol,
                trade_date,
                adj_open,
                {adj["high"]} AS adj_high,
                {adj["low"]} AS adj_low,
                {adj["close"]} AS adj_close,
                {adj["volume"]} AS volume,
                row_number() OVER (PARTITION BY market, symbol ORDER BY trade_date) AS rn,
                lag({adj["close"]}) OVER (PARTITION BY market, symbol ORDER BY trade_date) AS prev_close,
                avg({adj["close"]}) OVER (PARTITION BY market, symbol ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
                avg(({adj["high"]} - {adj["low"]})) OVER (PARTITION BY market, symbol ORDER BY trade_date ROWS BETWEEN 13 PRECEDING AND CURRENT ROW) AS atr14
            FROM adj_daily
        ),
        adj_enriched AS (
            SELECT
                *,
                {adj["limit_up"]} AS is_limit_up,
                {adj["limit_down"]} AS is_limit_down,
                {adj["suspended"]} AS is_suspended
            FROM adj_base
        ),
        buy_match AS (
            SELECT
                s.signal_date,
                s.signal_rank,
                s.market,
                s.symbol,
                s.display_symbol,
                s.score,
                s.candidate_type,
                s.direction,
                b.trade_date AS buy_date,
                b.adj_open AS buy_price,
                b.rn AS buy_rn,
                b.is_limit_up AS buy_is_limit_up,
                b.is_limit_down AS buy_is_limit_down,
                b.is_suspended AS buy_is_suspended
            FROM tmp_backtest_signals AS s
            LEFT JOIN LATERAL (
                SELECT trade_date, adj_open, rn, is_limit_up, is_limit_down, is_suspended
                FROM adj_enriched AS b
                WHERE b.market = s.market
                    AND b.symbol = s.symbol
                    AND b.trade_date > s.signal_date
                ORDER BY b.trade_date
                LIMIT 1
            ) AS b ON TRUE
        ),
        sell_candidates AS (
            SELECT
                b.*,
                sell.trade_date AS sell_date,
                sell.adj_open AS sell_price,
                sell.adj_close AS sell_close,
                sell.ma20 AS sell_ma20,
                sell.atr14 AS sell_atr14,
                sell.rn AS sell_rn,
                max(sell.adj_high) OVER (
                    PARTITION BY b.signal_date, b.signal_rank
                    ORDER BY sell.rn
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS highest_high_since_buy
            FROM buy_match AS b
            LEFT JOIN adj_enriched AS sell
                ON sell.market = b.market
                AND sell.symbol = b.symbol
                AND sell.rn > b.buy_rn
                AND sell.rn <= b.buy_rn + ?
                AND (
                    (b.direction = 'SHORT' AND sell.is_limit_up = FALSE AND sell.is_suspended = FALSE)
                    OR
                    (b.direction <> 'SHORT' AND sell.is_limit_down = FALSE AND sell.is_suspended = FALSE)
                )
        ),
        sell_triggers AS (
            SELECT
                *,
                CASE
                    WHEN sell_date IS NULL THEN NULL
                    WHEN direction <> 'SHORT' AND sell_ma20 IS NOT NULL AND sell_close < sell_ma20 THEN 'ma_breakdown'
                    WHEN direction <> 'SHORT' AND sell_atr14 IS NOT NULL AND sell_close <= highest_high_since_buy - 3.0 * sell_atr14 THEN 'atr_chandelier_stop'
                    WHEN sell_rn >= buy_rn + ? THEN 'max_holding_days'
                    ELSE NULL
                END AS exit_reason
            FROM sell_candidates
        ),
        sell_match AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY signal_date, signal_rank
                    ORDER BY sell_date
                ) AS sell_match_rank
            FROM sell_triggers
            WHERE exit_reason IS NOT NULL
        )
        SELECT
            signal_date,
            signal_rank,
            market,
            symbol,
            display_symbol,
            score,
            candidate_type,
            direction,
            buy_date,
            buy_price,
            buy_is_limit_up,
            buy_is_limit_down,
            buy_is_suspended,
            sell_date,
            sell_price,
            exit_reason
        FROM sell_match
        WHERE sell_match_rank = 1
        ORDER BY signal_date, signal_rank
        """,
        (hold_days, hold_days),
    )
    result = con.execute("SELECT * FROM tmp_backtest_price_matches")
    columns = [description[0] for description in result.description]
    rows = result.fetchall()
    return {
        (str(row_dict["signal_date"]), int(row_dict["signal_rank"])): row_dict
        for row_dict in (dict(zip(columns, row, strict=True)) for row in rows)
    }


def _register_tmp_signals(con, signals: list[dict[str, Any]]) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE tmp_backtest_signals (
            signal_date DATE,
            signal_rank INTEGER,
            market VARCHAR,
            symbol VARCHAR,
            display_symbol VARCHAR,
            score DOUBLE,
            candidate_type VARCHAR,
            direction VARCHAR
        )
        """
    )
    con.executemany(
        """
        INSERT INTO tmp_backtest_signals VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                signal["signal_date"],
                signal["signal_rank"],
                signal["market"],
                signal["symbol"],
                signal["display_symbol"],
                signal["score"],
                signal["candidate_type"],
                signal.get("direction") or "LONG",
            )
            for signal in signals
        ],
    )


def _match_signal_prices_with_loader(
    con,
    signal: dict[str, Any],
    trading_dates: list[date],
    buy_index: int,
    sell_index: int,
    price_loader_fn: PriceLoaderFn,
) -> dict[str, Any]:
    buy_quote = coerce_adj_open_price(
        price_loader_fn(con, signal["market"], signal["symbol"], trading_dates[buy_index])
    )
    direction = _normalize_direction(signal.get("direction"))
    if buy_quote is None:
        return {
            "buy_date": trading_dates[buy_index],
            "buy_price": None,
            "buy_is_limit_up": False,
            "buy_is_limit_down": False,
            "buy_is_suspended": False,
            "sell_date": trading_dates[sell_index],
            "sell_price": None,
            "exit_reason": None,
        }
    sell_quote = None
    actual_sell_date = None
    for index in range(sell_index, len(trading_dates)):
        quote = coerce_adj_open_price(
            price_loader_fn(con, signal["market"], signal["symbol"], trading_dates[index])
        )
        if quote is None:
            continue
        if direction == "SHORT":
            if quote.is_limit_up or quote.is_suspended:
                continue
        elif quote.is_limit_down or quote.is_suspended:
            continue
        sell_quote = quote
        actual_sell_date = trading_dates[index]
        break
    return {
        "buy_date": trading_dates[buy_index],
        "buy_price": buy_quote.price,
        "buy_is_limit_up": buy_quote.is_limit_up,
        "buy_is_limit_down": buy_quote.is_limit_down,
        "buy_is_suspended": buy_quote.is_suspended,
        "sell_date": actual_sell_date,
        "sell_price": sell_quote.price if sell_quote is not None else None,
        "exit_reason": "max_holding_days" if sell_quote is not None else None,
    }


def _adj_daily_expressions(con) -> dict[str, str]:
    columns = _table_column_names(con, "adj_daily")
    has_high = "adj_high" in columns
    has_low = "adj_low" in columns
    has_close = "adj_close" in columns
    has_volume = "volume" in columns
    return {
        "high": "adj_high" if has_high else "adj_open",
        "low": "adj_low" if has_low else "adj_open",
        "close": "adj_close" if has_close else "adj_open",
        "volume": "volume" if has_volume else "NULL::BIGINT",
        "limit_up": (
            "CASE WHEN prev_close IS NOT NULL AND adj_open = adj_high "
            "AND adj_close > prev_close * 1.04 THEN TRUE ELSE FALSE END"
            if has_high and has_close
            else "FALSE"
        ),
        "limit_down": (
            "CASE WHEN prev_close IS NOT NULL AND adj_open = adj_low "
            "AND adj_close < prev_close * 0.96 THEN TRUE ELSE FALSE END"
            if has_low and has_close
            else "FALSE"
        ),
        "suspended": "CASE WHEN volume = 0 THEN TRUE ELSE FALSE END" if has_volume else "FALSE",
    }


def _table_column_names(con, table: str) -> set[str]:
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    return {str(row[0]) for row in rows}


def _build_report(
    strategy_name: str,
    params: BacktestParams,
    trading_dates: list[date],
    periods: list[BacktestPeriod],
    trades: list[BacktestTrade],
    equity_curve: list[dict[str, Any]],
    empty_period_count: int,
    equity: float,
    *,
    base_equity: float = 1.0,
    benchmark: dict[str, Any] | None = None,
) -> BacktestReport:
    effective_periods = [period for period in periods if not period.empty]
    period_returns = [period.period_return for period in effective_periods]
    total_return = round(equity / base_equity - 1.0, 6) if base_equity > 0 else 0.0
    trade_returns = [trade.net_return for trade in trades if trade.net_return is not None]
    winsorized_total_return = _winsorized_compound_return(period_returns)
    benchmark = benchmark or {"status": "not_available", "name": "沪深300"}
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
        max_drawdown=max_drawdown([1.0] + [entry["equity"] / base_equity for entry in equity_curve]) if base_equity > 0 else 0.0,
        win_rate=win_rate,
        avg_period_return=round(mean(period_returns), 6) if period_returns else 0.0,
        best_period_return=round(max(period_returns), 6) if period_returns else 0.0,
        worst_period_return=round(min(period_returns), 6) if period_returns else 0.0,
        turnover=round(len(trade_returns) / len(effective_periods), 6) if effective_periods else 0.0,
        equity_curve=equity_curve,
        periods=[period.to_dict() for period in periods],
        trades=[trade.to_dict() for trade in trades],
        winsorized_total_return=winsorized_total_return,
        benchmark_name=benchmark.get("name"),
        benchmark_status=benchmark.get("status"),
        benchmark_return=benchmark.get("return"),
        alpha=(round(total_return - float(benchmark["return"]), 6) if benchmark.get("return") is not None else None),
        information_ratio=benchmark.get("information_ratio"),
    )



def _winsorized_compound_return(period_returns: list[float], *, trim_ratio: float = 0.01) -> float | None:
    values = [float(value) for value in period_returns if value is not None]
    if len(values) < 3:
        return None
    trim = int(len(values) * trim_ratio)
    if trim <= 0 and len(values) >= 20:
        trim = 1
    if trim > 0 and len(values) > trim * 2:
        values = sorted(values)[trim:-trim]
    equity = 1.0
    for value in values:
        equity *= 1.0 + value
    return round(equity - 1.0, 6)


def _benchmark_summary(con, trading_dates: list[date], periods_input: list[dict[str, Any]]) -> dict[str, Any]:
    if not trading_dates:
        return {"name": "沪深300", "status": "not_available"}
    candidates = [("sh", "000300", "沪深300"), ("sz", "399300", "沪深300"), ("sh", "000985", "万得全A"), ("sh", "000001", "上证指数")]
    columns = _table_column_names(con, "adj_daily")
    close_col = "adj_close" if "adj_close" in columns else "adj_open"
    start = trading_dates[0]
    end = trading_dates[-1]
    for market, symbol, name in candidates:
        try:
            rows = con.execute(
                f"""
                SELECT trade_date, {close_col} AS close_price
                FROM adj_daily
                WHERE market = ? AND symbol = ? AND trade_date BETWEEN ? AND ?
                ORDER BY trade_date
                """,
                (market, symbol, start, end),
            ).fetchall()
        except Exception:
            rows = []
        if len(rows) < 2:
            continue
        first = float(rows[0][1])
        last = float(rows[-1][1])
        if first <= 0:
            continue
        bench_return = round(last / first - 1.0, 6)
        price_by_date = {str(row[0]): float(row[1]) for row in rows if row[1] is not None}
        excess: list[float] = []
        for period in periods_input:
            if period.get("buy_date") is None or period.get("sell_date") is None:
                continue
            buy = price_by_date.get(str(period.get("buy_date")))
            sell = price_by_date.get(str(period.get("sell_date")))
            if buy and sell and buy > 0:
                # period return is unavailable here; IR is computed later only when there are enough benchmark observations.
                excess.append(sell / buy - 1.0)
        ir = None
        if len(excess) > 1:
            # Without period returns in this scope, expose benchmark availability and leave conservative IR unavailable.
            ir = None
        return {"name": name, "status": "available", "return": bench_return, "information_ratio": ir}
    return {"name": "沪深300", "status": "not_available"}


def _signal_key(signal: dict[str, Any]) -> tuple[str, int]:
    return (signal["signal_date"].isoformat(), int(signal["signal_rank"]))


def _date_or_none(value: Any) -> date | None:
    return value if isinstance(value, date) else None


def _collect_portfolio_signals(
    config: AppConfig,
    params: BacktestParams,
    trading_dates: list[date],
    strategy_runner_fn: StrategyRunnerFn,
) -> dict[date, list[dict[str, Any]]]:
    signal_map: dict[date, list[dict[str, Any]]] = {}
    for signal_date in trading_dates[:-1]:
        report = strategy_runner_fn(config, _strategy_params(params, signal_date))
        signal_map[signal_date] = [
            {
                "signal_date": signal_date,
                "signal_rank": signal_rank,
                "market": str(candidate.get("market") or "").lower(),
                "symbol": str(candidate.get("symbol") or ""),
                "display_symbol": str(candidate.get("display_symbol") or f"{candidate.get('symbol')}.{str(candidate.get('market') or '').upper()}"),
                "score": _float(candidate.get("score")),
                "candidate_type": (
                    str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None
                ),
                "direction": _normalize_direction(candidate.get("direction")),
            }
            for signal_rank, candidate in enumerate(report.picks[: params.top])
            if str(candidate.get("symbol") or "")
        ]
    return signal_map


def _load_daily_bar(
    con,
    loader_fn: DailyPriceLoaderFn,
    cache: dict[tuple[str, str, date], AdjDailyPrice | None],
    market: str,
    symbol: str,
    trade_date: date,
) -> AdjDailyPrice | None:
    key = (market, symbol, trade_date)
    if key not in cache:
        cache[key] = coerce_adj_daily_price(loader_fn(con, market, symbol, trade_date))
    return cache[key]


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_direction(value: Any) -> str:
    text = str(value or "LONG").upper()
    return "SHORT" if text == "SHORT" else "LONG"
