from __future__ import annotations

import logging
from pathlib import Path

from .alerts import should_alert
from .events.bus import has_subscribers, subscribe
from .events.types import Event


def configure_event_logging() -> None:
    if has_subscribers():
        return
    log_root = Path("Database/logs")
    log_root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tdx_stocks.events")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_root / "risk_events.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)

    def _handler(event: Event) -> None:
        flagged = should_alert(event)
        logger.info("event=%s alert=%s payload=%s", event.event_type, flagged, event.payload)
        if flagged:
            print(f"[ALERT] {event.event_type}: {event.payload}")

    subscribe(_handler)
