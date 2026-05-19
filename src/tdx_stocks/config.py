from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TDX_VIPDOC = Path("")
DEFAULT_TDX_EXPORT = Path("")
DEFAULT_DATA_ROOT = Path("./Database")
DEFAULT_PLUGIN_DIR = Path("~/.tdx-stocks/plugins")


@dataclass(frozen=True)
class PathsConfig:
    tdx_vipdoc: Path = DEFAULT_TDX_VIPDOC
    tdx_export: Path = DEFAULT_TDX_EXPORT
    data_root: Path = DEFAULT_DATA_ROOT
    plugin_dir: Path = DEFAULT_PLUGIN_DIR


@dataclass(frozen=True)
class BuildConfig:
    markets: tuple[str, ...] = ("sh", "sz")
    universe: str = "ashare"
    compression: str = "zstd"
    batch_rows: int = 200_000
    duckdb_memory_limit: str = "8GB"
    overwrite_staging: bool = False


@dataclass(frozen=True)
class FactorConfig:
    windows: tuple[int, ...] = (5, 10, 20, 60)


@dataclass(frozen=True)
class DailyConfig:
    enabled_strategies: tuple[str, ...] = (
        "trend-strength",
        "relative-strength",
        "low-vol-breakout",
        "volume-breakout",
    )
    strategy_limit: int = 50
    strategy_min_score: float = 60.0
    consensus_min_hit: int = 2
    consensus_limit: int = 50
    portfolio_top: int = 20
    portfolio_weighting: str = "equal"
    exclude_risk_tags: tuple[str, ...] = ("high_volatility", "low_liquidity")


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    factors: FactorConfig = field(default_factory=FactorConfig)
    daily: DailyConfig = field(default_factory=DailyConfig)


def _load_path(value: object | None, *, default: Path, env_name: str | None = None, expanduser: bool = False) -> Path:
    raw = value
    if raw in (None, "") and env_name:
        env_value = os.environ.get(env_name)
        if env_value:
            raw = env_value
    if raw in (None, ""):
        path = default
    elif isinstance(raw, Path):
        path = raw
    else:
        path = Path(str(raw))
    return path.expanduser() if expanduser else path


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        return AppConfig()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    build = data.get("build", {})
    factors = data.get("factors", {})
    daily = data.get("daily", {})

    return AppConfig(
        paths=PathsConfig(
            tdx_vipdoc=_load_path(paths.get("tdx_vipdoc"), default=DEFAULT_TDX_VIPDOC, env_name="TDX_STOCKS_TDX_VIPDOC"),
            tdx_export=_load_path(paths.get("tdx_export"), default=DEFAULT_TDX_EXPORT, env_name="TDX_STOCKS_TDX_EXPORT"),
            data_root=_load_path(paths.get("data_root"), default=DEFAULT_DATA_ROOT, env_name="TDX_STOCKS_DATA_ROOT"),
            plugin_dir=_load_path(paths.get("plugin_dir"), default=DEFAULT_PLUGIN_DIR, env_name="TDX_STOCKS_PLUGIN_DIR", expanduser=True),
        ),
        build=BuildConfig(
            markets=tuple(build.get("markets", ("sh", "sz"))),
            universe=build.get("universe", "ashare"),
            compression=build.get("compression", "zstd"),
            batch_rows=int(build.get("batch_rows", 200_000)),
            duckdb_memory_limit=build.get("duckdb_memory_limit", "8GB"),
            overwrite_staging=bool(build.get("overwrite_staging", False)),
        ),
        factors=FactorConfig(
            windows=tuple(int(w) for w in factors.get("windows", (5, 10, 20, 60))),
        ),
        daily=DailyConfig(
            enabled_strategies=tuple(daily.get(
                "enabled_strategies",
                (
                    "trend-strength",
                    "relative-strength",
                    "low-vol-breakout",
                    "volume-breakout",
                ),
            )),
            strategy_limit=int(daily.get("strategy_limit", 50)),
            strategy_min_score=float(daily.get("strategy_min_score", 60.0)),
            consensus_min_hit=int(daily.get("consensus_min_hit", 2)),
            consensus_limit=int(daily.get("consensus_limit", 50)),
            portfolio_top=int(daily.get("portfolio_top", 20)),
            portfolio_weighting=str(daily.get("portfolio_weighting", "equal")),
            exclude_risk_tags=tuple(daily.get("exclude_risk_tags", ("high_volatility", "low_liquidity"))),
        ),
    )


def write_default_config(path: Path) -> None:
    text = """[paths]
tdx_vipdoc = ""
tdx_export = ""
data_root = "./Database"
plugin_dir = "~/.tdx-stocks/plugins"

[build]
markets = ["sh", "sz"]
universe = "ashare"
compression = "zstd"
batch_rows = 200000
duckdb_memory_limit = "8GB"
overwrite_staging = false

[factors]
windows = [5, 10, 20, 60]

[daily]
enabled_strategies = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]
strategy_limit = 50
strategy_min_score = 60.0
consensus_min_hit = 2
consensus_limit = 50
portfolio_top = 20
portfolio_weighting = "equal"
exclude_risk_tags = ["high_volatility", "low_liquidity"]
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
