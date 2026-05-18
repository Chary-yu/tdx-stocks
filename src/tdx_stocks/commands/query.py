from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .common import add_config_arg, add_query_args, add_stock_args


def register_query_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    tables: tuple[str, ...],
    cmd_status: Callable[[argparse.Namespace], int],
    cmd_stock: Callable[[argparse.Namespace], int],
    cmd_head: Callable[[argparse.Namespace], int],
    cmd_tables: Callable[[argparse.Namespace], int],
    cmd_schema: Callable[[argparse.Namespace], int],
    cmd_sql: Callable[[argparse.Namespace], int],
    cmd_export: Callable[[argparse.Namespace], int],
) -> None:
    query_parser = subparsers.add_parser(
        "query",
        help="Read-only inspection and query commands.",
        description="Commands that inspect the latest versioned dataset.",
    )
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    status_parser = query_subparsers.add_parser("status", help="Show latest dataset status.")
    add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    price_parser = query_subparsers.add_parser(
        "price",
        help="Show merged daily rows and factors for one stock code.",
    )
    add_stock_args(price_parser)
    price_parser.set_defaults(func=cmd_stock)

    table_parser = query_subparsers.add_parser("table", help="Show rows from a latest table.")
    add_query_args(table_parser, default_limit=20)
    table_parser.set_defaults(func=cmd_head)

    tables_parser = query_subparsers.add_parser("tables", help="Show latest table summaries.")
    add_config_arg(tables_parser)
    tables_parser.add_argument("--json", action="store_true")
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = query_subparsers.add_parser("schema", help="Show a table schema.")
    add_config_arg(schema_parser)
    schema_parser.add_argument("table", choices=tables)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=cmd_schema)

    sql_parser = query_subparsers.add_parser("sql", help="Run SQL against latest table views.")
    add_config_arg(sql_parser)
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = query_subparsers.add_parser("export", help="Export a filtered table query to CSV.")
    add_query_args(export_parser, default_limit=1000)
    export_parser.add_argument("--to", type=Path, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)


def register_legacy_query_aliases(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    tables: tuple[str, ...],
    cmd_status: Callable[[argparse.Namespace], int],
    cmd_tables: Callable[[argparse.Namespace], int],
    cmd_schema: Callable[[argparse.Namespace], int],
    cmd_head: Callable[[argparse.Namespace], int],
    cmd_stock: Callable[[argparse.Namespace], int],
    cmd_sql: Callable[[argparse.Namespace], int],
    cmd_export: Callable[[argparse.Namespace], int],
) -> None:
    status_parser = subparsers.add_parser("status", help=argparse.SUPPRESS)
    status_parser._legacy_target = "query status"
    add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    tables_parser = subparsers.add_parser("tables", help=argparse.SUPPRESS)
    tables_parser._legacy_target = "query tables"
    add_config_arg(tables_parser)
    tables_parser.add_argument("--json", action="store_true")
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = subparsers.add_parser("schema", help=argparse.SUPPRESS)
    schema_parser._legacy_target = "query schema"
    add_config_arg(schema_parser)
    schema_parser.add_argument("table", choices=tables)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=cmd_schema)

    head_parser = subparsers.add_parser("head", help=argparse.SUPPRESS)
    head_parser._legacy_target = "query table"
    add_config_arg(head_parser)
    add_query_args(head_parser, default_limit=20)
    head_parser.set_defaults(func=cmd_head)

    stock_parser = subparsers.add_parser("stock", help=argparse.SUPPRESS)
    stock_parser._legacy_target = "query price"
    add_config_arg(stock_parser)
    add_stock_args(stock_parser)
    stock_parser.set_defaults(func=cmd_stock)

    sql_parser = subparsers.add_parser("sql", help=argparse.SUPPRESS)
    sql_parser._legacy_target = "query sql"
    add_config_arg(sql_parser)
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = subparsers.add_parser("export", help=argparse.SUPPRESS)
    export_parser._legacy_target = "query export"
    add_config_arg(export_parser)
    add_query_args(export_parser, default_limit=1000)
    export_parser.add_argument("--to", type=Path, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)
