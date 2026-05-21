from __future__ import annotations

from typing import Any


def compute_liquidity_fields(*, adv: float | None, target_amount: float | None, max_liquidation_days: float) -> dict[str, Any]:
    if adv is None or adv <= 0 or target_amount is None:
        return {
            "adv_20d": adv,
            "target_amount": target_amount,
            "target_amount_to_adv": None,
            "expected_liquidation_days": None,
            "liquidity_ok": False,
        }
    ratio = target_amount / adv
    expected_days = ratio
    return {
        "adv_20d": round(adv, 2),
        "target_amount": round(target_amount, 2),
        "target_amount_to_adv": round(ratio, 6),
        "expected_liquidation_days": round(expected_days, 4),
        "liquidity_ok": expected_days <= max_liquidation_days,
    }
