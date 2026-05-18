from __future__ import annotations

from ...config import AppConfig
from ...pipeline import parse_iso_date
from ..base import MultiFactorParams, ScoreWeights, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


def _build_params(args) -> MultiFactorParams:
    return MultiFactorParams(
        limit=args.limit,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
        market=args.market,
        candidate_type=args.candidate_type,
        include_excluded=args.include_excluded,
        show_excluded_limit=args.show_excluded_limit,
        explain_symbol=args.explain_symbol,
        as_of=parse_iso_date(args.as_of),
        weights=ScoreWeights(
            momentum=float(getattr(args, "weight_mom", 0.4)),
            volatility=float(getattr(args, "weight_vol", -0.3)),
            liquidity=float(getattr(args, "weight_liq", 0.3)),
            relative_strength=float(getattr(args, "weight_rs", 0.2)),
            trend=float(getattr(args, "weight_trend", 0.1)),
        ),
    )


def _add_arguments(parser) -> None:
    parser.add_argument("--weight-mom", type=float, default=0.4)
    parser.add_argument("--weight-vol", type=float, default=-0.3)
    parser.add_argument("--weight-liq", type=float, default=0.3)
    parser.add_argument("--weight-rs", type=float, default=0.2)
    parser.add_argument("--weight-trend", type=float, default=0.1)


def run_multi_factor_strategy(config: AppConfig, params: MultiFactorParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="multi-factor",
        source_table="factor_full",
    )


register_strategy(
    StrategyDefinition(
        name="multi-factor",
        display_name="Multi Factor",
        description="Generate a configurable multi-factor observation pool.",
        runner=run_multi_factor_strategy,
        group="momentum",
        style="medium_term",
        aliases=("multi_factor",),
        required_fields=(
            "rs_score",
            "pct_rank_ret_20",
            "pct_rank_ret_60",
            "vol_20_pct_rank",
            "amount_ma20_pct_rank",
            "atr_pct_14_pct_rank",
            "ma_cross_20_60",
        ),
        optional_fields=("price_vol_corr_20", "bb_lower_20"),
        default_params=MultiFactorParams(),
        param_schema={
            "weight_mom": {"type": "float", "description": "Momentum factor weight."},
            "weight_vol": {"type": "float", "description": "Volatility factor weight."},
            "weight_liq": {"type": "float", "description": "Liquidity factor weight."},
            "weight_rs": {"type": "float", "description": "Relative strength factor weight."},
            "weight_trend": {"type": "float", "description": "Trend factor weight."},
        },
        candidate_types=("strong_trend",),
        risk_tags=("risk_factor_missing", "mild_volatility", "ret_5_strong"),
        introduced_in="0.5.0",
        add_arguments=_add_arguments,
        params_builder=_build_params,
    )
)
