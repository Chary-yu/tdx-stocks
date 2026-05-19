from __future__ import annotations

import argparse
from pathlib import Path

from ..console import print_json
from ..io_utils import write_json_atomic, write_text_atomic
from ..runner import (
    build_latest_run_report,
    build_run_plan,
    dispatch_run,
    load_run_config,
    render_run_plan,
    save_latest_run_report,
)


def cmd_run(args: argparse.Namespace) -> int:
    run_config = load_run_config(Path(args.config))
    plan = build_run_plan(run_config)
    if args.explain or args.dry_run:
        if args.json:
            print_json(plan)
        else:
            print(render_run_plan(plan))
        return 0
    result = dispatch_run(run_config, dry_run=args.dry_run)
    if args.output is not None:
        if args.json:
            write_json_atomic(args.output, result.to_dict())
        else:
            write_text_atomic(args.output, f"{result.task_type}: {result.status}\n")
    save_latest_run_report(run_config.app_config.paths.data_root, build_latest_run_report(run_config, result))
    if args.json:
        print_json(result.to_dict())
    else:
        print(f"{result.task_type}: {result.status}")
    return 0


def register_run_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run a TOML experiment config.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.set_defaults(func=cmd_run)
