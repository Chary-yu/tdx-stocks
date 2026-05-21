from __future__ import annotations

from typing import Any


def split_orders(action: dict[str, Any], *, method: str = "TWAP", slices: int = 4) -> list[dict[str, Any]]:
    qty = float(action.get("delta_weight") if action.get("delta_weight") is not None else action.get("weight_delta") or 0.0)
    if slices <= 1 or qty == 0:
        return [{**action, "slice_no": 1, "slice_weight_delta": qty, "method": method}]
    per = qty / slices
    return [{**action, "slice_no": i + 1, "slice_weight_delta": per, "method": method} for i in range(slices)]
