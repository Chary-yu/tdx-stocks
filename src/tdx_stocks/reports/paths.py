from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

TASK_SLUGS: dict[str, str] = {
    "daily": "daily",
    "signal": "signal",
    "portfolio": "portfolio",
    "rebalance": "rebalance",
    "backtest": "backtest",
    "grid_search": "grid",
    "grid": "grid",
}

TASK_OUTPUT_LABELS: dict[str, str] = {
    "daily": "每日综合报告",
    "signal": "信号报告",
    "portfolio": "组合报告",
    "rebalance": "调仓报告",
    "backtest": "回测报告",
    "grid": "参数搜索报告",
}


def reports_root(data_root: Path) -> Path:
    """Directory for final human-readable Markdown reports only."""
    return data_root / "reports"


def report_payloads_root(data_root: Path) -> Path:
    """Directory for JSON payloads and other machine-readable report artifacts."""
    return data_root / "report_payloads"


def task_slug(task_type: str | None) -> str:
    value = str(task_type or "run").strip().replace("_", "-")
    return TASK_SLUGS.get(str(task_type or "run"), value)


def report_date_token(*values: Any) -> str:
    for value in values:
        token = _date_from_value(value)
        if token:
            return token
    return date.today().isoformat()


def run_report_outputs(
    data_root: Path,
    task_type: str,
    *,
    as_of: Any = None,
    strategy: Any = None,
) -> dict[str, str]:
    """Return final report and payload paths for a run task.

    V8 naming rule:
    - one ``tdx-stocks run <task>`` command maps to one final Markdown report;
    - final reports live directly under ``Database/reports``;
    - JSON/debug payloads live under ``Database/report_payloads``;
    - same task + same data date overwrites the previous file.

    Strategy names are intentionally kept in report content, not in filenames.
    """
    slug = task_slug(task_type)
    report_date = report_date_token(as_of)
    return {
        "report_markdown": (reports_root(data_root) / f"{slug}_{report_date}.md").as_posix(),
        "payload_json": (report_payloads_root(data_root) / f"{slug}_{report_date}.json").as_posix(),
    }


def report_outputs_from_result(data_root: Path, result: Any) -> dict[str, str]:
    payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    task_type = str(payload.get("task_type") or "run")
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    as_of = _find_as_of(summary) or payload.get("as_of") or payload.get("generated_at")
    if not _date_from_value(as_of):
        as_of = _find_generated_at(summary) or payload.get("generated_at")
    return run_report_outputs(data_root, task_type, as_of=as_of)


def _find_as_of(value: Any) -> Any:
    if isinstance(value, dict):
        direct = value.get("as_of")
        if direct not in (None, "", "latest"):
            return direct
        for item in value.values():
            found = _find_as_of(item)
            if found not in (None, "", "latest"):
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_as_of(item)
            if found not in (None, "", "latest"):
                return found
    return None


def _find_generated_at(value: Any) -> Any:
    if isinstance(value, dict):
        direct = value.get("generated_at")
        if direct:
            return direct
        for item in value.values():
            found = _find_generated_at(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_generated_at(item)
            if found:
                return found
    return None


def _date_from_value(value: Any) -> str | None:
    if value in (None, "", "latest"):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    text = str(value).strip()
    if not text or text == "latest":
        return None
    if len(text) >= 10:
        prefix = text[:10]
        try:
            return date.fromisoformat(prefix).isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError:
        return None
