
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .alerts import emit_console_alerts, evaluate_alerts
from .events.bus import has_subscribers, subscribe
from .events.types import Event


def setup_from_config(logging_cfg: dict[str, Any] | None = None, alerts_cfg: dict[str, Any] | None = None, *, data_root: Path | None = None) -> None:
    cfg = logging_cfg or {}
    level = getattr(logging, str(cfg.get("level") or "INFO").upper(), logging.INFO)
    logging.getLogger().setLevel(level)
    configure_event_logging(logging_cfg=cfg, alerts_cfg=alerts_cfg or {}, data_root=data_root)


def configure_event_logging(logging_cfg: dict[str, Any] | None = None, alerts_cfg: dict[str, Any] | None = None, *, data_root: Path | None = None) -> None:
    if has_subscribers():
        return
    cfg = logging_cfg or {}
    root = data_root or Path("Database")
    log_root = root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("tdx_stocks.events")
    logger.setLevel(getattr(logging, str(cfg.get("level") or "INFO").upper(), logging.INFO))
    if not logger.handlers and bool(cfg.get("file_output", True)):
        file_path = Path(str(cfg.get("file_path") or log_root / "risk_events.log"))
        if not file_path.is_absolute():
            file_path = root.parent / file_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(file_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    console_output = bool(cfg.get("console_output", False))

    def _handler(event: Event) -> None:
        decisions = evaluate_alerts([event], alerts_cfg or {})
        logger.info("event=%s alerts=%s payload=%s", event.event_type, [d.to_dict() for d in decisions if d.triggered], event.payload)
        if console_output:
            print(f"[EVENT] {event.event_type}: {event.payload}")
        emit_console_alerts(decisions)

    subscribe(_handler)
