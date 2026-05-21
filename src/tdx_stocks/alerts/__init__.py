from __future__ import annotations

from ..events.types import Event


def should_alert(event: Event) -> bool:
    return event.event_type in {
        "DATA_QUALITY_ERROR",
        "MACRO_PAUSE_OPEN",
        "TURNOVER_EXCEEDED",
        "REBALANCE_BUY_BLOCKED",
    }
