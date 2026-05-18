from __future__ import annotations

import argparse
import hashlib
import importlib.util
import sys
from dataclasses import dataclass, field
from collections.abc import Callable
from pathlib import Path

from ..config import AppConfig
from .base import StrategyParams, StrategyReport


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    description: str
    runner: Callable[[AppConfig, StrategyParams], StrategyReport]
    display_name: str = ""
    group: str = "other"
    style: str = "other"
    required_fields: tuple[str, ...] = ()
    optional_fields: tuple[str, ...] = ()
    default_params: StrategyParams = field(default_factory=StrategyParams)
    param_schema: dict[str, object] = field(default_factory=dict)
    candidate_types: tuple[str, ...] = ()
    risk_tags: tuple[str, ...] = ()
    introduced_in: str = "0.5.0"
    aliases: tuple[str, ...] = ()
    add_arguments: Callable[[argparse.ArgumentParser], None] | None = None
    params_builder: Callable[[argparse.Namespace], StrategyParams] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "group": self.group,
            "style": self.style,
            "required_fields": list(self.required_fields),
            "optional_fields": list(self.optional_fields),
            "default_params": self.default_params.to_dict(),
            "param_schema": self.param_schema,
            "candidate_types": list(self.candidate_types),
            "risk_tags": list(self.risk_tags),
            "introduced_in": self.introduced_in,
            "aliases": list(self.aliases),
        }

    def research_capabilities(self) -> tuple[str, ...]:
        return (
            "run",
            "compare",
            "consensus",
            "backtest",
            "tune",
            "analyze_forward_returns",
            "analyze_risk_tags",
        )


_REGISTRY: dict[str, StrategyDefinition] = {}
_LOADED_PLUGIN_PATHS: set[Path] = set()


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


def load_plugins(plugin_dir: Path) -> None:
    plugin_root = plugin_dir.expanduser()
    if not plugin_root.exists():
        return
    if not plugin_root.is_dir():
        raise NotADirectoryError(f"strategy plugin path is not a directory: {plugin_root}")

    for plugin_path in sorted(plugin_root.glob("*.py")):
        if not plugin_path.is_file():
            continue
        resolved_path = plugin_path.resolve()
        if resolved_path in _LOADED_PLUGIN_PATHS:
            continue
        module_name = _plugin_module_name(resolved_path)
        spec = importlib.util.spec_from_file_location(module_name, resolved_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load strategy plugin: {resolved_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        _LOADED_PLUGIN_PATHS.add(resolved_path)


def _plugin_module_name(path: Path) -> str:
    digest = hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()[:12]
    return f"tdx_stocks_strategy_plugin_{path.stem}_{digest}"


from .presets import low_vol_breakout as _low_vol_breakout  # noqa: E402,F401
from .presets import ma_pullback as _ma_pullback  # noqa: E402,F401
from .presets import mean_reversion as _mean_reversion  # noqa: E402,F401
from .presets import multi_factor as _multi_factor  # noqa: E402,F401
from .presets import relative_strength as _relative_strength  # noqa: E402,F401
from .presets import smart_money as _smart_money  # noqa: E402,F401
from .presets import trend_strength as _trend_strength  # noqa: E402,F401
from .presets import volume_breakout as _volume_breakout  # noqa: E402,F401
from . import pairs as _pairs  # noqa: E402,F401
