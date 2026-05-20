from __future__ import annotations

import json
from pathlib import Path

from ..io_utils import write_text_atomic
from ..runner.models import RunResult


def render_run_result_markdown(result: RunResult) -> str:
    payload = result.to_dict()
    lines = [
        f"# Run Report: {payload.get('task_type')}",
        "",
        "## Summary",
        "",
        f"- Name: {payload.get('name')}",
        f"- Status: {payload.get('status')}",
        f"- Task Type: {payload.get('task_type')}",
        "",
        "## Outputs",
        "",
        _render_table(
            ["name", "path"],
            [(key, value) for key, value in (payload.get("outputs") or {}).items()],
        ),
        "",
        "## Warnings",
        "",
        _render_list(payload.get("warnings")),
        "",
        "## Errors",
        "",
        _render_list(payload.get("errors")),
        "",
        "<details>",
        "<summary>Raw JSON</summary>",
        "",
        "```json",
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        "```",
        "",
        "</details>",
    ]
    return "\n".join(lines).rstrip() + "\n"


def save_run_result_markdown(path: Path, result: RunResult) -> Path:
    return write_text_atomic(path, render_run_result_markdown(result))


def _render_table(columns: list[str], rows: list[tuple[object, object]]) -> str:
    if not rows:
        return "_No data available._"
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join(
        "| " + " | ".join(str(value) for value in row) + " |" for row in rows
    )
    return "\n".join([header, separator, body])


def _render_list(values: object) -> str:
    if not values:
        return "_No data available._"
    if isinstance(values, list):
        return "\n".join(f"- {item}" for item in values)
    return str(values)
