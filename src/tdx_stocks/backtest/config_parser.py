from __future__ import annotations

import tomllib
from copy import deepcopy
from itertools import product
from pathlib import Path
from typing import Any


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def inject_nested_value(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = [part.strip() for part in dotted_key.split(".") if part.strip()]
    if not parts:
        raise ValueError("batch_search key cannot be empty")

    cursor: dict[str, Any] = target
    for part in parts[:-1]:
        next_value = cursor.get(part)
        if not isinstance(next_value, dict):
            next_value = {}
            cursor[part] = next_value
        cursor = next_value
    cursor[parts[-1]] = value


def expand_batch_configs(data: dict[str, Any], *, batch: bool = False) -> list[dict[str, Any]]:
    base_config = deepcopy(data)
    batch_search = base_config.get("batch_search")
    if not batch or not isinstance(batch_search, dict) or not batch_search.get("enabled", False):
        return [_strip_batch_search(base_config)]

    dimensions: list[tuple[str, list[Any]]] = []
    for key, value in batch_search.items():
        if key == "enabled":
            continue
        if isinstance(value, list):
            values = list(value)
        else:
            values = [value]
        if not values:
            raise ValueError(f"batch_search.{key} must not be empty")
        dimensions.append((key, values))

    if not dimensions:
        return [_strip_batch_search(base_config)]

    keys = [key for key, _values in dimensions]
    value_sets = [values for _key, values in dimensions]
    configs: list[dict[str, Any]] = []
    for combination in product(*value_sets):
        config = deepcopy(base_config)
        for key, value in zip(keys, combination, strict=True):
            inject_nested_value(config, key, value)
        config.pop("batch_search", None)
        configs.append(config)
    return configs


def load_backtest_configs(path: Path, *, batch: bool = False) -> list[dict[str, Any]]:
    data = load_toml(path)
    return expand_batch_configs(data, batch=batch)


def _strip_batch_search(data: dict[str, Any]) -> dict[str, Any]:
    config = deepcopy(data)
    config.pop("batch_search", None)
    return config
