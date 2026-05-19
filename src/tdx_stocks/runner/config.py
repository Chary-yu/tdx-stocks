from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..backtest.models import BacktestConfig
from ..config import AppConfig
from .schema import validate_run_config


@dataclass(frozen=True)
class LoadedRunConfig:
    config: dict[str, Any]
    run_config: BacktestConfig | None
    app_config: AppConfig
    path: Path
    base_dir: Path
    task_type: str


def load_run_config(path: Path) -> LoadedRunConfig:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    task_type, _ = validate_run_config(data)
    base_dir = path.parent.resolve()
    normalized = _resolve_paths(data, base_dir=base_dir)
    backtest_config = BacktestConfig.from_dict(normalized)
    app_defaults = AppConfig()
    app_config = AppConfig(
        paths=backtest_config.paths,
        build=backtest_config.build,
        factors=backtest_config.factors,
        daily=app_defaults.daily,
    )
    return LoadedRunConfig(
        config=normalized,
        run_config=backtest_config if task_type in {"backtest", "grid_search"} else None,
        app_config=app_config,
        path=path,
        base_dir=base_dir,
        task_type=task_type,
    )


def _resolve_paths(data: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
    resolved = dict(data)
    for section_name in ("paths", "output", "rebalance"):
        section = resolved.get(section_name)
        if not isinstance(section, dict):
            continue
        new_section = dict(section)
        for key in ("tdx_vipdoc", "tdx_export", "data_root", "plugin_dir", "current_holdings", "dir"):
            if key in new_section and isinstance(new_section[key], str) and new_section[key]:
                new_section[key] = _resolve_path(base_dir, new_section[key]).as_posix()
        resolved[section_name] = new_section
    return resolved


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
