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
        display_name="Low Vol Breakout",
        description="Generate a low-volatility breakout observation pool.",
        runner=run_low_vol_breakout_strategy,
        group="breakout",
        style="short_term",
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
        optional_fields=("vol_ratio_5_60", "price_vol_corr_20"),
        default_params=StrategyParams(),
        param_schema={},
        candidate_types=("breakout_watch",),
        risk_tags=("ret_5_strong", "rsi_high", "mild_volatility", "near_20d_high"),
        introduced_in="0.5.0",
    )
)
