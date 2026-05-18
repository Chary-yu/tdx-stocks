from __future__ import annotations

from typing import Any


def collect_warnings_errors(steps: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    for step in steps:
        status = str(step.get("status") or "")
        message = str(step.get("message") or "")
        if status == "warning":
            warnings.append(f"{step.get('step_name')}: {message}")
        elif status == "failed":
            errors.append(f"{step.get('step_name')}: {message}")
    return warnings, errors
