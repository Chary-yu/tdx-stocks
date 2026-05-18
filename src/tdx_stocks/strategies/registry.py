from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable

from ..config import AppConfig
from .base import StrategyParams, StrategyReport


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    description: str
    runner: Callable[[AppConfig, StrategyParams], StrategyReport]
    aliases: tuple[str, ...] = ()
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    default_params: StrategyParams = field(default_factory=StrategyParams)


_REGISTRY: dict[str, StrategyDefinition] = {}


def register_strategy(definition: StrategyDefinition) -> None:
    _REGISTRY[definition.name] = definition
    for alias in definition.aliases:
        _REGISTRY[alias] = definition


def get_strategy(name: str) -> StrategyDefinition:
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"unknown strategy: {name}") from exc


def list_strategies() -> list[StrategyDefinition]:
    seen: set[str] = set()
    ordered: list[StrategyDefinition] = []
    for definition in _REGISTRY.values():
        if definition.name in seen:
            continue
        seen.add(definition.name)
        ordered.append(definition)
    return sorted(ordered, key=lambda item: item.name)


from .presets import low_vol_breakout as _low_vol_breakout  # noqa: E402,F401
from .presets import ma_pullback as _ma_pullback  # noqa: E402,F401
from .presets import relative_strength as _relative_strength  # noqa: E402,F401
from .presets import trend_strength as _trend_strength  # noqa: E402,F401
from .presets import volume_breakout as _volume_breakout  # noqa: E402,F401
