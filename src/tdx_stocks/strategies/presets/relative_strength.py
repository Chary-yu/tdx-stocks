from __future__ import annotations

from ...config import AppConfig
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def run_relative_strength_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="relative-strength",
        preset_candidate_type="strong_trend",
    )


register_strategy(
    StrategyDefinition(
        name="relative-strength",
        description="Generate a relative-strength observation pool.",
        runner=run_relative_strength_strategy,
        aliases=("relative_strength",),
        default_params=StrategyParams(),
    )
)
