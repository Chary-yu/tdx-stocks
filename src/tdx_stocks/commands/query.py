from __future__ import annotations

import argparse
from pathlib import Path
from collections.abc import Callable

from ..config import load_config
from ..console import print_json, print_key_values
from ..query import (
    TABLES,
    build_select_sql,
    build_stock_sql,
    disk_usage,
    ensure_read_only_sql,
    export_query_csv,
    fetch_dicts,
    format_bytes,
    normalize_output_data,
    open_query_context,
    parquet_glob,
    print_rows,
    sql_literal,
    table_columns,
    table_summary,
)
from .common import add_config_arg, add_query_args, add_stock_args, legacy_notice as _legacy_notice


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


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [column.strip() for column in value.split(",")]
    return [column for column in columns if column]


def summarize_cached_table(con, root: Path, date_column: str) -> dict[str, object]:
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    summary: dict[str, object] = {
        "exists": bool(files),
        "parquet_files": len(files),
        "rows": 0,
        "symbols": 0,
        "min_date": None,
        "max_date": None,
        "cache_path": root.as_posix(),
    }
    if not files:
        return summary

    source = f"read_parquet('{sql_literal(parquet_glob(root))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            min({date_column}) AS min_date,
            max({date_column}) AS max_date
        FROM {source}
        """
    ).fetchone()
    summary.update(
        {
            "rows": row[0],
            "symbols": row[1],
            "min_date": str(row[2]) if row[2] is not None else None,
            "max_date": str(row[3]) if row[3] is not None else None,
        }
    )
    return summary


def _is_select_like(sql: str) -> bool:
    stripped = sql.lstrip().lower()
    return stripped.startswith(("select", "with"))


def cmd_status(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        manifest = ctx.manifest
        summary = manifest.get("summary", {})
        rows = [
            ("run_id", manifest.get("run_id")),
            ("generated_at", summary.get("generated_at")),
            ("version_dir", manifest.get("version_dir")),
            ("data_root", config.paths.data_root),
            ("disk_usage", format_bytes(disk_usage(config.paths.data_root))),
        ]
        checks = summary.get("checks", [])
        check_rows = []
        for check in checks:
            metrics = check.get("metrics", {})
            check_rows.append(
                {
                    "name": check.get("name"),
                    "rows": metrics.get("rows"),
                    "symbols": metrics.get("symbols"),
                    "errors": len(check.get("errors", [])),
                    "warnings": len(check.get("warnings", [])),
                }
            )
        if args.json:
            print_json(
                normalize_output_data(
                    {
                        "run_id": manifest.get("run_id"),
                        "generated_at": summary.get("generated_at"),
                        "version_dir": manifest.get("version_dir"),
                        "data_root": config.paths.data_root.as_posix(),
                        "disk_usage": format_bytes(disk_usage(config.paths.data_root)),
                        "checks": check_rows,
                    }
                )
            )
        else:
            print_key_values("status", rows)
            if check_rows:
                print_rows(["name", "rows", "symbols", "errors", "warnings"], check_rows)
    finally:
        ctx.close()
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [table_summary(ctx.con, ctx.manifest, table) for table in TABLES]
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(["table", "rows", "symbols", "min_date", "max_date", "disk", "path"], rows)
    finally:
        ctx.close()
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [{"column": name, "type": type_} for name, type_ in table_columns(ctx.con, args.table)]
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(["column", "type"], rows)
    finally:
        ctx.close()
    return 0


def cmd_head(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_select_sql(
            ctx.con,
            args.table,
            columns=parse_columns(args.columns),
            symbol=args.symbol,
            market=args.market,
            from_date=args.from_date,
            to_date=args.to_date,
            where=args.where,
            order_by=args.order_by,
            desc=args.desc,
            limit=args.limit,
        )
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = ensure_read_only_sql(args.sql)
        if args.limit and _is_select_like(sql) and " limit " not in f" {sql.lower()} ":
            sql = f"{sql.rstrip().rstrip(';')}\nLIMIT {args.limit}"
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_select_sql(
            ctx.con,
            args.table,
            columns=parse_columns(args.columns),
            symbol=args.symbol,
            market=args.market,
            from_date=args.from_date,
            to_date=args.to_date,
            where=args.where,
            order_by=args.order_by,
            desc=args.desc,
            limit=None if args.no_limit else args.limit,
        )
        count = export_query_csv(ctx.con, sql, args.to)
        if getattr(args, "json", False):
            print_json({"exported_rows": count, "path": args.to.as_posix()})
        else:
            print(f"exported rows={count} path={args.to}")
    finally:
        ctx.close()
    return 0


def cmd_stock(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_stock_sql(
            ctx.con,
            args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
            desc=args.desc,
            limit=None if args.no_limit else args.limit,
            adjust=args.adjust,
        )
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0
