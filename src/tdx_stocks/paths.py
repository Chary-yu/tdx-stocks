from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunPaths:
    data_root: Path
    run_id: str

    @property
    def staging_dir(self) -> Path:
        return self.data_root / "_staging" / self.run_id

    @property
    def version_dir(self) -> Path:
        return self.data_root / "versions" / self.run_id

    @property
    def latest_manifest(self) -> Path:
        return self.data_root / "latest.json"

    @property
    def reports_dir(self) -> Path:
        return self.staging_dir / "reports"

    @property
    def parquet_dir(self) -> Path:
        return self.staging_dir / "parquet"

    @property
    def cache_dir(self) -> Path:
        return self.data_root / "cache"

    @property
    def cache_corporate_actions_dir(self) -> Path:
        return self.cache_dir / "corporate_actions"

    @property
    def cache_adjustment_factors_dir(self) -> Path:
        return self.cache_dir / "adjustment_factors"

    @property
    def raw_daily_dir(self) -> Path:
        return self.parquet_dir / "raw_daily"

    @property
    def corporate_actions_dir(self) -> Path:
        return self.parquet_dir / "corporate_actions"

    @property
    def adjustment_factors_dir(self) -> Path:
        return self.parquet_dir / "adjustment_factors"

    @property
    def adj_daily_dir(self) -> Path:
        return self.parquet_dir / "adj_daily"

    @property
    def hfq_daily_dir(self) -> Path:
        return self.parquet_dir / "hfq_daily"

    @property
    def factors_dir(self) -> Path:
        return self.parquet_dir / "factors"

    @property
    def duckdb_tmp_dir(self) -> Path:
        return self.data_root / "duckdb" / "tmp"


def ensure_base_dirs(data_root: Path) -> None:
    for name in ("_staging", "versions", "duckdb/tmp", "cache/corporate_actions", "cache/adjustment_factors"):
        (data_root / name).mkdir(parents=True, exist_ok=True)
