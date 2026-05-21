from __future__ import annotations

from collections.abc import Callable

from .types import Event

Subscriber = Callable[[Event], None]
_SUBSCRIBERS: list[Subscriber] = []


def subscribe(handler: Subscriber) -> None:
    _SUBSCRIBERS.append(handler)


def publish(event: Event) -> None:
    for handler in list(_SUBSCRIBERS):
        handler(event)


def has_subscribers() -> bool:
    return bool(_SUBSCRIBERS)
