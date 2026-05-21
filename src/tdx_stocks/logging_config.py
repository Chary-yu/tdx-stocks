from __future__ import annotations

from .alerts import should_alert
from .events.bus import subscribe
from .events.types import Event


def configure_event_logging() -> None:
    def _handler(event: Event) -> None:
        _ = should_alert(event)
        # 保持轻量：当前版本仅确保事件被统一消费，不在此处做 IO。
        return

    subscribe(_handler)
