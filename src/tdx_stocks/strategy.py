from __future__ import annotations

from .config import AppConfig
from .query import open_query_context
from .strategies.base import StrategyParams, StrategyReport
from .strategies.presets.trend_strength import run_trend_strength_strategy as _run_trend_strength_strategy


def run_trend_strength_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    return _run_trend_strength_strategy(
        config,
        params,
        open_query_context_fn=open_query_context,
    )
