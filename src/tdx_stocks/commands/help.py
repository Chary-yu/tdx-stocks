from __future__ import annotations

import argparse


HELP_TOPICS: dict[str, str] = {
    "overview": (
        "tdx-stocks is organized around a small command surface.\n\n"
        "Typical flow:\n"
        "  init -> sync -> run daily -> report -> status -> ui\n"
        "  query stock <code> for a merged row view\n"
        "  query factors / query factor <name> / query rank <name>\n"
        "  query strategies / query strategy <name> [--symbol ... --explain]\n"
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
        "  tdx-stocks query factors\n"
        "  tdx-stocks query factor rs_score\n"
        "  tdx-stocks query rank rs_score --as-of latest\n"
        "  tdx-stocks query strategies\n"
        "  tdx-stocks query strategy trend-strength --symbol 600519.SH --explain\n"
    ),
    "report": (
        "Render the latest daily report or inspect strategy reports.\n\n"
        "Examples:\n"
        "  tdx-stocks report\n"
        "  tdx-stocks report --format json\n"
        "  tdx-stocks report strategy --list\n"
        "  tdx-stocks report strategy trend-strength --as-of latest\n"
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
    "workflow": (
        "Recommended workspace workflow.\n\n"
        "Typical order:\n"
        "  1. tdx-stocks init\n"
        "  2. tdx-stocks sync\n"
        "  3. tdx-stocks run daily --explain\n"
        "  4. tdx-stocks query stock 600519.SH\n"
        "  5. tdx-stocks query factors\n"
        "  6. tdx-stocks query strategy trend-strength --symbol 600519.SH --explain\n"
        "  7. tdx-stocks report\n"
        "  8. tdx-stocks status\n"
        "  9. tdx-stocks ui\n"
    ),
}


def register_help_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("help", help="Show built-in guidance topics.")
    parser.add_argument("topic", nargs="?", choices=tuple(HELP_TOPICS), default="overview")
    parser.set_defaults(func=cmd_help)


def cmd_help(args: argparse.Namespace) -> int:
    print(HELP_TOPICS[args.topic].rstrip())
    return 0
