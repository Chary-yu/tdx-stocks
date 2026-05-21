from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


RISK_EVENTS = {
    "DATA_QUALITY_ERROR",
    "MACRO_PAUSE_OPEN",
    "RISK_INTERCEPTED",
    "STOP_LOSS_TRIGGERED",
    "TURNOVER_EXCEEDED",
    "SECTOR_CONCENTRATION_WARNING",
    "SIGNAL_DOWNGRADED_TO_WATCHLIST",
    "REBALANCE_BUY_BLOCKED",
}


@dataclass(frozen=True)
class Event:
    event_type: str
    payload: dict[str, Any]
    created_at: str

    @staticmethod
    def create(event_type: str, payload: dict[str, Any]) -> "Event":
        return Event(event_type=event_type, payload=payload, created_at=datetime.now().isoformat(timespec="seconds"))
