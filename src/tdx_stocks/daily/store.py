from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ..io_utils import write_json_atomic, write_text_atomic
from ..reports.paths import report_date_token, report_payloads_root, reports_root
from .models import DailyRunReport


def daily_reports_root(data_root: Path) -> Path:
    return reports_root(data_root)


def daily_payloads_root(data_root: Path) -> Path:
    return report_payloads_root(data_root)


def daily_by_date_dir(data_root: Path, as_of: date) -> Path:
    # Kept for API compatibility. Final reports are written directly under reports/.
    return daily_reports_root(data_root)


def latest_daily_json_path(data_root: Path) -> Path:
    # Latest is resolved from dated payloads; this path is kept for compatibility only.
    return daily_payloads_root(data_root) / "daily_latest.json"


def latest_daily_md_path(data_root: Path) -> Path:
    return daily_reports_root(data_root) / "daily_latest.md"


def daily_json_path(data_root: Path, as_of: date) -> Path:
    return daily_payloads_root(data_root) / f"daily_{as_of.isoformat()}.json"


def daily_md_path(data_root: Path, as_of: date) -> Path:
    return daily_reports_root(data_root) / f"daily_{as_of.isoformat()}.md"


def daily_manifest_path(data_root: Path, as_of: date) -> Path:
    return daily_payloads_root(data_root) / f"daily_{as_of.isoformat()}_manifest.json"


def write_daily_json_file(data_root: Path, as_of: date, filename: str, payload: Any) -> Path:
    stem = Path(filename).stem.replace("daily_report", "daily")
    report_date = report_date_token(as_of)
    path = daily_payloads_root(data_root) / f"daily_{stem}_{report_date}.json"
    write_json_atomic(path, payload)
    return path


def save_daily_report(data_root: Path, report: DailyRunReport, markdown: str) -> dict[str, str]:
    as_of = date.fromisoformat(report.as_of)
    paths = {
        "report_markdown": daily_md_path(data_root, as_of),
        "payload_json": daily_json_path(data_root, as_of),
        "manifest": daily_manifest_path(data_root, as_of),
    }
    payload = report.to_dict()
    write_text_atomic(paths["report_markdown"], markdown)
    write_json_atomic(paths["payload_json"], payload)
    write_json_atomic(paths["manifest"], payload)
    return {key: path.as_posix() for key, path in paths.items()}


def load_latest_daily_report(data_root: Path) -> dict[str, Any] | None:
    rows = list_daily_reports(data_root)
    if rows:
        path = Path(str(rows[0].get("path")))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    legacy = data_root / "reports" / "daily" / "latest.json"
    if legacy.exists():
        return json.loads(legacy.read_text(encoding="utf-8"))
    legacy2 = data_root / "reports" / "daily_latest.json"
    if legacy2.exists():
        return json.loads(legacy2.read_text(encoding="utf-8"))
    return None


def load_daily_report(data_root: Path, as_of: str) -> dict[str, Any] | None:
    if as_of == "latest":
        return load_latest_daily_report(data_root)
    parsed = date.fromisoformat(as_of)
    path = daily_json_path(data_root, parsed)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    legacy = data_root / "reports" / "daily" / "by_date" / parsed.isoformat() / "daily_report.json"
    if legacy.exists():
        return json.loads(legacy.read_text(encoding="utf-8"))
    legacy2 = data_root / "reports" / f"daily_{parsed.isoformat()}.json"
    if legacy2.exists():
        return json.loads(legacy2.read_text(encoding="utf-8"))
    return None


def list_daily_reports(data_root: Path) -> list[dict[str, Any]]:
    root = daily_payloads_root(data_root)
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("daily_*.json")):
        name = path.name
        if name.endswith("_manifest.json") or name.startswith("daily_compare_") or name.startswith("daily_consensus_"):
            continue
        token = name.removeprefix("daily_").removesuffix(".json")
        try:
            date.fromisoformat(token)
        except ValueError:
            continue
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
                "markdown_path": daily_md_path(data_root, date.fromisoformat(str(doc.get("as_of") or token))).as_posix(),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("as_of") or ""), reverse=True)
