from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

DEFAULT_MARKETS = ("sh", "sz")
DEFAULT_LIMIT = 20
DEFAULT_MIN_SCORE = 60.0
DEFAULT_MIN_AMOUNT_MA20 = 150_000_000.0
DEFAULT_SHOW_EXCLUDED_LIMIT = 20

GLOBAL_REQUIRED_FIELDS = ("adj_close", "ma20", "ma60", "ret_5", "ret_20", "amount_ma20")
BREAKOUT_REQUIRED_FIELDS = ("pos_20", "dd_20", "vol_ratio_20")
PULLBACK_REQUIRED_FIELDS = ("dd_20", "atr_pct_14")

CANDIDATE_TYPE_ORDER = (
    "breakout_watch",
    "strong_trend",
    "pullback_watch",
    "oversold_rebound",
    "smart_money",
    "pair_short",
    "pair_long",
)
HARD_REASON_ORDER = (
    "missing_required_factor",
    "insufficient_liquidity",
    "overheated_ret_5",
    "extreme_rsi",
    "excessive_volatility",
)
TAG_ORDER = (
    "breakout_watch",
    "low_volatility",
    "trend_strong",
    "pullback_watch",
    "oversold_rebound",
    "near_20d_high",
    "volume_expansion",
    "volume_breakout",
    "relative_strength",
    "active_amount",
    "ma_bullish",
    "smart_money",
    "price_volume_alignment",
)
RISK_FLAG_ORDER = (
    "ret_5_strong",
    "rsi_high",
    "mild_volatility",
    "near_20d_high",
    "risk_factor_missing",
)


@dataclass(frozen=True)
class StrategyParams:
    limit: int = DEFAULT_LIMIT
    min_score: float = DEFAULT_MIN_SCORE
    min_amount_ma20: float = DEFAULT_MIN_AMOUNT_MA20
    market: str | None = None
    candidate_type: str | None = None
    include_excluded: bool = False
    show_excluded_limit: int = DEFAULT_SHOW_EXCLUDED_LIMIT
    explain_symbol: str | None = None
    as_of: date | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "limit": self.limit,
            "min_score": self.min_score,
            "min_amount_ma20": self.min_amount_ma20,
            "market": self.market,
            "candidate_type": self.candidate_type,
            "include_excluded": self.include_excluded,
            "show_excluded_limit": self.show_excluded_limit,
            "explain_symbol": self.explain_symbol,
            "as_of": self.as_of.isoformat() if self.as_of else None,
        }


@dataclass(frozen=True)
class ScoreWeights:
    momentum: float = 0.4
    volatility: float = -0.3
    liquidity: float = 0.3
    relative_strength: float = 0.2
    trend: float = 0.1

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class MultiFactorParams(StrategyParams):
    weights: ScoreWeights = field(default_factory=ScoreWeights)

    def to_dict(self) -> dict[str, Any]:
        payload = super().to_dict()
        payload["weights"] = self.weights.to_dict()
        return payload


@dataclass(frozen=True)
class StrategyReport:
    summary: dict[str, object]
    picks: list[dict[str, object]]
    excluded: list[dict[str, object]]
    explain: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "picks": self.picks,
            "excluded": self.excluded,
            "explain": self.explain,
        }
