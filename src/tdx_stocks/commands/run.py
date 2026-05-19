from __future__ import annotations

import argparse
from pathlib import Path

from ..console import print_json
from ..io_utils import write_json_atomic, write_text_atomic
from ..runner import dispatch_run, load_run_config


def cmd_run(args: argparse.Namespace) -> int:
    run_config = load_run_config(Path(args.config))
    result = dispatch_run(run_config, dry_run=args.dry_run)
    if args.output is not None:
        if args.json:
            write_json_atomic(args.output, result.to_dict())
        else:
            write_text_atomic(args.output, str(result.summary))
    if args.json:
        print_json(result.to_dict())
    else:
        print(f"{result.task_type}: {result.status}")
    return 0


def register_run_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("run", help="Run a TOML experiment config.")
    parser.add_argument("config", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--set", dest="set_values", action="append", default=[])
    parser.set_defaults(func=cmd_run)
