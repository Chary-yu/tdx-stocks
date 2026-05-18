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
        display_name="MA Pullback",
        description="Generate a moving-average pullback observation pool.",
        runner=run_ma_pullback_strategy,
        group="pullback",
        style="swing",
        aliases=("ma_pullback",),
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
        candidate_types=("pullback_watch",),
        risk_tags=("risk_factor_missing", "mild_volatility", "ret_5_strong"),
        introduced_in="0.5.0",
    )
)
