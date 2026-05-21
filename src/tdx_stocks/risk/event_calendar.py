from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventDecision:
    action: str
    reason: str
    event_type: str

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reason": self.reason, "event_type": self.event_type}


def apply_event_calendar(candidate: dict[str, Any], calendar_cfg: dict[str, Any] | None = None) -> EventDecision:
    cfg = calendar_cfg or {}
    event_type = str(candidate.get("event_type") or "")
    if not event_type:
        return EventDecision(action="ignore", reason="无事件", event_type="")
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    action = str((rules.get(event_type) if isinstance(rules, dict) else None) or cfg.get("default_action") or "postpone")
    return EventDecision(action=action, reason=f"命中事件窗口: {event_type}", event_type=event_type)
