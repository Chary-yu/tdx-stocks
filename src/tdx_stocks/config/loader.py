from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .bundle import ConfigBundle
from .normalize import AUX_CONFIG_ALIASES, SECTION_EXTRACTORS, extract_aux_section_payload

RUNNABLE_TASKS = ("daily", "signal", "portfolio", "rebalance", "backtest", "grid_search")
AUXILIARY_SECTIONS = tuple(AUX_CONFIG_ALIASES.keys())

TASK_PRESETS: dict[str, Path] = {
    "daily": Path("experiments/daily.toml"),
    "signal": Path("experiments/signal.toml"),
    "portfolio": Path("experiments/portfolio.toml"),
    "rebalance": Path("experiments/rebalance.toml"),
    "backtest": Path("experiments/backtest.toml"),
    "grid": Path("experiments/grid_search.toml"),
    "grid_search": Path("experiments/grid_search.toml"),
}


def resolve_task_config_path(value: str | Path) -> Path:
    path = Path(value)
    if path.suffix.lower() == ".toml" or path.exists():
        return path.resolve() if path.exists() else path
    preset = TASK_PRESETS.get(str(value))
    if preset is not None:
        root = _discover_project_root(_safe_cwd())
        return (root / preset).resolve()
    return path


def load_config_bundle(path: Path) -> ConfigBundle:
    task_path = path.resolve()
    task_config = _read_toml(task_path)
    root = _project_root(task_path)
    auxiliary_configs: dict[str, dict[str, Any]] = {}
    auxiliary_sources: dict[str, Path] = {}
    warnings: list[str] = []
    for section in AUXILIARY_SECTIONS:
        source = _find_auxiliary_config(root, section)
        if source is None:
            continue
        try:
            loaded = _read_toml(source)
            auxiliary_configs[section] = extract_aux_section_payload(
                section,
                loaded,
                extractor_key=SECTION_EXTRACTORS.get(section, section),
            )
            auxiliary_sources[section] = source
        except (OSError, tomllib.TOMLDecodeError) as exc:
            warnings.append(f"failed to load {section} from {source}: {exc}")
    merged = dict(task_config)
    for section in AUXILIARY_SECTIONS:
        data = auxiliary_configs.get(section)
        if not isinstance(data, Mapping):
            continue
        current = merged.get(section)
        if isinstance(current, Mapping):
            merged[section] = _deep_merge(dict(current), data)
        else:
            merged[section] = dict(data)
    return ConfigBundle(
        task_path=task_path,
        task_config=task_config,
        merged_config=merged,
        auxiliary_configs=auxiliary_configs,
        auxiliary_sources=auxiliary_sources,
        auxiliary_extractors=dict(SECTION_EXTRACTORS),
        warnings=warnings,
    )


def _read_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _project_root(task_path: Path) -> Path:
    for candidate in (task_path.parent, *task_path.parents):
        if (candidate / "experiments").exists():
            return candidate
    return task_path.parent


def _discover_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "experiments").exists():
            return candidate
    return start


def _safe_cwd() -> Path:
    try:
        return Path.cwd()
    except FileNotFoundError:
        return Path(os.environ.get("PWD", ".")).resolve()


def _find_auxiliary_config(root: Path, section: str) -> Path | None:
    names = AUX_CONFIG_ALIASES.get(section, [f"{section}.toml"])
    candidates: list[Path] = []
    for name in names:
        candidates.extend(
            [
                root / "experiments" / name,
                root / "configs" / name,
                root / "config" / name,
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _deep_merge(left: dict[str, Any], right: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(left)
    for key, value in right.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(dict(merged[key]), value)
        else:
            merged[key] = value
    return merged
