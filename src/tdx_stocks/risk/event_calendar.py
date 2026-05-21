from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any


@dataclass(frozen=True)
class EventDecision:
    action: str
    reason: str
    event_type: str
    event_date: str | None = None
    weight_multiplier: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "event_type": self.event_type,
            "event_date": self.event_date,
            "weight_multiplier": self.weight_multiplier,
        }


def apply_event_calendar(candidate: dict[str, Any], calendar_cfg: dict[str, Any] | None = None) -> EventDecision:
    cfg = calendar_cfg or {}
    if not bool(cfg.get("enabled", True)):
        return EventDecision(action="ignore", reason="事件日历未启用", event_type="")

    event_type = str(candidate.get("event_type") or candidate.get("event") or "")
    event_date = _parse_date(candidate.get("event_date") or candidate.get("calendar_date"))
    as_of = _parse_date(candidate.get("as_of") or candidate.get("signal_date") or candidate.get("trade_date"))
    if not event_type:
        return EventDecision(action="ignore", reason="无事件", event_type="")

    sources = cfg.get("sources") if isinstance(cfg.get("sources"), dict) else {}
    if event_type in sources and not bool(sources.get(event_type)):
        return EventDecision(action="ignore", reason=f"事件类型未启用: {event_type}", event_type=event_type, event_date=_fmt(event_date))

    windows = cfg.get("windows") if isinstance(cfg.get("windows"), dict) else {}
    window = windows.get(event_type) if isinstance(windows.get(event_type), list) else None
    in_window = True
    if event_date is not None and as_of is not None and isinstance(window, list) and len(window) >= 2:
        start = event_date + timedelta(days=int(window[0]))
        end = event_date + timedelta(days=int(window[1]))
        in_window = start <= as_of <= end
    if not in_window:
        return EventDecision(action="ignore", reason=f"不在事件窗口: {event_type}", event_type=event_type, event_date=_fmt(event_date))

    action_cfg = cfg.get("action") if isinstance(cfg.get("action"), dict) else {}
    action = str(action_cfg.get("on_conflict") or cfg.get("default_action") or "postpone")
    weight_multiplier = None
    if action == "reduce_weight":
        weight_multiplier = float(action_cfg.get("reduce_weight_factor") or 0.5)
    return EventDecision(
        action=action,
        reason=f"命中事件窗口: {event_type}",
        event_type=event_type,
        event_date=_fmt(event_date),
        weight_multiplier=weight_multiplier,
    )


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _fmt(value: date | None) -> str | None:
    return value.isoformat() if value else None
