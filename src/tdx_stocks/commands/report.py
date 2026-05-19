from __future__ import annotations

import argparse
from pathlib import Path

from ..config import load_config
from ..console import print_json
from ..daily import load_daily_report, render_daily_json, render_daily_markdown
from ..io_utils import write_json_atomic, write_text_atomic
from ..query import normalize_output_data
from .common import add_config_arg


def register_report_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("report", help="Show the latest daily report.")
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    parser.set_defaults(func=cmd_report)


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
    else:
        markdown = render_daily_markdown(_to_report(doc))
        if args.output is not None:
            write_text_atomic(args.output, markdown)
        print(markdown, end="")
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
