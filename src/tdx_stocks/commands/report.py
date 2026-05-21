from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ..config import load_config
from ..console import print_json, print_table
from ..daily import load_daily_report, render_daily_json
from ..daily.store import daily_md_path, latest_daily_md_path
from ..io_utils import write_json_atomic, write_text_atomic
from ..query import normalize_output_data
from ..reports.opening import open_report_if_needed, print_report_path
from ..reports.renderers import render_daily_markdown, render_strategy_markdown
from ..strategies.storage import list_saved_reports, load_saved_report, report_path
from .common import add_config_arg


def register_report_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "report",
        help="Show daily or strategy reports.",
        description="Render the latest daily report or inspect saved strategy reports.",
    )
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-open", action="store_true")
    parser.set_defaults(func=cmd_report)
    report_subparsers = parser.add_subparsers(dest="report_command")
    strategy_parser = report_subparsers.add_parser("strategy", help="Inspect saved strategy reports.")
    add_config_arg(strategy_parser)
    strategy_parser.add_argument("strategy_name", nargs="?")
    strategy_parser.add_argument("--list", action="store_true")
    strategy_parser.add_argument("--as-of", default="latest")
    strategy_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    strategy_parser.add_argument("--output", type=Path)
    strategy_parser.add_argument("--no-open", action="store_true")
    strategy_parser.set_defaults(func=cmd_report_strategy)


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    doc = load_daily_report(config.paths.data_root, args.as_of)
    if doc is None:
        raise FileNotFoundError(f"daily report not found for as_of={args.as_of!r}")
    if args.format == "json":
        payload = render_daily_json(_to_report(doc))
        if args.output is not None:
            write_json_atomic(args.output, payload)
        print_json(normalize_output_data(payload))
        return 0

    markdown = render_daily_markdown(_to_report(doc))
    output_path = args.output or _daily_report_markdown_path(config.paths.data_root, str(doc.get("as_of") or args.as_of))
    write_text_atomic(output_path, markdown)
    print_report_path(output_path, json_mode=False)
    open_report_if_needed(args, output_path, json_mode=False)
    return 0


def cmd_report_strategy(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    if args.list:
        rows = list_saved_reports(config.paths.data_root)
        if args.format == "json":
            payload = normalize_output_data(rows)
            if args.output is not None:
                write_json_atomic(args.output, payload)
            print_json(payload)
        else:
            if args.output is not None:
                buffer = "\n".join(
                    f"{row.get('strategy_name')}\t{row.get('as_of')}\t{row.get('generated_at')}\t{row.get('path')}"
                    for row in rows
                )
                write_text_atomic(args.output, buffer + ("\n" if buffer else ""))
            print_table(
                ["strategy_name", "as_of", "generated_at", "data_run_id", "candidate_count", "excluded_count", "path"],
                rows,
            )
        return 0

    if not args.strategy_name:
        raise ValueError("report strategy requires a strategy name or --list")
    report = load_saved_report(config.paths.data_root, args.strategy_name, as_of=args.as_of)
    if report is None:
        raise FileNotFoundError(
            f"saved report not found for strategy={args.strategy_name!r}, as_of={args.as_of!r}"
        )
    if args.format == "json":
        if args.output is not None:
            write_json_atomic(args.output, report)
        print_json(normalize_output_data(report))
        return 0

    markdown = render_strategy_markdown(report)
    output_path = args.output or _strategy_report_markdown_path(config.paths.data_root, args.strategy_name, args.as_of)
    write_text_atomic(output_path, markdown)
    print_report_path(output_path, json_mode=False)
    open_report_if_needed(args, output_path, json_mode=False)
    return 0


def _to_report(doc) -> object:
    from ..daily.models import DailyRunReport

    return DailyRunReport(
        schema_version=str(doc.get("schema_version") or "daily-report-v1"),
        app_version=str(doc.get("app_version") or ""),
        as_of=str(doc.get("as_of") or "latest"),
        generated_at=str(doc.get("generated_at") or ""),
        data_run_id=doc.get("data_run_id"),
        status=str(doc.get("status") or ""),
        steps=list(doc.get("steps") or []),
        summary=dict(doc.get("summary") or {}),
        data_quality=dict(doc.get("data_quality") or {}),
        strategy_summary=dict(doc.get("strategy_summary") or {}),
        consensus_summary=dict(doc.get("consensus_summary") or {}),
        portfolio_summary=dict(doc.get("portfolio_summary") or {}),
        rebalance_summary=dict(doc.get("rebalance_summary") or {}),
        warnings=list(doc.get("warnings") or []),
        errors=list(doc.get("errors") or []),
        outputs=dict(doc.get("outputs") or {}),
    )


def _daily_report_markdown_path(data_root: Path, as_of: str) -> Path:
    if as_of == "latest":
        return latest_daily_md_path(data_root)
    return daily_md_path(data_root, date.fromisoformat(as_of))


def _strategy_report_markdown_path(data_root: Path, strategy_name: str, as_of: str) -> Path:
    path = report_path(data_root, strategy_name, as_of=None if as_of == "latest" else date.fromisoformat(as_of))
    return path.with_suffix(".md")
