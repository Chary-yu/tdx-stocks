from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ..backtest.models import BacktestConfig
from ..config import AppConfig, BuildConfig, DailyConfig, FactorConfig, PathsConfig
from .schema import validate_run_config


@dataclass(frozen=True)
class LoadedRunConfig:
    raw_config: dict[str, Any]
    config: dict[str, Any]
    run_config: BacktestConfig | None
    app_config: AppConfig
    path: Path
    base_dir: Path
    task_type: str
    task_name: str

    def section(self, name: str, default: Any | None = None) -> Any:
        return self.config.get(name, default)


def load_run_config(path: Path) -> LoadedRunConfig:
    raw_config = tomllib.loads(path.read_text(encoding="utf-8"))
    task_type, task_name, _warnings = validate_run_config(raw_config)
    base_dir = path.parent.resolve()
    normalized = _resolve_config(raw_config, base_dir=base_dir)
    app_config = _build_app_config(normalized)
    backtest_config = BacktestConfig.from_dict(normalized) if task_type in {"backtest", "grid_search"} else None
    return LoadedRunConfig(
        raw_config=raw_config,
        config=normalized,
        run_config=backtest_config,
        app_config=app_config,
        path=path,
        base_dir=base_dir,
        task_type=task_type,
        task_name=task_name,
    )


def _build_app_config(data: Mapping[str, Any]) -> AppConfig:
    app_defaults = AppConfig()
    paths = data.get("paths") if isinstance(data.get("paths"), Mapping) else {}
    build = data.get("build") if isinstance(data.get("build"), Mapping) else {}
    factors = data.get("factors") if isinstance(data.get("factors"), Mapping) else {}
    daily = data.get("daily") if isinstance(data.get("daily"), Mapping) else {}
    return AppConfig(
        paths=PathsConfig(
            tdx_vipdoc=_load_path(paths.get("tdx_vipdoc"), default=app_defaults.paths.tdx_vipdoc),
            tdx_export=_load_path(paths.get("tdx_export"), default=app_defaults.paths.tdx_export),
            data_root=_load_path(paths.get("data_root"), default=app_defaults.paths.data_root),
            plugin_dir=_load_path(paths.get("plugin_dir"), default=app_defaults.paths.plugin_dir, expanduser=True),
        ),
        build=BuildConfig(
            markets=tuple(build.get("markets", app_defaults.build.markets)),
            universe=str(build.get("universe", app_defaults.build.universe)),
            compression=str(build.get("compression", app_defaults.build.compression)),
            batch_rows=int(build.get("batch_rows", app_defaults.build.batch_rows)),
            duckdb_memory_limit=str(build.get("duckdb_memory_limit", app_defaults.build.duckdb_memory_limit)),
            overwrite_staging=bool(build.get("overwrite_staging", app_defaults.build.overwrite_staging)),
        ),
        factors=FactorConfig(
            windows=tuple(int(value) for value in factors.get("windows", app_defaults.factors.windows)),
        ),
        daily=DailyConfig(
            enabled_strategies=tuple(
                daily.get("enabled_strategies", app_defaults.daily.enabled_strategies)
            ),
            strategy_limit=int(daily.get("strategy_limit", app_defaults.daily.strategy_limit)),
            strategy_min_score=float(daily.get("strategy_min_score", app_defaults.daily.strategy_min_score)),
            consensus_min_hit=int(daily.get("consensus_min_hit", app_defaults.daily.consensus_min_hit)),
            consensus_limit=int(daily.get("consensus_limit", app_defaults.daily.consensus_limit)),
            portfolio_top=int(daily.get("portfolio_top", app_defaults.daily.portfolio_top)),
            portfolio_weighting=str(daily.get("portfolio_weighting", app_defaults.daily.portfolio_weighting)),
            exclude_risk_tags=tuple(daily.get("exclude_risk_tags", app_defaults.daily.exclude_risk_tags)),
        ),
    )


def _resolve_config(data: dict[str, Any], *, base_dir: Path) -> dict[str, Any]:
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


def _load_path(value: object | None, *, default: Path, expanduser: bool = False) -> Path:
    if value in (None, ""):
        path = default
    elif isinstance(value, Path):
        path = value
    else:
        path = Path(os.path.expandvars(str(value)))
    if expanduser:
        path = path.expanduser()
    return path


def _resolve_path(base_dir: Path, value: str) -> Path:
    path = Path(os.path.expandvars(value)).expanduser()
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()
