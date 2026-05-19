from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import DailyConfig


@dataclass(frozen=True)
class DailyRunConfig:
    enabled_strategies: tuple[str, ...]
    strategy_limit: int
    strategy_min_score: float
    consensus_min_hit: int
    portfolio_top: int
    portfolio_weighting: str
    portfolio_max_weight: float
    exclude_risk_tags: tuple[str, ...]

    @classmethod
    def from_app_config(cls, config: Any) -> "DailyRunConfig":
        daily: DailyConfig = getattr(config, "daily")
        return cls(
            enabled_strategies=daily.enabled_strategies,
            strategy_limit=daily.strategy_limit,
            strategy_min_score=daily.strategy_min_score,
            consensus_min_hit=daily.consensus_min_hit,
            portfolio_top=daily.portfolio_top,
            portfolio_weighting=daily.portfolio_weighting,
            portfolio_max_weight=daily.portfolio_max_weight,
            exclude_risk_tags=daily.exclude_risk_tags,
        )
