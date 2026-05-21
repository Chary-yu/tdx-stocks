from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from ..config_validators import validate_compression

DEFAULT_TDX_VIPDOC = Path("./vipdoc")
DEFAULT_TDX_EXPORT = Path("./export")
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
    portfolio_max_weight: float = 0.10
    exclude_risk_tags: tuple[str, ...] = ("high_volatility", "low_liquidity")


@dataclass(frozen=True)
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    factors: FactorConfig = field(default_factory=FactorConfig)
    daily: DailyConfig = field(default_factory=DailyConfig)


def _load_path_info(
    value: object | None,
    *,
    default: Path,
    env_name: str | None = None,
    expanduser: bool = False,
) -> tuple[Path, bool]:
    raw = value
    env_used = False
    if raw in (None, "") and env_name:
        env_value = os.environ.get(env_name)
        if env_value:
            raw = env_value
            env_used = True
    if raw in (None, ""):
        path = default
    elif isinstance(raw, Path):
        path = raw
    else:
        path = Path(os.path.expandvars(str(raw)))
    path = path.expanduser() if expanduser else path
    should_detect = not env_used and path == default
    return path, should_detect


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        tdx_vipdoc, detect_vipdoc = _load_path_info(
            None,
            default=DEFAULT_TDX_VIPDOC,
            env_name="TDX_STOCKS_TDX_VIPDOC",
        )
        tdx_export, detect_export = _load_path_info(
            None,
            default=DEFAULT_TDX_EXPORT,
            env_name="TDX_STOCKS_TDX_EXPORT",
        )
        data_root, _ = _load_path_info(
            None,
            default=DEFAULT_DATA_ROOT,
            env_name="TDX_STOCKS_DATA_ROOT",
        )
        plugin_dir, _ = _load_path_info(
            None,
            default=DEFAULT_PLUGIN_DIR,
            env_name="TDX_STOCKS_PLUGIN_DIR",
            expanduser=True,
        )
        return resolve_tdx_paths(
            AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=tdx_vipdoc,
                    tdx_export=tdx_export,
                    data_root=data_root,
                    plugin_dir=plugin_dir,
                ),
            ),
            detect_vipdoc=detect_vipdoc,
            detect_export=detect_export,
        )

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    build = data.get("build", {})
    factors = data.get("factors", {})
    daily = data.get("daily", {})

    tdx_vipdoc, detect_vipdoc = _load_path_info(
        paths.get("tdx_vipdoc"),
        default=DEFAULT_TDX_VIPDOC,
        env_name="TDX_STOCKS_TDX_VIPDOC",
    )
    tdx_export, detect_export = _load_path_info(
        paths.get("tdx_export"),
        default=DEFAULT_TDX_EXPORT,
        env_name="TDX_STOCKS_TDX_EXPORT",
    )
    data_root, _ = _load_path_info(
        paths.get("data_root"),
        default=DEFAULT_DATA_ROOT,
        env_name="TDX_STOCKS_DATA_ROOT",
    )
    plugin_dir, _ = _load_path_info(
        paths.get("plugin_dir"),
        default=DEFAULT_PLUGIN_DIR,
        env_name="TDX_STOCKS_PLUGIN_DIR",
        expanduser=True,
    )

    return resolve_tdx_paths(
        AppConfig(
            paths=PathsConfig(
                tdx_vipdoc=tdx_vipdoc,
                tdx_export=tdx_export,
                data_root=data_root,
                plugin_dir=plugin_dir,
            ),
            build=BuildConfig(
                markets=tuple(build.get("markets", ("sh", "sz"))),
                universe=build.get("universe", "ashare"),
                compression=validate_compression(build.get("compression", "zstd")),
                batch_rows=int(build.get("batch_rows", 200_000)),
                duckdb_memory_limit=build.get("duckdb_memory_limit", "8GB"),
                overwrite_staging=bool(build.get("overwrite_staging", False)),
            ),
            factors=FactorConfig(
                windows=tuple(int(w) for w in factors.get("windows", (5, 10, 20, 60))),
            ),
            daily=DailyConfig(
                enabled_strategies=tuple(
                    daily.get(
                        "enabled_strategies",
                        (
                            "trend-strength",
                            "relative-strength",
                            "low-vol-breakout",
                            "volume-breakout",
                        ),
                    )
                ),
                strategy_limit=int(daily.get("strategy_limit", 50)),
                strategy_min_score=float(daily.get("strategy_min_score", 60.0)),
                consensus_min_hit=int(daily.get("consensus_min_hit", 2)),
                consensus_limit=int(daily.get("consensus_limit", 50)),
                portfolio_top=int(daily.get("portfolio_top", 20)),
                portfolio_weighting=str(daily.get("portfolio_weighting", "equal")),
                portfolio_max_weight=float(daily.get("portfolio_max_weight", 0.10)),
                exclude_risk_tags=tuple(daily.get("exclude_risk_tags", ("high_volatility", "low_liquidity"))),
            ),
        ),
        detect_vipdoc=detect_vipdoc,
        detect_export=detect_export,
    )


def default_config_text(*, data_root: Path) -> str:
    data_root_text = _format_relative_path(data_root)
    return f"""[paths]
tdx_vipdoc = "./vipdoc"
tdx_export = "./export"
data_root = "{data_root_text}"
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
portfolio_max_weight = 0.10
exclude_risk_tags = ["high_volatility", "low_liquidity"]
"""


def write_default_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_text(data_root=DEFAULT_DATA_ROOT), encoding="utf-8")


def _format_relative_path(path: Path) -> str:
    text = path.as_posix()
    if path.is_absolute():
        return text
    if text.startswith("./") or text.startswith("../"):
        return text
    return f"./{text}"


def resolve_tdx_paths(
    config: AppConfig,
    *,
    detect_vipdoc: bool = True,
    detect_export: bool = True,
) -> AppConfig:
    return AppConfig(
        paths=PathsConfig(
            tdx_vipdoc=_resolve_tdx_vipdoc_path(config.paths.tdx_vipdoc) if detect_vipdoc else config.paths.tdx_vipdoc,
            tdx_export=_resolve_tdx_export_path(config.paths.tdx_export) if detect_export else config.paths.tdx_export,
            data_root=config.paths.data_root,
            plugin_dir=config.paths.plugin_dir,
        ),
        build=config.build,
        factors=config.factors,
        daily=config.daily,
    )


def _resolve_tdx_vipdoc_path(path: Path) -> Path:
    if _has_day_files(path):
        return path
    for candidate in _candidate_tdx_vipdoc_paths():
        if _has_day_files(candidate):
            return candidate
    return path


def _resolve_tdx_export_path(path: Path) -> Path:
    if _has_export_text_files(path):
        return path
    for candidate in _candidate_tdx_export_paths():
        if _has_export_text_files(candidate):
            return candidate
    return path


def _has_day_files(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*/lday/*.day"))


def _has_export_text_files(path: Path) -> bool:
    return path.is_dir() and any(path.glob("*.txt"))


@lru_cache(maxsize=1)
def _candidate_tdx_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    for raw_root in (os.environ.get("TDX_STOCKS_TDX_ROOT"), os.environ.get("TDX_ROOT")):
        if raw_root:
            roots.append(Path(raw_root).expanduser())
    for mount_name in ("c", "d", "e", "f"):
        mount_root = Path("/mnt") / mount_name
        if not mount_root.exists():
            continue
        roots.extend(
            [
                mount_root / "ProgramFiles" / "Tdx",
                mount_root / "Program Files" / "Tdx",
                mount_root / "Tdx",
                mount_root / "TongDaXin",
                mount_root / "tdx",
            ]
        )
    home = Path.home()
    roots.extend([home / "Tdx", home / "tdx"])

    seen: set[str] = set()
    unique: list[Path] = []
    for root in roots:
        key = root.expanduser().as_posix()
        if key in seen:
            continue
        seen.add(key)
        unique.append(root.expanduser())
    return tuple(unique)


def _candidate_tdx_vipdoc_paths() -> tuple[Path, ...]:
    candidates: list[Path] = []
    for root in _candidate_tdx_roots():
        candidates.extend([root / "vipdoc", root])
    return tuple(candidates)


def _candidate_tdx_export_paths() -> tuple[Path, ...]:
    candidates: list[Path] = []
    for root in _candidate_tdx_roots():
        candidates.extend([root / "T0002" / "export", root / "export", root])
    return tuple(candidates)
