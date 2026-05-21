
from __future__ import annotations

from collections.abc import Callable

from .types import Event

Subscriber = Callable[[Event], None]
_SUBSCRIBERS: list[Subscriber] = []
_EVENTS: list[Event] = []


def subscribe(handler: Subscriber) -> None:
    if handler not in _SUBSCRIBERS:
        _SUBSCRIBERS.append(handler)


def publish(event: Event) -> None:
    _EVENTS.append(event)
    for handler in list(_SUBSCRIBERS):
        handler(event)


def has_subscribers() -> bool:
    return bool(_SUBSCRIBERS)


def get_events(*, clear: bool = False) -> list[Event]:
    events = list(_EVENTS)
    if clear:
        _EVENTS.clear()
    return events


def clear_events() -> None:
    _EVENTS.clear()
