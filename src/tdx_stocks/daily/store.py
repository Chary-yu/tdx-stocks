from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ..io_utils import write_json_atomic, write_text_atomic
from .models import DailyRunReport


def daily_reports_root(data_root: Path) -> Path:
    return data_root / "reports" / "daily"


def daily_by_date_dir(data_root: Path, as_of: date) -> Path:
    return daily_reports_root(data_root) / "by_date" / as_of.isoformat()


def latest_daily_json_path(data_root: Path) -> Path:
    return daily_reports_root(data_root) / "latest.json"


def latest_daily_md_path(data_root: Path) -> Path:
    return daily_reports_root(data_root) / "latest.md"


def daily_json_path(data_root: Path, as_of: date) -> Path:
    return daily_by_date_dir(data_root, as_of) / "daily_report.json"


def daily_md_path(data_root: Path, as_of: date) -> Path:
    return daily_by_date_dir(data_root, as_of) / "daily_report.md"


def daily_manifest_path(data_root: Path, as_of: date) -> Path:
    return daily_by_date_dir(data_root, as_of) / "manifest.json"


def write_daily_json_file(data_root: Path, as_of: date, filename: str, payload: Any) -> Path:
    path = daily_by_date_dir(data_root, as_of) / filename
    write_json_atomic(path, payload)
    return path


def save_daily_report(data_root: Path, report: DailyRunReport, markdown: str) -> dict[str, str]:
    as_of = date.fromisoformat(report.as_of)
    paths = {
        "latest_json": latest_daily_json_path(data_root),
        "latest_md": latest_daily_md_path(data_root),
        "daily_json": daily_json_path(data_root, as_of),
        "daily_md": daily_md_path(data_root, as_of),
        "manifest": daily_manifest_path(data_root, as_of),
    }
    payload = report.to_dict()
    write_json_atomic(paths["latest_json"], payload)
    write_json_atomic(paths["daily_json"], payload)
    write_json_atomic(paths["manifest"], payload)
    write_text_atomic(paths["latest_md"], markdown)
    write_text_atomic(paths["daily_md"], markdown)
    return {key: path.as_posix() for key, path in paths.items()}


def load_latest_daily_report(data_root: Path) -> dict[str, Any] | None:
    path = latest_daily_json_path(data_root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_daily_report(data_root: Path, as_of: str) -> dict[str, Any] | None:
    if as_of == "latest":
        return load_latest_daily_report(data_root)
    path = daily_json_path(data_root, date.fromisoformat(as_of))
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def list_daily_reports(data_root: Path) -> list[dict[str, Any]]:
    root = daily_reports_root(data_root) / "by_date"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "as_of": doc.get("as_of"),
                "generated_at": doc.get("generated_at"),
                "data_run_id": doc.get("data_run_id"),
                "status": doc.get("status"),
                "warnings": len(doc.get("warnings") or []),
                "errors": len(doc.get("errors") or []),
                "path": path.as_posix(),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("as_of") or ""), reverse=True)
