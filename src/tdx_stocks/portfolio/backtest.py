from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from statistics import mean, pstdev
from typing import Any

from .. import __version__ as APP_VERSION
from ..config import AppConfig
from ..exit_codes import NoDataError
from ..query import open_query_context
from ..backtest.metrics import annualize_return, max_drawdown
from ..backtest.prices import load_adj_daily_price, load_trading_dates
from .builder import build_portfolio
from .models import PortfolioBacktestReport
from .rebalance import build_rebalance_plan


@dataclass(frozen=True)
class PortfolioBacktestContext:
    con: Any
    manifest: dict[str, Any]

    def close(self) -> None:
        self.con.close()


def run_portfolio_backtest(
    config: AppConfig,
    *,
    source: str = "consensus",
    strategy: str | None = None,
    from_date: date,
    to_date: date,
    top: int = 20,
    weighting: str = "equal",
    rebalance_days: int = 5,
    max_weight: float = 0.10,
    min_weight: float = 0.0,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    market: str | None = None,
) -> PortfolioBacktestReport:
    ctx = open_query_context(config)
    try:
        trading_dates = load_trading_dates(ctx.con, from_date, to_date, market)
        if len(trading_dates) < 2:
            raise NoDataError("no trading dates found for the selected portfolio backtest range")

        equity = 1.0
        equity_curve: list[dict[str, Any]] = []
        periods: list[dict[str, Any]] = []
        period_returns: list[float] = []
        turnovers: list[float] = []
        holdings_counts: list[int] = []
        max_single_weights: list[float] = []
        latest_market_exposure: dict[str, float] = {}
        previous_holdings: list[Any] = []

        rebalance_indices = list(range(0, len(trading_dates) - 1, max(1, rebalance_days)))
        for signal_index in rebalance_indices:
            buy_index = signal_index + 1
            sell_index = min(signal_index + 1 + max(1, rebalance_days), len(trading_dates) - 1)
            signal_date = trading_dates[signal_index]
            buy_date = trading_dates[buy_index]
            sell_date = trading_dates[sell_index]

            report = build_portfolio(
                config,
                source=source,
                strategy=strategy,
                top=top,
                weighting=weighting,
                max_weight=max_weight,
                min_weight=min_weight,
                market=market,
                as_of=signal_date,
            )
            holdings = [
                row for row in report.holdings
                if float(row.get("weight") or 0.0) > 0
            ]
            current_holdings = [_holding_from_dict(row) for row in holdings]
            holdings_counts.append(len(holdings))
            if holdings:
                max_single_weights.append(max(float(row.get("weight") or 0.0) for row in holdings))
            buy_prices = {}
            sell_prices = {}
            for row in holdings:
                market_code = str(row.get("market") or "")
                symbol = str(row.get("symbol") or "")
                buy_bar = load_adj_daily_price(ctx.con, market_code, symbol, buy_date)
                sell_bar = load_adj_daily_price(ctx.con, market_code, symbol, sell_date)
                buy_prices[(market_code, symbol)] = buy_bar.open_price if buy_bar is not None else None
                sell_prices[(market_code, symbol)] = sell_bar.open_price if sell_bar is not None else None

            period_return = 0.0
            missing_prices = 0
            for row in holdings:
                market_code = str(row.get("market") or "")
                symbol = str(row.get("symbol") or "")
                buy_price = buy_prices.get((market_code, symbol))
                sell_price = sell_prices.get((market_code, symbol))
                weight = float(row.get("weight") or 0.0)
                if buy_price is None or sell_price is None or buy_price <= 0:
                    missing_prices += 1
                    continue
                gross = sell_price / buy_price - 1.0
                net = gross - 2.0 * ((fee_bps + slippage_bps) / 10_000.0)
                period_return += weight * net

            equity *= 1.0 + period_return
            period_returns.append(period_return)
            rebalance_plan = build_rebalance_plan(
                previous_holdings,
                current_holdings,
                as_of=signal_date.isoformat(),
                min_trade_weight=0.0,
                max_turnover=None,
            )
            turnover = rebalance_plan.turnover
            turnovers.append(turnover)
            latest_market_exposure = dict(report.risk_summary.get("summary", {}).get("market_exposure") or {})
            periods.append(
                {
                    "signal_date": signal_date.isoformat(),
                    "buy_date": buy_date.isoformat(),
                    "sell_date": sell_date.isoformat(),
                    "holdings": len(holdings),
                    "period_return": round(period_return, 6),
                    "equity": round(equity, 6),
                    "turnover": turnover,
                    "missing_prices": missing_prices,
                    "risk_summary": report.risk_summary,
                    "rebalance_plan": rebalance_plan.to_dict(),
                }
            )
            equity_curve.append(
                {
                    "signal_date": signal_date.isoformat(),
                    "buy_date": buy_date.isoformat(),
                    "sell_date": sell_date.isoformat(),
                    "equity": round(equity, 6),
                }
            )
            previous_holdings = current_holdings

        total_return = round(equity - 1.0, 6)
        period_days = (trading_dates[-1] - trading_dates[0]).days or 1
        win_rate = round(sum(1 for value in period_returns if value > 0) / len(period_returns), 6) if period_returns else 0.0
        volatility = round(pstdev(period_returns) * (252 ** 0.5), 6) if len(period_returns) > 1 else 0.0
        return PortfolioBacktestReport(
            schema_version="portfolio-backtest-v1",
            app_version=APP_VERSION,
            generated_at=date.today().isoformat(),
            as_of=to_date.isoformat(),
            data_run_id=str(ctx.manifest.get("run_id") or None),
            source=source,
            params={
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "top": top,
                "weighting": weighting,
                "rebalance_days": rebalance_days,
                "max_weight": max_weight,
                "min_weight": min_weight,
                "fee_bps": fee_bps,
                "slippage_bps": slippage_bps,
                "market": market,
                "strategy": strategy,
            },
            total_return=total_return,
            annual_return=annualize_return(total_return, period_days),
            max_drawdown=max_drawdown([entry["equity"] for entry in equity_curve]) if equity_curve else 0.0,
            volatility=volatility,
            win_rate=win_rate,
            turnover=round(mean(turnovers), 6) if turnovers else 0.0,
            avg_holdings=round(mean(holdings_counts), 6) if holdings_counts else 0.0,
            max_single_weight=round(max(max_single_weights), 6) if max_single_weights else 0.0,
            market_exposure={market_name: round(float(weight), 6) for market_name, weight in latest_market_exposure.items()},
            equity_curve=equity_curve,
            periods=periods,
            diagnostics={
                "rebalance_days": rebalance_days,
                "period_count": len(periods),
                "empty_period_count": sum(1 for value in period_returns if value == 0),
            },
        )
    finally:
        ctx.close()
def _holding_from_dict(row: dict[str, Any]):
    from .models import Holding

    return Holding(
        market=str(row.get("market") or ""),
        symbol=str(row.get("symbol") or ""),
        weight=float(row.get("weight") or 0.0),
        score=float(row.get("score") or 0.0) if row.get("score") is not None else None,
        source_strategy=str(row.get("source_strategy") or ""),
        source_strategies=[str(item) for item in row.get("source_strategies") or []],
        candidate_type=str(row.get("candidate_type") or "") or None,
        risk_flags=[str(item) for item in row.get("risk_flags") or []],
        tags=[str(item) for item in row.get("tags") or []],
        reason=str(row.get("reason") or ""),
        risk_score=float(row.get("risk_score")) if row.get("risk_score") is not None else None,
        factor_values=dict(row.get("factor_values") or {}),
    )
