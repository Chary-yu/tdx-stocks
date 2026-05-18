from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..console import print_notice
from ..lock import acquire_database_lock
from ..query import TABLES


def add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)


def add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--limit-symbols", type=int)
    parser.add_argument("--overwrite-staging", action="store_true")


def add_query_args(parser: argparse.ArgumentParser, default_limit: int) -> None:
    parser.add_argument("table", choices=TABLES)
    parser.add_argument("--limit", type=int, default=default_limit)
    parser.add_argument("--columns", help="Comma-separated output columns.")
    parser.add_argument("--symbol")
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--where", help="Extra SQL WHERE expression.")
    parser.add_argument("--order-by")
    parser.add_argument("--desc", action="store_true")
    parser.add_argument("--json", action="store_true")


def add_stock_args(parser: argparse.ArgumentParser, default_limit: int = 100) -> None:
    parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    parser.add_argument("--limit", type=int, default=default_limit)
    parser.add_argument("--adjust", choices=("raw", "qfq", "hfq"), default="qfq")
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--asc", dest="desc", action="store_false")
    parser.set_defaults(desc=True)
    parser.add_argument("--no-limit", action="store_true")
    parser.add_argument("--json", action="store_true")


def legacy_notice(args: argparse.Namespace) -> None:
    target = getattr(args, "_legacy_target", None)
    if target and not getattr(args, "json", False):
        print_notice(f"提示: 该命令已升级。建议下次使用 {target}。")


def lock_path(config) -> Path:
    return config.paths.data_root / ".lock"


def write_lock(config, command: str):
    return acquire_database_lock(lock_path(config), command)


def stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
