from __future__ import annotations

import argparse


HELP_TOPICS: dict[str, str] = {
    "overview": (
        "tdx-stocks is organized around a small command surface.\n\n"
        "Typical flow:\n"
        "  init -> sync -> run daily -> report -> status -> ui\n"
        "  query stock <code> for a merged row view\n"
        "  query factor rank <factor> for factor ranking\n"
    ),
    "init": (
        "Create a workspace with default config and example experiment files.\n\n"
        "Examples:\n"
        "  tdx-stocks init\n"
        "  tdx-stocks init --profile portfolio\n"
    ),
    "sync": (
        "Refresh local caches and rebuild the latest dataset when needed.\n\n"
        "Examples:\n"
        "  tdx-stocks sync\n"
        "  tdx-stocks sync --dry-run\n"
    ),
    "run": (
        "Run a preset or custom TOML workflow config.\n\n"
        "Built-in presets:\n"
        "  daily, signal, portfolio, rebalance, backtest, grid\n"
        "Examples:\n"
        "  tdx-stocks run daily --explain\n"
        "  tdx-stocks run experiments/backtest.toml\n"
    ),
    "query": (
        "Inspect the latest dataset and factor catalog.\n\n"
        "Examples:\n"
        "  tdx-stocks query stock 600519.SH\n"
        "  tdx-stocks query table raw_daily --limit 20\n"
        "  tdx-stocks query factor rank rs_score --as-of latest\n"
    ),
    "report": (
        "Render the latest daily report in markdown or JSON.\n\n"
        "Examples:\n"
        "  tdx-stocks report\n"
        "  tdx-stocks report --format json\n"
    ),
    "status": (
        "Show the latest workspace, dataset, and report status.\n\n"
        "Examples:\n"
        "  tdx-stocks status\n"
        "  tdx-stocks status --json\n"
    ),
    "ui": (
        "Launch the read-only Streamlit UI.\n\n"
        "Examples:\n"
        "  tdx-stocks ui\n"
    ),
    "doctor": (
        "Check required paths and workspace configuration.\n\n"
        "Examples:\n"
        "  tdx-stocks doctor\n"
    ),
    "help": (
        "Show built-in help topics.\n\n"
        "Examples:\n"
        "  tdx-stocks help\n"
        "  tdx-stocks help query\n"
    ),
}


def register_help_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("help", help="Show built-in guidance topics.")
    parser.add_argument("topic", nargs="?", choices=tuple(HELP_TOPICS), default="overview")
    parser.set_defaults(func=cmd_help)


def cmd_help(args: argparse.Namespace) -> int:
    print(HELP_TOPICS[args.topic].rstrip())
    return 0
