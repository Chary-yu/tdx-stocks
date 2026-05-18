from __future__ import annotations

from ...config import AppConfig
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def run_smart_money_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="smart-money",
        preset_candidate_type="smart_money",
        source_table="factor_full",
    )


register_strategy(
    StrategyDefinition(
        name="smart-money",
        display_name="Smart Money",
        description="Generate a smart-money observation pool.",
        runner=run_smart_money_strategy,
        group="momentum",
        style="swing",
        aliases=("smart_money",),
        required_fields=(
            "adj_close",
            "ma20",
            "ma60",
            "ret_5",
            "ret_20",
            "amount_ma20",
            "rsi_14",
            "atr_pct_14",
            "vol_ratio_5_60",
            "price_vol_corr_20",
            "atr_pct_14_pct_rank",
        ),
        optional_fields=("vol_ratio_5_60", "bb_lower_20"),
        default_params=StrategyParams(),
        param_schema={},
        candidate_types=("smart_money",),
        risk_tags=("risk_factor_missing", "mild_volatility", "volume_expansion"),
        introduced_in="0.5.0",
    )
)
