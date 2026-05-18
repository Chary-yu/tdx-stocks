from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, date
from typing import Any

from .. import __version__ as APP_VERSION


@dataclass(frozen=True)
class Holding:
    market: str
    symbol: str
    weight: float
    score: float | None = None
    source_strategy: str | None = None
    source_strategies: list[str] = field(default_factory=list)
    candidate_type: str | None = None
    risk_flags: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    reason: str | None = None
    risk_score: float | None = None
    factor_values: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RiskCheckResult:
    passed: bool
    violations: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioReport:
    schema_version: str
    app_version: str
    generated_at: str
    as_of: str
    data_run_id: str | None
    source: str
    params: dict[str, Any]
    holdings: list[dict[str, Any]]
    summary: dict[str, Any]
    risk_summary: dict[str, Any]
    diagnostics: dict[str, Any]

    @classmethod
    def build(
        cls,
        *,
        generated_at: datetime,
        as_of: date | str,
        data_run_id: str | None,
        source: str,
        params: dict[str, Any],
        holdings: list[Holding],
        summary: dict[str, Any],
        risk_summary: dict[str, Any],
        diagnostics: dict[str, Any],
        schema_version: str = "portfolio-report-v1",
    ) -> "PortfolioReport":
        return cls(
            schema_version=schema_version,
            app_version=APP_VERSION,
            generated_at=generated_at.isoformat(timespec="seconds"),
            as_of=as_of.isoformat() if isinstance(as_of, date) else str(as_of),
            data_run_id=data_run_id,
            source=source,
            params=params,
            holdings=[holding.to_dict() for holding in holdings],
            summary=summary,
            risk_summary=risk_summary,
            diagnostics=diagnostics,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RebalanceAction:
    market: str
    symbol: str
    current_weight: float
    target_weight: float
    delta_weight: float
    action: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RebalancePlan:
    schema_version: str
    as_of: str
    current_holdings: list[dict[str, Any]]
    target_holdings: list[dict[str, Any]]
    buy: list[dict[str, Any]]
    sell: list[dict[str, Any]]
    hold: list[dict[str, Any]]
    increase: list[dict[str, Any]]
    reduce: list[dict[str, Any]]
    weight_changes: list[dict[str, Any]]
    turnover: float
    risk_summary: dict[str, Any]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioBacktestReport:
    schema_version: str
    app_version: str
    generated_at: str
    as_of: str
    data_run_id: str | None
    source: str
    params: dict[str, Any]
    total_return: float
    annual_return: float
    max_drawdown: float
    volatility: float
    win_rate: float
    turnover: float
    avg_holdings: float
    max_single_weight: float
    market_exposure: dict[str, float]
    equity_curve: list[dict[str, Any]]
    periods: list[dict[str, Any]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
