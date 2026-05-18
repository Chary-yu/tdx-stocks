from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import date
from itertools import product
from statistics import mean, median
from typing import Any

from .. import __version__ as APP_VERSION
from ..config import AppConfig
from ..query import open_query_context
from ..strategies.base import StrategyParams
from ..strategies.registry import get_strategy
from .engine import run_backtest
from .metrics import max_drawdown
from .models import BacktestParams
from .prices import load_adj_open_price, load_trading_dates


@dataclass(frozen=True)
class ResearchRow:
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestCompareRow(ResearchRow):
    strategy_name: str
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    avg_period_return: float
    turnover: float
    period_count: int
    empty_period_count: int


@dataclass(frozen=True)
class ParameterScanRow(ResearchRow):
    min_score: float
    top: int
    hold_days: int
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    turnover: float
    period_count: int
    empty_period_count: int
    research_score: float


@dataclass(frozen=True)
class ForwardReturnRow(ResearchRow):
    horizon: int
    sample_count: int
    mean_return: float
    median_return: float
    win_rate: float
    p25: float
    p75: float
    best: float
    worst: float


@dataclass(frozen=True)
class RiskTagRow(ResearchRow):
    risk_tag: str
    horizon: int
    sample_count: int
    mean_forward_return: float
    win_rate: float
    worst_return: float
    max_drawdown_after_entry: float


@dataclass(frozen=True)
class ConsensusTrade(ResearchRow):
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    market: str
    symbol: str
    display_symbol: str
    score: float | None
    hit_count: int
    candidate_types: list[str]
    strategies: list[str]
    tags: list[str]
    risk_flags: list[str]
    reasons: list[str]
    buy_price: float | None
    sell_price: float | None
    gross_return: float | None
    net_return: float | None
    skipped_reason: str | None = None


def compare_backtests(
    config: AppConfig,
    strategy_names: list[str],
    params: BacktestParams,
) -> dict[str, Any]:
    rows: list[BacktestCompareRow] = []
    for strategy_name in strategy_names:
        report = run_backtest(config, strategy_name, params)
        rows.append(
            BacktestCompareRow(
                strategy_name=strategy_name,
                total_return=report.total_return,
                annual_return=report.annual_return,
                max_drawdown=report.max_drawdown,
                win_rate=report.win_rate,
                avg_period_return=report.avg_period_return,
                turnover=report.turnover,
                period_count=report.period_count,
                empty_period_count=report.empty_period_count,
            )
        )
    rows = sorted(rows, key=lambda row: row.annual_return, reverse=True)
    return {
        "schema_version": "backtest-compare-v1",
        "app_version": APP_VERSION,
        "strategy_names": strategy_names,
        "params": params.to_dict(),
        "rows": [row.to_dict() for row in rows],
    }


def tune_strategy_parameters(
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    *,
    min_scores: list[float],
    tops: list[int],
    hold_days: list[int],
) -> dict[str, Any]:
    rows: list[ParameterScanRow] = []
    for min_score, top, hold_days_value in product(min_scores, tops, hold_days):
        scan_params = BacktestParams(
            from_date=params.from_date,
            to_date=params.to_date,
            top=top,
            hold_days=hold_days_value,
            fee_rate=params.fee_rate,
            slippage=params.slippage,
            market=params.market,
            candidate_type=params.candidate_type,
            min_score=min_score,
            min_amount_ma20=params.min_amount_ma20,
        )
        report = run_backtest(config, strategy_name, scan_params)
        research_score = round(
            report.annual_return
            - abs(report.max_drawdown)
            + report.win_rate * 0.1,
            6,
        )
        rows.append(
            ParameterScanRow(
                min_score=min_score,
                top=top,
                hold_days=hold_days_value,
                total_return=report.total_return,
                annual_return=report.annual_return,
                max_drawdown=report.max_drawdown,
                win_rate=report.win_rate,
                turnover=report.turnover,
                period_count=report.period_count,
                empty_period_count=report.empty_period_count,
                research_score=research_score,
            )
        )
    rows = sorted(rows, key=lambda row: row.research_score, reverse=True)
    return {
        "schema_version": "parameter-scan-v1",
        "app_version": APP_VERSION,
        "strategy_name": strategy_name,
        "params": params.to_dict(),
        "rows": [row.to_dict() for row in rows],
    }


def analyze_forward_returns(
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    horizons: list[int],
) -> dict[str, Any]:
    ctx = open_query_context(config)
    try:
        rows = _analyze_forward_returns(ctx.con, config, strategy_name, params, horizons)
    finally:
        ctx.close()
    return {
        "schema_version": "forward-returns-v1",
        "app_version": APP_VERSION,
        "strategy_name": strategy_name,
        "params": params.to_dict(),
        "rows": [row.to_dict() for row in rows],
    }


def analyze_risk_tags(
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    horizons: list[int],
) -> dict[str, Any]:
    ctx = open_query_context(config)
    try:
        rows = _analyze_risk_tags(ctx.con, config, strategy_name, params, horizons)
    finally:
        ctx.close()
    return {
        "schema_version": "risk-tags-v1",
        "app_version": APP_VERSION,
        "strategy_name": strategy_name,
        "params": params.to_dict(),
        "rows": [row.to_dict() for row in rows],
    }


def backtest_consensus(
    config: AppConfig,
    strategy_names: list[str],
    params: BacktestParams,
    *,
    min_hit: int = 2,
) -> dict[str, Any]:
    ctx = open_query_context(config)
    try:
        trading_dates = load_trading_dates(ctx.con, params.from_date, params.to_date, params.market)
        if not trading_dates:
            raise ValueError("no trading dates found for the selected backtest range")
        periods: list[dict[str, Any]] = []
        trades: list[ConsensusTrade] = []
        equity_curve: list[dict[str, Any]] = []
        equity = 1.0
        empty_period_count = 0
        for index, signal_date in enumerate(trading_dates):
            buy_index = index + 1
            sell_index = buy_index + params.hold_days
            if buy_index >= len(trading_dates) or sell_index >= len(trading_dates):
                periods.append(
                    {
                        "signal_date": signal_date.isoformat(),
                        "buy_date": None,
                        "sell_date": None,
                        "trade_count": 0,
                        "empty": True,
                        "period_return": 0.0,
                        "equity": equity,
                        "skipped_reasons": ["insufficient_future_dates"],
                    }
                )
                empty_period_count += 1
                continue
            buy_date = trading_dates[buy_index]
            sell_date = trading_dates[sell_index]
            candidates = _collect_consensus_candidates(
                config,
                strategy_names,
                signal_date,
                params,
            )
            selected = [item for item in candidates if item["hit_count"] >= min_hit]
            selected = sorted(
                selected,
                key=lambda item: (
                    -item["hit_count"],
                    -item["avg_score"],
                    -item["max_score"],
                    len(item["risk_flags"]),
                    item["symbol"],
                ),
            )[: params.top]
            period_returns: list[float] = []
            skipped_reasons: list[str] = []
            for item in selected:
                buy_price = load_adj_open_price(ctx.con, item["market"], item["symbol"], buy_date)
                sell_price = load_adj_open_price(ctx.con, item["market"], item["symbol"], sell_date)
                if buy_price is None or sell_price is None:
                    skipped_reasons.append(f"missing_price:{item['market']}:{item['symbol']}")
                    trades.append(
                        ConsensusTrade(
                            signal_date=signal_date.isoformat(),
                            buy_date=buy_date.isoformat(),
                            sell_date=sell_date.isoformat(),
                            market=item["market"],
                            symbol=item["symbol"],
                            display_symbol=f"{item['symbol']}.{item['market'].upper()}",
                            score=item["avg_score"],
                            hit_count=item["hit_count"],
                            candidate_types=item["candidate_types"],
                            strategies=item["strategies"],
                            tags=item["tags"],
                            risk_flags=item["risk_flags"],
                            reasons=item["reasons"],
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
                period_returns.append(net_return)
                trades.append(
                    ConsensusTrade(
                        signal_date=signal_date.isoformat(),
                        buy_date=buy_date.isoformat(),
                        sell_date=sell_date.isoformat(),
                        market=item["market"],
                        symbol=item["symbol"],
                        display_symbol=f"{item['symbol']}.{item['market'].upper()}",
                        score=item["avg_score"],
                        hit_count=item["hit_count"],
                        candidate_types=item["candidate_types"],
                        strategies=item["strategies"],
                        tags=item["tags"],
                        risk_flags=item["risk_flags"],
                        reasons=item["reasons"],
                        buy_price=buy_price,
                        sell_price=sell_price,
                        gross_return=round(gross_return, 6),
                        net_return=round(net_return, 6),
                    )
                )
            if not period_returns:
                empty_period_count += 1
                period_return = 0.0
            else:
                period_return = round(mean(period_returns), 6)
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
                {
                    "signal_date": signal_date.isoformat(),
                    "buy_date": buy_date.isoformat(),
                    "sell_date": sell_date.isoformat(),
                    "trade_count": len(period_returns),
                    "empty": not period_returns,
                    "period_return": period_return,
                    "equity": equity,
                    "skipped_reasons": skipped_reasons,
                }
            )
        period_returns = [period["period_return"] for period in periods]
        trade_returns = [trade.net_return for trade in trades if trade.net_return is not None]
        total_return = round(equity - 1.0, 6)
        start = trading_dates[0]
        end = trading_dates[-1]
        days = (end - start).days if end and start else 0
        return {
            "schema_version": "consensus-backtest-v1",
            "app_version": APP_VERSION,
            "strategy_name": "consensus",
            "strategy_names": strategy_names,
            "params": params.to_dict() | {"min_hit": min_hit},
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "trade_count": len(trade_returns),
            "period_count": len(periods),
            "empty_period_count": empty_period_count,
            "total_return": total_return,
            "annual_return": round((1.0 + total_return) ** (365.0 / days) - 1.0, 6) if days > 0 else total_return,
            "max_drawdown": max_drawdown([entry["equity"] for entry in equity_curve]),
            "win_rate": round(sum(1 for value in trade_returns if value > 0) / len(trade_returns), 6) if trade_returns else 0.0,
            "avg_period_return": round(mean(period_returns), 6) if period_returns else 0.0,
            "best_period_return": round(max(period_returns), 6) if period_returns else 0.0,
            "worst_period_return": round(min(period_returns), 6) if period_returns else 0.0,
            "turnover": round(len(trade_returns) / len(periods), 6) if periods else 0.0,
            "equity_curve": equity_curve,
            "periods": periods,
            "trades": [trade.to_dict() for trade in trades],
        }
    finally:
        ctx.close()


def _analyze_forward_returns(
    con,
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    horizons: list[int],
) -> list[ForwardReturnRow]:
    signal_dates = load_trading_dates(con, params.from_date, params.to_date, params.market)
    buckets: dict[int, list[float]] = {horizon: [] for horizon in horizons}
    market_dates_cache: dict[str, list[date]] = {}
    market_index_cache: dict[str, dict[date, int]] = {}
    runner = get_strategy(strategy_name).runner
    for signal_date in signal_dates:
        report = runner(
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
        for candidate in report.picks[: params.top]:
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            if not market or not symbol:
                continue
            market_dates = market_dates_cache.setdefault(
                market,
                load_trading_dates(con, signal_dates[0], signal_dates[-1], market),
            )
            market_index = market_index_cache.setdefault(market, {item: idx for idx, item in enumerate(market_dates)})
            signal_index = market_index.get(signal_date)
            if signal_index is None:
                continue
            for horizon in horizons:
                sample = _forward_sample(con, market_dates, signal_index, market, symbol, horizon)
                if sample is not None:
                    buckets[horizon].append(sample["return"])
    rows: list[ForwardReturnRow] = []
    for horizon in sorted(horizons):
        values = buckets.get(horizon) or []
        rows.append(
            ForwardReturnRow(
                horizon=horizon,
                sample_count=len(values),
                mean_return=round(mean(values), 6) if values else 0.0,
                median_return=round(median(values), 6) if values else 0.0,
                win_rate=round(sum(1 for value in values if value > 0) / len(values), 6) if values else 0.0,
                p25=_percentile(values, 0.25),
                p75=_percentile(values, 0.75),
                best=round(max(values), 6) if values else 0.0,
                worst=round(min(values), 6) if values else 0.0,
            )
        )
    return rows


def _analyze_risk_tags(
    con,
    config: AppConfig,
    strategy_name: str,
    params: BacktestParams,
    horizons: list[int],
) -> list[RiskTagRow]:
    signal_dates = load_trading_dates(con, params.from_date, params.to_date, params.market)
    buckets: dict[tuple[str, int], list[dict[str, float]]] = defaultdict(list)
    market_dates_cache: dict[str, list[date]] = {}
    market_index_cache: dict[str, dict[date, int]] = {}
    runner = get_strategy(strategy_name).runner
    for signal_date in signal_dates:
        report = runner(
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
        for candidate in report.picks[: params.top]:
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            if not market or not symbol:
                continue
            market_dates = market_dates_cache.setdefault(
                market,
                load_trading_dates(con, signal_dates[0], signal_dates[-1], market),
            )
            market_index = market_index_cache.setdefault(market, {item: idx for idx, item in enumerate(market_dates)})
            signal_index = market_index.get(signal_date)
            if signal_index is None:
                continue
            risk_flags = [str(item) for item in candidate.get("risk_flags") or []]
            for horizon in horizons:
                sample = _forward_sample(con, market_dates, signal_index, market, symbol, horizon)
                if sample is None:
                    continue
                for risk_flag in risk_flags:
                    buckets[(risk_flag, horizon)].append(sample)
    rows: list[RiskTagRow] = []
    for (risk_tag, horizon), samples in sorted(buckets.items()):
        returns = [sample["return"] for sample in samples]
        drawdowns = [sample["drawdown"] for sample in samples]
        rows.append(
            RiskTagRow(
                risk_tag=risk_tag,
                horizon=horizon,
                sample_count=len(samples),
                mean_forward_return=round(mean(returns), 6) if returns else 0.0,
                win_rate=round(sum(1 for value in returns if value > 0) / len(returns), 6) if returns else 0.0,
                worst_return=round(min(returns), 6) if returns else 0.0,
                max_drawdown_after_entry=round(min(drawdowns), 6) if drawdowns else 0.0,
            )
        )
    rows.sort(key=lambda row: (row.risk_tag, row.horizon))
    return rows


def _collect_consensus_candidates(
    config: AppConfig,
    strategy_names: list[str],
    signal_date: date,
    params: BacktestParams,
) -> list[dict[str, Any]]:
    bucket: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy_name in strategy_names:
        report = get_strategy(strategy_name).runner(
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
        for candidate in report.picks[: params.top]:
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            if not market or not symbol:
                continue
            key = (market, symbol)
            item = bucket.setdefault(
                key,
                {
                    "market": market,
                    "symbol": symbol,
                    "strategies": set(),
                    "scores": [],
                    "candidate_types": set(),
                    "tags": set(),
                    "risk_flags": set(),
                    "reasons": set(),
                },
            )
            item["strategies"].add(strategy_name)
            if candidate.get("score") is not None:
                item["scores"].append(float(candidate["score"]))
            if candidate.get("candidate_type"):
                item["candidate_types"].add(str(candidate["candidate_type"]))
            for field in ("tags", "risk_flags", "reasons"):
                for value in candidate.get(field) or []:
                    item[field].add(str(value))
    rows: list[dict[str, Any]] = []
    for item in bucket.values():
        scores = item["scores"]
        rows.append(
            {
                "market": item["market"],
                "symbol": item["symbol"],
                "hit_count": len(item["strategies"]),
                "strategies": sorted(item["strategies"]),
                "avg_score": round(mean(scores), 2) if scores else 0.0,
                "max_score": round(max(scores), 2) if scores else 0.0,
                "candidate_types": sorted(item["candidate_types"]),
                "tags": sorted(item["tags"]),
                "risk_flags": sorted(item["risk_flags"]),
                "reasons": sorted(item["reasons"]),
            }
        )
    return rows


def _forward_sample(
    con,
    market_dates: list[date],
    signal_index: int,
    market: str,
    symbol: str,
    horizon: int,
) -> dict[str, float] | None:
    buy_index = signal_index + 1
    sell_index = buy_index + horizon
    if buy_index >= len(market_dates) or sell_index >= len(market_dates):
        return None
    buy_date = market_dates[buy_index]
    sell_date = market_dates[sell_index]
    prices: list[float] = []
    for index in range(buy_index, sell_index + 1):
        price = load_adj_open_price(con, market, symbol, market_dates[index])
        if price is None:
            return None
        prices.append(price)
    if len(prices) < 2 or prices[0] <= 0:
        return None
    return {
        "return": prices[-1] / prices[0] - 1.0,
        "drawdown": max_drawdown([price / prices[0] for price in prices]),
        "buy_date": buy_date,
        "sell_date": sell_date,
    }


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return round(ordered[index], 6)
