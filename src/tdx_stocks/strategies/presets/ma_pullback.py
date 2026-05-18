from __future__ import annotations

from ...config import AppConfig
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def run_ma_pullback_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="ma-pullback",
        preset_candidate_type="pullback_watch",
    )


register_strategy(
    StrategyDefinition(
        name="ma-pullback",
        description="Generate a moving-average pullback observation pool.",
        runner=run_ma_pullback_strategy,
        aliases=("ma_pullback",),
        default_params=StrategyParams(),
    )
)
