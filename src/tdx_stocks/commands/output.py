from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

from ..console import print_json, print_key_values, print_table
from ..io_utils import write_json_atomic, write_text_atomic
from ..query import normalize_output_data


def write_rows(rows: list[dict[str, object]], *, columns: list[str], format_name: str, to: Path | None) -> None:
    _validate_format_name(format_name)
    if format_name == "json":
        payload = normalize_output_data(rows)
        if to is not None:
            write_json_atomic(to, payload)
        else:
            print_json(payload)
        return
    if format_name == "csv":
        write_csv(rows, columns, to)
        return
    if to is not None:
        buffer = StringIO()
        print_table(columns, rows, stream=buffer)
        write_text_atomic(to, buffer.getvalue())
        return
    print_table(columns, rows)


def write_csv(rows: list[dict[str, object]], columns: list[str], to: Path | None) -> None:
    if to is None:
        stream = StringIO()
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in columns})
        print(stream.getvalue(), end="")
        return
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
    write_text_atomic(to, buffer.getvalue())


def emit_report_table(report: dict[str, object], *, format_name: str, to: Path | None) -> None:
    _validate_format_name(format_name)
    if format_name == "json":
        if to is not None:
            write_json_atomic(to, report)
        else:
            print_json(report)
        return
    if format_name == "csv":
        rows = report.get("rows") or report.get("periods") or report.get("trades") or []
        if not isinstance(rows, list):
            rows = []
        columns = list(rows[0].keys()) if rows else []
        write_csv(rows, columns, to)
        return
    rows = report.get("rows")
    if isinstance(rows, list) and rows:
        columns = list(rows[0].keys())
        write_rows(rows, columns=columns, format_name="table", to=to)
        return
    periods = report.get("periods")
    if isinstance(periods, list) and periods:
        summary = [
            ("schema_version", report.get("schema_version")),
            ("strategy_name", report.get("strategy_name")),
            ("strategy_names", ",".join(report.get("strategy_names") or [])),
            ("start_date", report.get("start_date")),
            ("end_date", report.get("end_date")),
            ("trade_count", report.get("trade_count")),
            ("period_count", report.get("period_count")),
            ("empty_period_count", report.get("empty_period_count")),
            ("total_return", report.get("total_return")),
            ("annual_return", report.get("annual_return")),
            ("max_drawdown", report.get("max_drawdown")),
            ("win_rate", report.get("win_rate")),
            ("avg_period_return", report.get("avg_period_return")),
            ("best_period_return", report.get("best_period_return")),
            ("worst_period_return", report.get("worst_period_return")),
            ("turnover", report.get("turnover")),
        ]
        if to is None:
            print_key_values("backtest report", summary)
            print_table(list(periods[0].keys()), periods)
        else:
            buffer = StringIO()
            for key, value in summary:
                buffer.write(f"{key}={value}\n")
            buffer.write("\n")
            print_table(list(periods[0].keys()), periods, stream=buffer)
            write_text_atomic(to, buffer.getvalue())
        return
    print_json(report)


def _validate_format_name(format_name: str) -> None:
    if format_name not in {"table", "json", "csv"}:
        raise ValueError(f"unsupported output format: {format_name}")
