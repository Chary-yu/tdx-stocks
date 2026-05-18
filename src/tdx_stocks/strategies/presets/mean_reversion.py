from __future__ import annotations

from dataclasses import dataclass

from ...config import AppConfig
from ...pipeline import parse_iso_date
from ..base import StrategyParams, StrategyReport
from ..registry import StrategyDefinition, register_strategy
from .trend_strength import run_trend_strength_strategy


@dataclass(frozen=True)
class MeanReversionParams(StrategyParams):
    rsi_threshold: float = 25.0

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["rsi_threshold"] = self.rsi_threshold
        return payload


def _build_params(args) -> MeanReversionParams:
    return MeanReversionParams(
        limit=args.limit,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
        market=args.market,
        candidate_type=args.candidate_type,
        include_excluded=args.include_excluded,
        show_excluded_limit=args.show_excluded_limit,
        explain_symbol=args.explain_symbol,
        as_of=parse_iso_date(args.as_of),
        rsi_threshold=float(getattr(args, "rsi_threshold", 25.0)),
    )


def run_mean_reversion_strategy(config: AppConfig, params: MeanReversionParams) -> StrategyReport:
    return run_trend_strength_strategy(
        config,
        params,
        strategy_name="mean-reversion",
        preset_candidate_type="oversold_rebound",
    )


def _add_arguments(parser) -> None:
    parser.add_argument("--rsi-threshold", type=float, default=25.0)


register_strategy(
    StrategyDefinition(
        name="mean-reversion",
        description="Generate an oversold rebound observation pool.",
        runner=run_mean_reversion_strategy,
        aliases=("mean_reversion",),
        required_fields=(
            "adj_close",
            "ma20",
            "ma60",
            "ret_5",
            "ret_20",
            "amount_ma20",
            "rsi_14",
            "std_pctchg_20",
            "bb_lower_20",
        ),
        default_params=MeanReversionParams(),
        add_arguments=_add_arguments,
        params_builder=_build_params,
    )
)
