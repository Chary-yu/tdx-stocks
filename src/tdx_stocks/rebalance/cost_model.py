
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TradeCostEstimate:
    tier: str
    trade_to_adv: float | None
    fee_bps: float
    slippage_bps: float
    impact_bps: float
    reject: bool
    reason: str

    @property
    def total_bps(self) -> float:
        return round(self.fee_bps + self.slippage_bps + self.impact_bps, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "cost_tier": self.tier,
            "trade_to_adv": self.trade_to_adv,
            "fee_bps": self.fee_bps,
            "slippage_bps": self.slippage_bps,
            "impact_bps": self.impact_bps,
            "estimated_cost_bps": self.total_bps,
            "reject": self.reject,
            "reason": self.reason,
        }


def estimate_trade_cost(delta_weight: float, *, capital: float, adv: float | None, model: dict[str, Any] | None = None) -> TradeCostEstimate:
    piecewise = model.get("piecewise") if isinstance(model, dict) and isinstance(model.get("piecewise"), dict) else {}
    trade_amount = abs(delta_weight) * max(capital, 0.0)
    ratio = None if not adv or adv <= 0 else trade_amount / adv
    tier = _tier(ratio)
    critical_cfg = piecewise.get("critical") if isinstance(piecewise.get("critical"), dict) else {}
    if ratio is None and critical_cfg:
        delta_threshold = _float(critical_cfg.get("delta_threshold"), 1.0)
        if abs(delta_weight) >= delta_threshold:
            tier = "critical"
    cfg = piecewise.get(tier) if isinstance(piecewise.get(tier), dict) else {}
    fee = _float(cfg.get("fee_bps"), 3.0)
    slip = _float(cfg.get("slippage_bps"), 5.0 if tier == "low" else 10.0 if tier == "medium" else 20.0 if tier == "high" else 50.0)
    impact = _float(cfg.get("impact_bps"), 0.0)
    reject = bool(cfg.get("reject", False)) and tier == "critical"
    if ratio is None:
        reason = "缺少 ADV，按权重变化阈值判断成本等级" if tier == "critical" else "缺少 ADV，无法精确估算冲击成本"
    else:
        reason = f"交易金额约占 ADV {ratio:.2%}，成本等级 {tier}"
    return TradeCostEstimate(tier, round(ratio, 6) if ratio is not None else None, fee, slip, impact, reject, reason)


def _tier(ratio: float | None) -> str:
    if ratio is None:
        return "unknown"
    if ratio >= 0.10:
        return "critical"
    if ratio >= 0.05:
        return "high"
    if ratio >= 0.01:
        return "medium"
    return "low"


def _float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
