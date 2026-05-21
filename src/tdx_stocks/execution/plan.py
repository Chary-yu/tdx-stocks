from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .cost import estimate_impact_bps
from .splitter import split_orders


@dataclass(frozen=True)
class ExecutionPlan:
    method: str
    duration_minutes: int
    limit_offset_bps: float
    timeout_to_market: bool
    orders: list[dict[str, Any]]
    estimated_impact_bps: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "duration_minutes": self.duration_minutes,
            "limit_offset_bps": self.limit_offset_bps,
            "timeout_to_market": self.timeout_to_market,
            "orders": self.orders,
            "estimated_impact_bps": self.estimated_impact_bps,
            "batch_execution_recommended": len(self.orders) > 1,
        }


def build_execution_plan(actions: list[dict[str, Any]], cfg: dict[str, Any] | None = None) -> ExecutionPlan:
    config = cfg or {}
    method = str(config.get("method") or "TWAP")
    duration = int(config.get("duration_minutes") or 60)
    offset = float(config.get("limit_offset_bps") or 5.0)
    timeout_to_market = bool(config.get("timeout_to_market", True))
    slices = int(config.get("slices") or (4 if method in {"TWAP", "PoV"} else 1))
    split: list[dict[str, Any]] = []
    impacts: list[float] = []
    for action in actions:
        parts = split_orders(action, method=method, slices=slices)
        split.extend(parts)
        impacts.extend(estimate_impact_bps(item) for item in parts)
    est = round(sum(impacts) / len(impacts), 4) if impacts else 0.0
    return ExecutionPlan(method=method, duration_minutes=duration, limit_offset_bps=offset, timeout_to_market=timeout_to_market, orders=split, estimated_impact_bps=est)
