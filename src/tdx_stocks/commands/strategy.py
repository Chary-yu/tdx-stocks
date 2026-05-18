from __future__ import annotations

import argparse
from typing import Callable

from .common import add_config_arg
from ..strategies.registry import list_strategies


def register_strategy_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_strategy_list: Callable[[argparse.Namespace], int],
    cmd_strategy_run: Callable[[argparse.Namespace], int],
) -> None:
    strategy_parser = subparsers.add_parser(
        "strategy",
        help="Strategy analysis commands.",
        description="Commands that generate read-only observation pools from the latest dataset.",
    )
    strategy_subparsers = strategy_parser.add_subparsers(dest="strategy_command", required=True)

    list_parser = strategy_subparsers.add_parser("list", help="List available strategy presets.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_strategy_list)

    run_parser = strategy_subparsers.add_parser("run", help="Run a strategy and emit a report.")
    run_subparsers = run_parser.add_subparsers(dest="strategy_name", required=True)

    for definition in list_strategies():
        strategy_parser = run_subparsers.add_parser(
            definition.name,
            help=definition.description,
            aliases=list(definition.aliases),
            description=definition.description,
        )
        _add_common_run_args(strategy_parser)
        strategy_parser.set_defaults(func=cmd_strategy_run, strategy_name=definition.name)


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    from pathlib import Path

    add_config_arg(parser)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument(
        "--candidate-type",
        choices=("strong_trend", "breakout_watch", "pullback_watch"),
    )
    parser.add_argument("--include-excluded", action="store_true")
    parser.add_argument("--show-excluded-limit", type=int, default=20)
    parser.add_argument("--explain-symbol")
    parser.add_argument("--to", type=Path)
