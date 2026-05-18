from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .common import add_build_args, add_config_arg


def register_data_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_build: Callable[[argparse.Namespace], int],
    cmd_rebuild: Callable[[argparse.Namespace], int],
    cmd_update_actions: Callable[[argparse.Namespace], int],
    cmd_actions_status: Callable[[argparse.Namespace], int],
) -> None:
    data_parser = subparsers.add_parser(
        "data",
        help="Data pipeline commands.",
        description="Commands that refresh caches and rebuild versioned data.",
    )
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)

    update_parser = data_subparsers.add_parser("update", help="Refresh cached corporate actions.")
    add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "file", "export"),
        default="local",
        help="Update source label for the report.",
    )
    update_parser.add_argument(
        "--input",
        type=Path,
        help="Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv.",
    )
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.add_argument("--json", action="store_true")
    update_parser.set_defaults(func=cmd_update_actions)

    status_parser = data_subparsers.add_parser(
        "status",
        help="Show cached corporate actions and adjustment factor status.",
    )
    add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_actions_status)

    build_parser = data_subparsers.add_parser("build", help="Build a versioned local dataset.")
    add_config_arg(build_parser)
    add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_build)

    rebuild_parser = data_subparsers.add_parser(
        "rebuild",
        help="Clear the current database and rebuild from local TDX data.",
    )
    add_config_arg(rebuild_parser)
    add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=cmd_rebuild)


def register_legacy_data_aliases(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_build: Callable[[argparse.Namespace], int],
    cmd_rebuild: Callable[[argparse.Namespace], int],
    cmd_update_actions: Callable[[argparse.Namespace], int],
    cmd_actions_status: Callable[[argparse.Namespace], int],
) -> None:
    build_parser = subparsers.add_parser("build", help=argparse.SUPPRESS)
    build_parser._legacy_target = "data build"
    add_config_arg(build_parser)
    add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_build)

    rebuild_parser = subparsers.add_parser("rebuild", help=argparse.SUPPRESS)
    rebuild_parser._legacy_target = "data rebuild"
    add_config_arg(rebuild_parser)
    add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=cmd_rebuild)

    update_parser = subparsers.add_parser("update-actions", help=argparse.SUPPRESS)
    update_parser._legacy_target = "data update"
    add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "file", "export"),
        default="local",
    )
    update_parser.add_argument(
        "--input",
        type=Path,
        help="Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv.",
    )
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.add_argument("--json", action="store_true")
    update_parser.set_defaults(func=cmd_update_actions)

    actions_status_parser = subparsers.add_parser("actions-status", help=argparse.SUPPRESS)
    actions_status_parser._legacy_target = "data status"
    add_config_arg(actions_status_parser)
    actions_status_parser.add_argument("--json", action="store_true")
    actions_status_parser.set_defaults(func=cmd_actions_status)
