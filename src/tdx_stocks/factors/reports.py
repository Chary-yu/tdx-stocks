from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .. import __version__ as APP_VERSION


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def write_json_atomic(path: Path, document: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(json_safe(document), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)
    return path


def build_factor_catalog_report(data_run_id: str | None = None, factor_version: str | None = None) -> dict[str, Any]:
    from .catalog import list_factor_definitions

    return {
        "schema_version": "factor-catalog-v1",
        "app_version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_run_id": data_run_id,
        "factor_version": factor_version,
        "factors": [definition.to_dict() for definition in list_factor_definitions()],
    }


def build_data_quality_report(
    summary: dict[str, Any],
    checks: list[dict[str, Any]],
    *,
    factor_quality: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "data-quality-report-v1",
        "app_version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": json_safe(summary),
        "checks": json_safe(checks),
        "factor_quality": json_safe(factor_quality) if factor_quality is not None else None,
        "factor_quality_report": json_safe(factor_quality) if factor_quality is not None else None,
    }


def build_factor_quality_report(summary: dict[str, Any], columns: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "factor-quality-report-v1",
        "app_version": APP_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": json_safe(summary),
        "columns": json_safe(columns),
    }
