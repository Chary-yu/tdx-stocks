from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .. import __version__ as APP_VERSION
from ..io_utils import write_json_atomic

REPORT_SCHEMA_VERSION = "strategy-report-v1"
REPORT_ROOT_NAME = "reports"


def strategy_reports_root(data_root: Path) -> Path:
    return data_root / REPORT_ROOT_NAME / "strategies"


def latest_report_dir(data_root: Path) -> Path:
    return strategy_reports_root(data_root) / "latest"


def by_date_report_dir(data_root: Path, as_of: date) -> Path:
    return strategy_reports_root(data_root) / "by_date" / as_of.isoformat()


def by_run_id_report_dir(data_root: Path, run_id: str) -> Path:
    return strategy_reports_root(data_root) / "by_run_id" / run_id


def report_path(data_root: Path, strategy_name: str, *, as_of: date | None = None, run_id: str | None = None) -> Path:
    if run_id is not None:
        return by_run_id_report_dir(data_root, run_id) / f"{strategy_name}.json"
    if as_of is not None:
        return by_date_report_dir(data_root, as_of) / f"{strategy_name}.json"
    return latest_report_dir(data_root) / f"{strategy_name}.json"


def save_report_document(data_root: Path, strategy_name: str, document: dict[str, Any]) -> dict[str, str]:
    schema_version = str(document.get("schema_version") or REPORT_SCHEMA_VERSION)
    document = dict(document)
    document["schema_version"] = schema_version
    targets = {
        "latest": report_path(data_root, strategy_name),
    }
    as_of_text = document.get("as_of")
    if as_of_text:
        targets["by_date"] = report_path(data_root, strategy_name, as_of=date.fromisoformat(str(as_of_text)))
    run_id = document.get("data_run_id")
    if run_id:
        targets["by_run_id"] = report_path(data_root, strategy_name, run_id=str(run_id))

    for path in targets.values():
        write_json_atomic(path, document)
    return {name: path.as_posix() for name, path in targets.items()}


def load_report_document(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_saved_report(
    data_root: Path,
    strategy_name: str,
    *,
    as_of: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any] | None:
    if run_id:
        path = report_path(data_root, strategy_name, run_id=run_id)
        if path.exists():
            return load_report_document(path)
        return None
    if as_of and as_of != "latest":
        path = report_path(data_root, strategy_name, as_of=date.fromisoformat(as_of))
        if path.exists():
            return load_report_document(path)
        return None
    path = report_path(data_root, strategy_name)
    if path.exists():
        return load_report_document(path)
    return None


def list_saved_reports(data_root: Path) -> list[dict[str, Any]]:
    root = strategy_reports_root(data_root) / "by_run_id"
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*.json")):
        try:
            doc = load_report_document(path)
        except (OSError, json.JSONDecodeError):
            continue
        items.append(
            {
                "strategy_name": doc.get("strategy_name"),
                "as_of": doc.get("as_of"),
                "generated_at": doc.get("generated_at"),
                "data_run_id": doc.get("data_run_id"),
                "factor_version": doc.get("factor_version"),
                "candidate_count": doc.get("candidate_count"),
                "excluded_count": doc.get("excluded_count"),
                "path": path.as_posix(),
            }
        )
    return sorted(
        items,
        key=lambda item: (
            str(item.get("generated_at") or ""),
            str(item.get("strategy_name") or ""),
            str(item.get("data_run_id") or ""),
        ),
        reverse=True,
    )


def build_report_document(
    *,
    strategy_name: str,
    as_of: date,
    generated_at: datetime,
    data_run_id: str | None,
    factor_version: str | None,
    params: Any,
    report: Any,
) -> dict[str, Any]:
    report_dict = report.to_dict() if hasattr(report, "to_dict") else dict(report)
    summary = dict(report_dict.get("summary") or {})
    picks = list(report_dict.get("picks") or [])
    excluded = list(report_dict.get("excluded") or [])
    explain = report_dict.get("explain")
    candidate_count = int(summary.get("eligible") or len(picks))
    excluded_count = int(summary.get("excluded") or len(excluded))
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "strategy_name": strategy_name,
        "as_of": as_of.isoformat(),
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "data_run_id": data_run_id,
        "factor_version": factor_version,
        "params": json_safe(params),
        "candidate_count": candidate_count,
        "excluded_count": excluded_count,
        "candidates": picks,
        "excluded_summary": _build_excluded_summary(excluded, summary),
        "risk_summary": summary.get("risk_flag_counts", {}),
        "diagnostics": {
            "summary": summary,
            "explain": explain,
        },
    }


def json_safe(value: Any) -> Any:
    if is_dataclass(value):
        return json_safe(asdict(value))
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _build_excluded_summary(excluded: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    reason_counts: dict[str, int] = {}
    for row in excluded:
        reason = str(row.get("excluded_reason") or "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    return {
        "total": int(summary.get("excluded") or len(excluded)),
        "reasons": reason_counts,
    }
