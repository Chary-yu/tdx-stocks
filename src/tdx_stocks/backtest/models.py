from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any


@dataclass(frozen=True)
class BacktestParams:
    from_date: date
    to_date: date
    top: int = 20
    hold_days: int = 5
    fee_rate: float = 0.0
    slippage: float = 0.0
    market: str | None = None
    candidate_type: str | None = None
    min_score: float | None = None
    min_amount_ma20: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_date": self.from_date.isoformat(),
            "to_date": self.to_date.isoformat(),
            "top": self.top,
            "hold_days": self.hold_days,
            "fee_rate": self.fee_rate,
            "slippage": self.slippage,
            "market": self.market,
            "candidate_type": self.candidate_type,
            "min_score": self.min_score,
            "min_amount_ma20": self.min_amount_ma20,
        }


@dataclass(frozen=True)
class BacktestTrade:
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    market: str
    symbol: str
    display_symbol: str
    score: float | None
    candidate_type: str | None
    buy_price: float | None
    sell_price: float | None
    gross_return: float | None
    net_return: float | None
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestPeriod:
    signal_date: str
    buy_date: str | None
    sell_date: str | None
    trade_count: int
    empty: bool
    period_return: float
    equity: float
    skipped_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestReport:
    schema_version: str
    app_version: str
    strategy_name: str
    params: dict[str, Any]
    start_date: str
    end_date: str
    trade_count: int
    period_count: int
    empty_period_count: int
    total_return: float
    annual_return: float
    max_drawdown: float
    win_rate: float
    avg_period_return: float
    best_period_return: float
    worst_period_return: float
    turnover: float
    equity_curve: list[dict[str, Any]]
    periods: list[dict[str, Any]]
    trades: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
