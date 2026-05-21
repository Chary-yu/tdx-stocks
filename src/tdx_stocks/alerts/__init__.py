
from __future__ import annotations

from ..events.types import Event
from .engine import AlertDecision, emit_console_alerts, evaluate_alerts, validate_alert_config


def should_alert(event: Event) -> bool:
    return any(item.triggered for item in evaluate_alerts([event], {"channels": ["console"]}))


__all__ = ["AlertDecision", "emit_console_alerts", "evaluate_alerts", "should_alert", "validate_alert_config"]
