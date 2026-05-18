from __future__ import annotations

from ...config import AppConfig
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def run_volume_breakout_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="volume-breakout",
        preset_candidate_type="breakout_watch",
    )


register_strategy(
    StrategyDefinition(
        name="volume-breakout",
        description="Generate a volume breakout observation pool.",
        runner=run_volume_breakout_strategy,
        aliases=("volume_breakout",),
        default_params=StrategyParams(),
    )
)
