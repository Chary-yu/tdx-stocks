from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketRegimeResult:
    status: str
    action: str
    reason: str
    required_missing: list[str]
    cash_floor: float | None = None
    position_limit: float | None = None
    sector_neutral_required: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "reason": self.reason,
            "required_missing": list(self.required_missing),
            "cash_floor": self.cash_floor,
            "position_limit": self.position_limit,
            "sector_neutral_required": self.sector_neutral_required,
        }


def evaluate_market_regime(config: dict[str, Any] | None = None) -> MarketRegimeResult:
    cfg = config or {}
    enabled = bool(cfg.get("enabled", False))
    if not enabled:
        return MarketRegimeResult(status="neutral", action="allow_open", reason="macro_filter.disabled", required_missing=[])

    indicators = cfg.get("indicators") if isinstance(cfg.get("indicators"), dict) else {}
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    impact = cfg.get("impact") if isinstance(cfg.get("impact"), dict) else {}
    required = list(cfg.get("required") or ["market_breadth"])
    missing = [str(name) for name in required if indicators.get(str(name)) in (None, "")]
    if missing:
        fallback = str(cfg.get("missing_action") or "pause_open")
        return MarketRegimeResult(
            status="not_available",
            action=fallback,
            reason="required 指标缺失",
            required_missing=missing,
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
        )

    breadth = str(indicators.get("market_breadth") or "neutral").lower()
    status = "bull" if breadth == "bull" else ("bear" if breadth == "bear" else "neutral")
    if bool(rules.get("bull_trade_required", False)) and status != "bull":
        return MarketRegimeResult(
            status=status,
            action="pause_open",
            reason="bull_trade_required 未满足",
            required_missing=[],
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
        )

    bear_trade_allowed = bool(rules.get("bear_trade_allowed", False))
    if status == "bear" and not bear_trade_allowed:
        return MarketRegimeResult(
            status="bear",
            action="pause_open",
            reason="熊市且不允许开仓",
            required_missing=[],
            position_limit=float(impact.get("position_limit_bear")) if impact.get("position_limit_bear") is not None else None,
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
        )

    if status == "neutral":
        return MarketRegimeResult(
            status="neutral",
            action="reduce_position",
            reason="中性市场，降低仓位",
            required_missing=[],
            cash_floor=float(rules.get("neutral_cash_floor")) if rules.get("neutral_cash_floor") is not None else None,
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
        )
    if status == "bear":
        return MarketRegimeResult(
            status="bear",
            action="reduce_position",
            reason="熊市允许交易但收缩风险",
            required_missing=[],
            position_limit=float(impact.get("position_limit_bear")) if impact.get("position_limit_bear") is not None else None,
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
        )
    return MarketRegimeResult(status="bull", action="allow_open", reason="牛市可开仓", required_missing=[])
