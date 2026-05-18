from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from typing import Any, Sequence

from ..strategies.base import MultiFactorParams, ScoreWeights, StrategyParams as RuntimeStrategyParams
from ..strategies.registry import get_strategy
from .engine import run_backtest
from .models import BacktestConfig, BacktestReport, StrategyParams


def run_single(config_dict: dict[str, Any]) -> BacktestReport:
    config = BacktestConfig.from_dict(config_dict)
    if config.engine is None:
        raise ValueError("backtest.engine section is required")

    app_config = config.to_app_config()
    params = config.to_backtest_params()
    strategy_runner_fn = _build_strategy_runner(config.strategy_name, config.strategy)
    return run_backtest(app_config, config.strategy_name, params, strategy_runner_fn=strategy_runner_fn)


def run_batch(configs: Sequence[dict[str, Any]], *, max_workers: int | None = None) -> list[BacktestReport]:
    if not configs:
        return []
    if len(configs) == 1:
        return [run_single(configs[0])]

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        return list(executor.map(run_single, configs))


def _build_strategy_runner(strategy_name: str, configured_strategy: StrategyParams):
    definition = get_strategy(strategy_name)
    strategy_runner = definition.runner

    def _runner(app_config, runtime_params):
        merged_params = _merge_strategy_params(runtime_params, configured_strategy, strategy_name)
        return strategy_runner(app_config, merged_params)

    return _runner


def _merge_strategy_params(
    runtime_params: RuntimeStrategyParams,
    configured_strategy: StrategyParams,
    strategy_name: str,
) -> RuntimeStrategyParams:
    base_kwargs: dict[str, Any] = {
        "limit": configured_strategy.limit if configured_strategy.limit is not None else runtime_params.limit,
        "min_score": configured_strategy.min_score if configured_strategy.min_score is not None else runtime_params.min_score,
        "min_amount_ma20": (
            configured_strategy.min_amount_ma20
            if configured_strategy.min_amount_ma20 is not None
            else runtime_params.min_amount_ma20
        ),
        "market": configured_strategy.market if configured_strategy.market is not None else runtime_params.market,
        "candidate_type": (
            configured_strategy.candidate_type
            if configured_strategy.candidate_type is not None
            else runtime_params.candidate_type
        ),
        "include_excluded": configured_strategy.include_excluded or runtime_params.include_excluded,
        "show_excluded_limit": (
            configured_strategy.show_excluded_limit
            if configured_strategy.show_excluded_limit is not None
            else runtime_params.show_excluded_limit
        ),
        "explain_symbol": configured_strategy.explain_symbol or runtime_params.explain_symbol,
        "as_of": configured_strategy.as_of or runtime_params.as_of,
    }
    if strategy_name == "multi-factor":
        weights_data = configured_strategy.factors.get("weights")
        if isinstance(weights_data, dict):
            weights = ScoreWeights(
                momentum=float(weights_data.get("momentum", 0.4)),
                volatility=float(weights_data.get("volatility", -0.3)),
                liquidity=float(weights_data.get("liquidity", 0.3)),
                relative_strength=float(weights_data.get("relative_strength", 0.2)),
                trend=float(weights_data.get("trend", 0.1)),
            )
            return MultiFactorParams(**base_kwargs, weights=weights)

    return RuntimeStrategyParams(**base_kwargs)
