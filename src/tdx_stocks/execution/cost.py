from __future__ import annotations

from typing import Any


def estimate_impact_bps(order: dict[str, Any], *, base_bps: float = 8.0) -> float:
    ratio = float(order.get("target_amount_to_adv") or 0.0)
    adjust = float(order.get("impact_bps_adjustment") or 0.0)
    return round(base_bps * (1.0 + ratio * 2.0) + adjust, 4)
