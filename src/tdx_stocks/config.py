from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


DEFAULT_TDX_VIPDOC = Path("/mnt/d/ProgramFiles/Tdx/vipdoc")
DEFAULT_DATA_ROOT = Path("/mnt/d/Zcyu/Chary-codex/tdx-stocks/Database")


@dataclass(frozen=True)
class PathsConfig:
    tdx_vipdoc: Path = DEFAULT_TDX_VIPDOC
    data_root: Path = DEFAULT_DATA_ROOT


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
class AppConfig:
    paths: PathsConfig = field(default_factory=PathsConfig)
    build: BuildConfig = field(default_factory=BuildConfig)
    factors: FactorConfig = field(default_factory=FactorConfig)


def load_config(path: Path | None) -> AppConfig:
    if path is None:
        return AppConfig()

    data = tomllib.loads(path.read_text(encoding="utf-8"))
    paths = data.get("paths", {})
    build = data.get("build", {})
    factors = data.get("factors", {})

    return AppConfig(
        paths=PathsConfig(
            tdx_vipdoc=Path(paths.get("tdx_vipdoc", DEFAULT_TDX_VIPDOC)),
            data_root=Path(paths.get("data_root", DEFAULT_DATA_ROOT)),
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
    )


def write_default_config(path: Path) -> None:
    text = f"""[paths]
tdx_vipdoc = "{DEFAULT_TDX_VIPDOC.as_posix()}"
data_root = "{DEFAULT_DATA_ROOT.as_posix()}"

[build]
markets = ["sh", "sz"]
universe = "ashare"
compression = "zstd"
batch_rows = 200000
duckdb_memory_limit = "8GB"
overwrite_staging = false

[factors]
windows = [5, 10, 20, 60]
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
