from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Sequence


def fmt_int(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def fmt_float(value: object, *, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    try:
        return f"{float(value):,.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: object, *, digits: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:,.{digits}f}%"
    except (TypeError, ValueError):
        return str(value)


def fmt_bool(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "yes" if bool(value) else "no"


def fmt_list(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, (list, tuple, set)):
        items = [_stringify(item) for item in value if item not in (None, "")]
        return ", ".join(items) if items else "N/A"
    return str(value)


def md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    header_row = "| " + " | ".join(_escape_md_cell(str(header)) for header in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(_escape_md_cell(_stringify(cell)) for cell in row) + " |"
        for row in rows
    ]
    return "\n".join([header_row, separator, *body]) if body else "\n".join([header_row, separator])


def render_daily_markdown(report: Any) -> str:
    payload = _payload(report)
    lines: list[str] = []
    lines.extend(_section_header("TDX Stocks Daily Report"))
    lines.extend(_summary_block(payload))
    data_quality = payload.get("data_quality")
    checks = data_quality.get("checks") if isinstance(data_quality, dict) else data_quality
    lines.extend(_with_fallback("Data Quality", _render_checks_section("Data Quality", checks)))
    lines.extend(_with_fallback("Strategy Summary", _render_kv_section("Strategy Summary", payload.get("strategy_summary"))))
    lines.extend(_with_fallback("Consensus", _render_consensus_section(payload.get("consensus_summary"))))
    portfolio_summary = payload.get("portfolio_summary") if isinstance(payload.get("portfolio_summary"), dict) else {}
    lines.extend(_with_fallback("Portfolio", _render_portfolio_section(portfolio_summary)))
    lines.extend(
        _with_fallback(
            "Risk Summary",
            _render_kv_section("Risk Summary", portfolio_summary.get("risk_summary") if isinstance(portfolio_summary, dict) else None),
        )
    )
    lines.extend(_with_fallback("Rebalance Plan", _render_kv_section("Rebalance Plan", payload.get("rebalance_summary"))))
    lines.extend(_with_fallback("Output Files", _render_outputs_section(payload.get("outputs"))))
    lines.extend(_with_fallback("Warnings", _render_simple_list_section("Warnings", payload.get("warnings"))))
    lines.extend(_with_fallback("Errors", _render_simple_list_section("Errors", payload.get("errors"))))
    lines.extend(_render_json_details("Raw JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def render_strategy_markdown(report: dict[str, Any]) -> str:
    payload = _payload(report)
    lines = []
    lines.extend(_section_header(f"Strategy Report: {payload.get('strategy_name') or 'unknown'}"))
    lines.extend(
        _render_kv_table(
            "Overview",
            [
                ("strategy_name", payload.get("strategy_name")),
                ("as_of", payload.get("as_of")),
                ("generated_at", payload.get("generated_at")),
                ("data_run_id", payload.get("data_run_id")),
                ("factor_version", payload.get("factor_version")),
                ("candidate_count", payload.get("candidate_count")),
                ("excluded_count", payload.get("excluded_count")),
            ],
        )
    )
    lines.extend(_render_strategy_identity_section(payload))
    lines.extend(_render_strategy_candidates_section(payload.get("candidates")))
    lines.extend(_render_strategy_excluded_section(payload.get("excluded_summary")))
    lines.extend(_render_strategy_risk_section(payload.get("risk_summary")))
    lines.extend(_render_json_details("Raw JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def render_portfolio_markdown(report: dict[str, Any]) -> str:
    payload = _payload(report)
    lines = []
    lines.extend(_section_header(f"Portfolio Report: {payload.get('as_of') or 'latest'}"))
    lines.extend(
        _render_kv_table(
            "Overview",
            [
                ("source", payload.get("source")),
                ("as_of", payload.get("as_of")),
                ("generated_at", payload.get("generated_at")),
                ("data_run_id", payload.get("data_run_id")),
            ],
        )
    )
    if isinstance(payload.get("summary"), dict):
        lines.extend(
            _render_kv_table(
                "Portfolio Summary",
                [(key, value) for key, value in payload["summary"].items()],
            )
        )
    if isinstance(payload.get("risk_summary"), dict):
        lines.extend(
            _render_kv_table(
                "Risk Summary",
                [(key, value) for key, value in payload["risk_summary"].items()],
            )
        )
    lines.extend(_render_portfolio_holdings_section(payload.get("holdings")))
    lines.extend(_render_json_details("Raw JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def _section_header(title: str) -> list[str]:
    return [f"# {title}", ""]


def _summary_block(payload: dict[str, Any]) -> list[str]:
    return _render_kv_table(
        "Summary",
        [
            ("as_of", payload.get("as_of")),
            ("status", payload.get("status")),
            ("data_run_id", payload.get("data_run_id")),
            ("generated_at", payload.get("generated_at")),
            ("step_count", payload.get("summary", {}).get("step_count") if isinstance(payload.get("summary"), dict) else None),
            ("warning_count", payload.get("summary", {}).get("warning_count") if isinstance(payload.get("summary"), dict) else None),
            ("error_count", payload.get("summary", {}).get("error_count") if isinstance(payload.get("summary"), dict) else None),
        ],
    )


def _render_checks_section(title: str, checks: object) -> list[str]:
    rows = list(checks or []) if isinstance(checks, list) else []
    if not rows:
        return []
    table_rows = []
    for row in rows:
        if isinstance(row, dict):
            table_rows.append(
                (
                    row.get("name") or row.get("table") or row.get("step_name") or row.get("check"),
                    row.get("passed") if "passed" in row else row.get("status"),
                    row.get("detail") or row.get("message") or row.get("summary"),
                )
            )
    if not table_rows:
        return []
    return [f"## {title}", "", md_table(("name", "status", "detail"), table_rows), ""]


def _render_kv_section(title: str, data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = [(key, value) for key, value in data.items() if key not in {"holdings", "diagnostics", "candidates"}]
    if not rows:
        return []
    return [f"## {title}", "", md_table(("field", "value"), rows), ""]


def _render_consensus_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = []
    if isinstance(data.get("rows"), list) and data["rows"]:
        for row in data["rows"][:10]:
            if isinstance(row, dict):
                rows.append(
                    (
                        row.get("market"),
                        row.get("symbol"),
                        row.get("hit_count"),
                        fmt_float(row.get("avg_score")),
                        fmt_float(row.get("max_score")),
                        fmt_list(row.get("strategies")),
                        fmt_list(row.get("risk_flags")),
                    )
                )
    if rows:
        return ["## Consensus", "", md_table(("market", "symbol", "hits", "avg_score", "max_score", "strategies", "risk_flags"), rows), ""]
    return _render_kv_section("Consensus", data)


def _render_portfolio_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    rows = [
        ("source", data.get("source")),
        ("as_of", data.get("as_of")),
        ("data_run_id", data.get("data_run_id")),
        ("holding_count", len(data.get("holdings") or [])),
        ("summary", summary),
    ]
    lines = ["## Portfolio", "", md_table(("field", "value"), rows), ""]
    lines.extend(_render_portfolio_holdings_section(data.get("holdings")))
    return lines


def _render_rebalance_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    return _render_kv_section("Rebalance Plan", data)


def _render_outputs_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = [(key, value) for key, value in data.items()]
    return ["## Output Files", "", md_table(("name", "path"), rows), ""]


def _render_simple_list_section(title: str, values: object) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        rows = [(index + 1, item) for index, item in enumerate(values)]
        return [f"## {title}", "", md_table(("item", "value"), rows), ""]
    return [f"## {title}", "", str(values), ""]


def _render_json_details(title: str, payload: object) -> list[str]:
    return [
        f"## {title}",
        "",
        "_Full JSON payload is available in the paired `.json` report file._",
        "",
    ]


def _with_fallback(title: str, lines: list[str]) -> list[str]:
    if lines:
        return lines
    return [f"## {title}", "", "_No data available._", ""]


def _render_kv_table(title: str, rows: Sequence[tuple[str, object]]) -> list[str]:
    if not rows:
        return []
    return [f"## {title}", "", md_table(("field", "value"), rows), ""]


def _render_portfolio_holdings_section(holdings: object) -> list[str]:
    if not isinstance(holdings, list) or not holdings:
        return []
    rows = []
    for row in holdings[:20]:
        if not isinstance(row, dict):
            continue
        rows.append(
            (
                row.get("market"),
                row.get("symbol"),
                fmt_pct(row.get("weight")),
                fmt_float(row.get("score")),
                row.get("source_strategy"),
                row.get("candidate_type"),
                fmt_float(row.get("risk_score")),
                fmt_list(row.get("risk_flags")),
                fmt_list(row.get("tags")),
                row.get("reason"),
            )
        )
    if not rows:
        return []
    return [
        "### Holdings",
        "",
        md_table(
            ("market", "symbol", "weight", "score", "source_strategy", "candidate_type", "risk_score", "risk_flags", "tags", "reason"),
            rows,
        ),
        "",
    ]


def _render_strategy_identity_section(payload: dict[str, Any]) -> list[str]:
    rows = [
        ("display_name", payload.get("display_name")),
        ("description", payload.get("description")),
        ("group", payload.get("group")),
        ("style", payload.get("style")),
        ("required_fields", fmt_list(payload.get("required_fields"))),
        ("optional_fields", fmt_list(payload.get("optional_fields"))),
        ("candidate_types", fmt_list(payload.get("candidate_types"))),
        ("risk_tags", fmt_list(payload.get("risk_tags"))),
        ("aliases", fmt_list(payload.get("aliases"))),
        ("supported_research_capabilities", fmt_list(payload.get("supported_research_capabilities"))),
    ]
    return ["## Strategy Definition", "", md_table(("field", "value"), rows), ""]


def _render_strategy_candidates_section(candidates: object) -> list[str]:
    if not isinstance(candidates, list) or not candidates:
        return []
    rows = []
    for row in candidates[:20]:
        if not isinstance(row, dict):
            continue
        rows.append(
            (
                row.get("market"),
                row.get("symbol"),
                fmt_float(row.get("score")),
                row.get("candidate_type"),
                fmt_list(row.get("tags")),
                fmt_list(row.get("risk_flags")),
                row.get("reason"),
            )
        )
    if not rows:
        return []
    return ["## Candidates", "", md_table(("market", "symbol", "score", "candidate_type", "tags", "risk_flags", "reason"), rows), ""]


def _render_strategy_excluded_section(excluded_summary: object) -> list[str]:
    if not isinstance(excluded_summary, dict) or not excluded_summary:
        return []
    reasons = excluded_summary.get("reasons")
    rows = [("total", excluded_summary.get("total"))]
    if isinstance(reasons, dict) and reasons:
        rows.extend((str(key), value) for key, value in reasons.items())
    return ["## Excluded Summary", "", md_table(("field", "value"), rows), ""]


def _render_strategy_risk_section(risk_summary: object) -> list[str]:
    if not isinstance(risk_summary, dict) or not risk_summary:
        return []
    rows = [(str(key), value) for key, value in risk_summary.items()]
    return ["## Risk Summary", "", md_table(("risk_tag", "count"), rows), ""]


def _payload(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if hasattr(report, "to_dict"):
        return dict(report.to_dict())
    return dict(report)


def _stringify(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (list, tuple, set)):
        items = [_stringify(item) for item in value if item not in (None, "")]
        return ", ".join(items) if items else "N/A"
    if isinstance(value, dict):
        if not value:
            return "N/A"
        parts = [f"{key}: {_stringify(item)}" for key, item in value.items()]
        return "<br>".join(parts)
    if isinstance(value, float):
        return fmt_float(value)
    return str(value)


def _escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
