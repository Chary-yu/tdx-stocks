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
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else config
    split = execution.get("split") if isinstance(execution.get("split"), dict) else {}
    limit_order = execution.get("limit_order") if isinstance(execution.get("limit_order"), dict) else {}
    method_raw = str(split.get("method") or config.get("method") or "twap").lower()
    method = "PoV" if method_raw == "pov" else method_raw.upper()
    twap_cfg = split.get("twap") if isinstance(split.get("twap"), dict) else {}
    pov_cfg = split.get("pov") if isinstance(split.get("pov"), dict) else {}
    duration = int(twap_cfg.get("duration_minutes") or config.get("duration_minutes") or 60)
    offset = float(limit_order.get("offset_bps") if limit_order.get("offset_bps") is not None else config.get("limit_offset_bps", 5.0))
    timeout_to_market = bool(limit_order.get("timeout_to_market", config.get("timeout_to_market", True)))
    auto_slices = 4 if method in {"TWAP", "PoV"} else 1
    slices = int(twap_cfg.get("num_slices") or config.get("slices") or auto_slices)
    if method == "PoV" and slices <= 0:
        target_p = float(pov_cfg.get("target_participation") or 0.1)
        slices = 6 if target_p <= 0.1 else 4
    if slices <= 0:
        slices = auto_slices
    split: list[dict[str, Any]] = []
    impacts: list[float] = []
    piecewise = config.get("cost_model", {}).get("piecewise") if isinstance(config.get("cost_model"), dict) else None
    for action in actions:
        parts = split_orders(action, method=method, slices=slices)
        parts = _apply_piecewise_impact(parts, piecewise)
        split.extend(parts)
        impacts.extend(estimate_impact_bps(item) for item in parts)
    est = round(sum(impacts) / len(impacts), 4) if impacts else 0.0
    return ExecutionPlan(method=method, duration_minutes=duration, limit_offset_bps=offset, timeout_to_market=timeout_to_market, orders=split, estimated_impact_bps=est)


def _apply_piecewise_impact(parts: list[dict[str, Any]], piecewise: Any) -> list[dict[str, Any]]:
    if not isinstance(piecewise, dict):
        return parts
    adjusted: list[dict[str, Any]] = []
    for row in parts:
        ratio = float(row.get("target_amount_to_adv") or 0.0)
        tier = "low"
        if ratio >= 0.20:
            tier = "critical"
        elif ratio >= 0.10:
            tier = "high"
        elif ratio >= 0.05:
            tier = "medium"
        bump = piecewise.get(tier) if isinstance(piecewise.get(tier), dict) else {}
        extra_bps = float(bump.get("impact_bps") or 0.0)
        adjusted.append({**row, "impact_bps_adjustment": extra_bps})
    return adjusted
