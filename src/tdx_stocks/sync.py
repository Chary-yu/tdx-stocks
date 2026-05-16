from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .duckdb_ops import has_parquet_files
from .export_io import iter_export_files
from .query import load_latest_manifest


@dataclass(frozen=True)
class SyncPlanStep:
    name: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "reason": self.reason}


@dataclass(frozen=True)
class SyncPlan:
    data_root: str
    tdx_export: str
    latest_manifest: str | None
    latest_generated_at: str | None
    latest_export_mtime: str | None
    cache_corporate_actions: bool
    cache_adjustment_factors: bool
    steps: list[SyncPlanStep]

    @property
    def needs_write(self) -> bool:
        return bool(self.steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "data_root": self.data_root,
            "tdx_export": self.tdx_export,
            "latest_manifest": self.latest_manifest,
            "latest_generated_at": self.latest_generated_at,
            "latest_export_mtime": self.latest_export_mtime,
            "cache_corporate_actions": self.cache_corporate_actions,
            "cache_adjustment_factors": self.cache_adjustment_factors,
            "needs_write": self.needs_write,
            "steps": [step.to_dict() for step in self.steps],
        }


def build_sync_plan(config: AppConfig) -> SyncPlan:
    latest_manifest_path = config.paths.data_root / "latest.json"
    latest_manifest: dict | None = None
    latest_generated_at: datetime | None = None
    if latest_manifest_path.exists():
        latest_manifest = load_latest_manifest(config.paths.data_root)
        summary = latest_manifest.get("summary", {})
        generated_at = summary.get("generated_at")
        if generated_at:
            try:
                latest_generated_at = datetime.fromisoformat(str(generated_at))
            except ValueError:
                latest_generated_at = None

    latest_export_mtime = _latest_export_mtime(config.paths.tdx_export)
    cache_root = config.paths.data_root / "cache"
    cache_corporate_actions = has_parquet_files(cache_root / "corporate_actions")
    cache_adjustment_factors = has_parquet_files(cache_root / "adjustment_factors")

    if latest_export_mtime is None and (latest_manifest is None or not cache_corporate_actions or not cache_adjustment_factors):
        raise FileNotFoundError(f"no export text files found under: {config.paths.tdx_export}")

    steps: list[SyncPlanStep] = []
    if latest_manifest is None:
        steps.append(SyncPlanStep("data update", "latest.json is missing"))
        steps.append(SyncPlanStep("data rebuild", "latest.json is missing"))
    elif latest_generated_at is None:
        steps.append(SyncPlanStep("data update", "latest manifest has no generated_at"))
        steps.append(SyncPlanStep("data rebuild", "latest manifest has no generated_at"))
    elif latest_export_mtime is not None and latest_export_mtime > latest_generated_at:
        steps.append(SyncPlanStep("data update", "export text is newer than latest dataset"))
        steps.append(SyncPlanStep("data rebuild", "export text is newer than latest dataset"))
    elif not cache_corporate_actions or not cache_adjustment_factors:
        steps.append(SyncPlanStep("data update", "cache is incomplete"))
        steps.append(SyncPlanStep("data rebuild", "cache is incomplete"))

    return SyncPlan(
        data_root=config.paths.data_root.as_posix(),
        tdx_export=config.paths.tdx_export.as_posix(),
        latest_manifest=latest_manifest_path.as_posix() if latest_manifest_path.exists() else None,
        latest_generated_at=latest_generated_at.isoformat(timespec="seconds") if latest_generated_at else None,
        latest_export_mtime=latest_export_mtime.isoformat(timespec="seconds") if latest_export_mtime else None,
        cache_corporate_actions=cache_corporate_actions,
        cache_adjustment_factors=cache_adjustment_factors,
        steps=steps,
    )


def _latest_export_mtime(export_dir: Path) -> datetime | None:
    latest: datetime | None = None
    for path in iter_export_files(export_dir):
        mtime = datetime.fromtimestamp(path.stat().st_mtime)
        latest = mtime if latest is None else max(latest, mtime)
    return latest
