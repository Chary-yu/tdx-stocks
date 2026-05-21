from __future__ import annotations

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
    ]
    lines.extend(_render_summary_sections(payload.get("summary")))
    lines.extend(
        [
            "## Warnings",
            "",
            _render_list(payload.get("warnings")),
            "",
            "## Errors",
            "",
            _render_list(payload.get("errors")),
            "",
            "## Raw JSON",
            "",
            "_Full JSON payload is available in the paired `.json` report file._",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_run_result_markdown(path: Path, result: RunResult) -> Path:
    return write_text_atomic(path, render_run_result_markdown(result))


def _render_table(columns: list[str], rows: list[tuple[object, object]]) -> str:
    if not rows:
        return "_No data available._"
    header = "| " + " | ".join(_escape_md_cell(str(column)) for column in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = "\n".join(
        "| " + " | ".join(_escape_md_cell(_stringify(value)) for value in row) + " |" for row in rows
    )
    return "\n".join([header, separator, body])


def _render_list(values: object) -> str:
    if not values:
        return "_No data available._"
    if isinstance(values, list):
        return "\n".join(f"- {_escape_md_cell(_stringify(item))}" for item in values)
    return _escape_md_cell(_stringify(values))


def _render_summary_sections(summary: object) -> list[str]:
    if not isinstance(summary, dict) or not summary:
        return []

    lines: list[str] = []
    compare = summary.get("compare")
    if isinstance(compare, dict) and compare:
        lines.extend(
            [
                "## Strategy Compare",
                "",
                _render_table(
                    ["strategy", "candidates", "avg_score", "max_score", "high_score_count", "risk_flags", "stocks"],
                    _render_compare_rows(compare),
                ),
                "",
            ]
        )
        lines.extend(_render_named_section("Unique Stocks", compare.get("unique_stocks"), heading_level=3))
        lines.extend(_render_named_section("Overlaps", compare.get("overlaps"), heading_level=3))

    consensus = summary.get("consensus")
    if isinstance(consensus, dict) and consensus:
        lines.extend(
            [
                "## Consensus",
                "",
                _render_table(
                    ["market", "symbol", "hits", "avg_score", "max_score", "strategies", "risk_flags"],
                    _render_consensus_rows(consensus),
                ),
                "",
            ]
        )
    for key, value in summary.items():
        if key in {"compare", "consensus"}:
            continue
        lines.extend(_render_named_section(_titleize(key), value))
    return lines


def _render_named_section(title: str, value: object, *, heading_level: int = 2) -> list[str]:
    if value is None or value == {} or value == []:
        return []
    heading = "#" * max(2, heading_level)
    if isinstance(value, dict):
        rows = [(key, _stringify(v)) for key, v in value.items()]
        if rows:
            return [f"{heading} {title}", "", _render_table(["field", "value"], rows), ""]
        return []
    if isinstance(value, list):
        if not value:
            return []
        if all(isinstance(item, dict) for item in value):
            rows = _render_rows_from_dicts(value)
            if rows:
                headers = list(rows[0].keys())
                table_rows = [tuple(row.get(header) for header in headers) for row in rows]
                return [f"{heading} {title}", "", _render_table(headers, table_rows), ""]
        return [f"{heading} {title}", "", _render_list(value), ""]
    return [f"{heading} {title}", "", str(value), ""]


def _render_compare_rows(compare: dict[str, object]) -> list[tuple[object, object, object, object, object, object, object]]:
    rows = compare.get("strategies")
    if not isinstance(rows, list) or not rows:
        return []
    rendered: list[tuple[object, object, object, object, object, object, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rendered.append(
            (
                row.get("strategy_name"),
                row.get("candidate_count"),
                row.get("avg_score"),
                row.get("max_score"),
                row.get("high_score_count"),
                row.get("risk_flag_count"),
                row.get("stocks"),
            )
        )
    return rendered


def _render_rows_from_dicts(items: list[dict[str, object]]) -> list[dict[str, object]]:
    if not items:
        return []
    headers: list[str] = []
    seen: set[str] = set()
    for item in items:
        for key in item.keys():
            if key not in seen:
                seen.add(key)
                headers.append(key)
    normalized: list[dict[str, object]] = []
    for item in items:
        normalized.append({header: item.get(header) for header in headers})
    return normalized


def _render_consensus_rows(consensus: dict[str, object]) -> list[tuple[object, object, object, object, object, object, object]]:
    rows = consensus.get("rows")
    if not isinstance(rows, list) or not rows:
        return []
    rendered: list[tuple[object, object, object, object, object, object, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rendered.append(
            (
                row.get("market"),
                row.get("symbol"),
                row.get("hit_count"),
                row.get("avg_score"),
                row.get("max_score"),
                row.get("strategies"),
                row.get("risk_flags"),
            )
        )
    return rendered


def _stringify(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, set)):
        items = [str(item) for item in value if item not in (None, "")]
        return ", ".join(items) if items else "N/A"
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _titleize(value: str) -> str:
    return " ".join(part.capitalize() for part in value.replace("_", " ").split())


def _escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
