from __future__ import annotations

from ...config import AppConfig
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def run_low_vol_breakout_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="low-vol-breakout",
        preset_candidate_type="breakout_watch",
    )


register_strategy(
    StrategyDefinition(
        name="low-vol-breakout",
        description="Generate a low-volatility breakout observation pool.",
        runner=run_low_vol_breakout_strategy,
        aliases=("low_vol_breakout",),
        required_fields=(
            "adj_close",
            "ma20",
            "ma60",
            "ret_5",
            "ret_20",
            "ret_60",
            "amount_ma20",
            "pos_20",
            "pos_60",
            "dd_20",
            "vol_ratio_20",
            "rsi_14",
            "atr_pct_14",
            "vol_20",
            "vol_60",
            "high_20",
            "low_20",
        ),
        default_params=StrategyParams(),
    )
)
