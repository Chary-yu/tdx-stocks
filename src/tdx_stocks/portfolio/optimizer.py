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
) -> list[float]:
    normalized_mode = str(mode or "equal")
    if normalized_mode == "risk-parity":
        raise NotImplementedError("risk-parity 暂未实现")
    if normalized_mode in {"hybrid", "signal-strength"}:
        normalized_mode = "liquidity-risk"
    return build_portfolio_weights(
        candidates,
        normalized_mode,
        max_weight=max_weight,
        min_weight=min_weight,
        normalize=True,
        capital=capital,
        max_adv_participation=max_adv_participation,
        max_liquidation_days=max_liquidation_days,
    )
