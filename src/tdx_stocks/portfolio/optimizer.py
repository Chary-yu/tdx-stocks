from __future__ import annotations

from typing import Any

from .weights import build_portfolio_weights


def optimize_weights(
    candidates: list[dict[str, Any]],
    *,
    mode: str,
    max_weight: float,
    min_weight: float,
    capital: float,
    max_adv_participation: float,
    max_liquidation_days: float,
) -> tuple[list[float], dict[str, Any]]:
    normalized_mode = str(mode or "equal")
    diagnostics: dict[str, Any] = {"requested_weighting": normalized_mode, "effective_weighting": normalized_mode}
    if normalized_mode == "risk-parity":
        diagnostics["effective_weighting"] = "liquidity-risk"
        diagnostics["unsupported_feature"] = "risk-parity 当前暂未实现，已回退为 liquidity-risk"
        normalized_mode = "liquidity-risk"
    if normalized_mode == "signal-strength":
        normalized_mode = "signal-strength"
    if normalized_mode == "hybrid":
        normalized_mode = "hybrid"
    return build_portfolio_weights(
        candidates,
        normalized_mode,
        max_weight=max_weight,
        min_weight=min_weight,
        normalize=True,
        capital=capital,
        max_adv_participation=max_adv_participation,
        max_liquidation_days=max_liquidation_days,
    ), diagnostics
