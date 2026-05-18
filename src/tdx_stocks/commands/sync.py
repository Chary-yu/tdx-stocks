from __future__ import annotations

import argparse
from pathlib import Path

from ..config import load_config
from ..console import print_json
from ..pipeline import parse_iso_date
from ..query import normalize_output_data
from ..sync import build_sync_plan, execute_sync
from .common import write_lock as _write_lock


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    plan = build_sync_plan(config)
    if args.dry_run or not plan.needs_write:
        print_json(_build_sync_report(plan, status="dry-run" if args.dry_run else "up-to-date"))
        return 0

    with _write_lock(config, "sync"):
        execution = execute_sync(
            config,
            plan,
            from_date=parse_iso_date(args.from_date),
            to_date=parse_iso_date(args.to_date),
            limit_symbols=args.limit_symbols,
            overwrite_staging=args.overwrite_staging or None,
            progress=stderr_progress,
        )

    report = _build_sync_report(plan, status="updated")
    report["update_report"] = normalize_output_data(execution.update_report)
    report["build_report"] = normalize_output_data(execution.build_report)
    print_json(report)
    return 0


def _build_sync_report(plan, status: str) -> dict[str, object]:
    report = plan.to_dict()
    report["status"] = status
    return report


def stderr_progress(message: str) -> None:
    from sys import stderr

    print(message, file=stderr, flush=True)


def register_sync_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sync_parser = subparsers.add_parser("sync", help="Synchronize export-derived data and rebuild.")
    sync_parser.add_argument("--config", type=Path)
    sync_parser.add_argument("--from-date", dest="from_date")
    sync_parser.add_argument("--to-date", dest="to_date")
    sync_parser.add_argument("--limit-symbols", type=int)
    sync_parser.add_argument("--overwrite-staging", action="store_true")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.add_argument("--json", action="store_true")
    sync_parser.set_defaults(func=cmd_sync)
