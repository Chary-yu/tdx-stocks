from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketRegimeResult:
    status: str
    action: str
    reason: str
    required_missing: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "reason": self.reason,
            "required_missing": list(self.required_missing),
        }


def evaluate_market_regime(config: dict[str, Any] | None = None) -> MarketRegimeResult:
    cfg = config or {}
    required = list(cfg.get("required") or [])
    missing = [str(name) for name in required if not cfg.get(name)]
    if missing:
        fallback = str(cfg.get("missing_action") or "pause_open")
        return MarketRegimeResult(status="not_available", action=fallback, reason="required 指标缺失", required_missing=missing)

    status = str(cfg.get("status") or "neutral")
    bear_trade_allowed = bool(cfg.get("bear_trade_allowed", False))
    if status == "bear" and not bear_trade_allowed:
        return MarketRegimeResult(status="bear", action="pause_open", reason="熊市且不允许开仓", required_missing=[])

    action = str(cfg.get("action") or ("allow_open" if status in {"bull", "neutral"} else "reduce_position"))
    return MarketRegimeResult(status=status, action=action, reason=str(cfg.get("reason") or "ok"), required_missing=[])
