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
        display_name="Relative Strength",
        description="Generate a relative-strength observation pool.",
        runner=run_relative_strength_strategy,
        group="momentum",
        style="medium_term",
        aliases=("relative_strength",),
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
        candidate_types=("strong_trend",),
        risk_tags=("risk_factor_missing", "ret_5_strong", "mild_volatility"),
        introduced_in="0.5.0",
    )
)
