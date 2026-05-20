from __future__ import annotations

import argparse
from pathlib import Path

from ..config import load_config
from ..console import print_json
from ..query import (
    TABLES,
    build_select_sql,
    build_stock_sql,
    ensure_read_only_sql,
    export_query_csv,
    fetch_dicts,
    normalize_output_data,
    open_query_context,
    parquet_glob,
    print_rows,
    sql_literal,
    table_columns,
    table_summary,
)
from .common import add_config_arg, add_output_arg, add_query_args, add_stock_args
from .common import validate_output_alias


def register_query_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    tables: tuple[str, ...],
    hidden: bool = False,
) -> None:
    query_parser = subparsers.add_parser(
        "query",
        help=argparse.SUPPRESS if hidden else "Read-only inspection and query commands.",
        description="Commands that inspect the latest versioned dataset.",
    )
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    stock_parser = query_subparsers.add_parser(
        "stock",
        help="Show merged daily rows and factors for one stock code.",
    )
    add_config_arg(stock_parser)
    add_stock_args(stock_parser)
    stock_parser.set_defaults(func=cmd_stock)

    table_parser = query_subparsers.add_parser("table", help="Show rows from a latest table.")
    add_config_arg(table_parser)
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
    sql_parser.add_argument(
        "--unsafe-sql",
        action="store_true",
        help="Allow arbitrary SQL. Disabled by default because DuckDB can expose file and function access.",
    )
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = query_subparsers.add_parser("export", help="Export a filtered table query to CSV.")
    add_config_arg(export_parser)
    add_query_args(export_parser, default_limit=1000)
    add_output_arg(export_parser, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)


    factor_parser = query_subparsers.add_parser(
        "factor",
        help="Factor catalog, schema inspection, and ranking commands.",
        description="Commands for factor catalog browsing and ranking.",
    )
    factor_subparsers = factor_parser.add_subparsers(dest="factor_command", required=True)

    factor_list_parser = factor_subparsers.add_parser("list", help="List available factors.")
    factor_list_parser.add_argument("--json", action="store_true")
    factor_list_parser.set_defaults(func=cmd_factor_list)

    factor_describe_parser = factor_subparsers.add_parser("describe", help="Describe one factor.")
    factor_describe_parser.add_argument("factor")
    factor_describe_parser.add_argument("--json", action="store_true")
    factor_describe_parser.set_defaults(func=cmd_factor_describe)

    factor_schema_parser = factor_subparsers.add_parser("schema", help="Show factor table schema.")
    add_config_arg(factor_schema_parser)
    factor_schema_parser.add_argument("--json", action="store_true")
    factor_schema_parser.set_defaults(func=cmd_factor_schema)

    factor_rank_parser = factor_subparsers.add_parser("rank", help="Rank one factor on a chosen date.")
    add_config_arg(factor_rank_parser)
    factor_rank_parser.add_argument("factor")
    factor_rank_parser.add_argument("--as-of", default="latest")
    factor_rank_parser.add_argument("--limit", type=int, default=50)
    factor_rank_parser.add_argument("--market", choices=("sh", "sz", "bj"))
    factor_rank_parser.add_argument("--json", action="store_true")
    factor_rank_parser.set_defaults(func=cmd_factor_rank)


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


def _sql_has_top_level_keyword(sql: str, keyword: str) -> bool:
    target = keyword.lower()
    depth = 0
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ""
        if in_single:
            if char == "'" and nxt == "'":
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            if char == '"':
                in_double = False
            index += 1
            continue
        if char == "-" and nxt == "-":
            newline = sql.find("\n", index + 2)
            if newline == -1:
                return False
            index = newline + 1
            continue
        if char == "/" and nxt == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                return False
            index = end + 2
            continue
        if char == "'":
            in_single = True
            index += 1
            continue
        if char == '"':
            in_double = True
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            index += 1
            continue
        if depth == 0 and (char.isalpha() or char == "_"):
            start = index
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] == "_"):
                index += 1
            if sql[start:index].lower() == target:
                return True
            continue
        index += 1
    return False


def cmd_tables(args: argparse.Namespace) -> int:
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
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        if not getattr(args, "unsafe_sql", False):
            raise ValueError("query sql is disabled by default; pass --unsafe-sql to run arbitrary SQL")
        sql = ensure_read_only_sql(args.sql)
        if args.limit and _is_select_like(sql) and not _sql_has_top_level_keyword(sql, "limit"):
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
    validate_output_alias(args)
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
        count = export_query_csv(ctx.con, sql, args.output)
        if getattr(args, "json", False):
            print_json({"exported_rows": count, "path": args.output.as_posix()})
        else:
            print(f"exported rows={count} path={args.output}")
    finally:
        ctx.close()
    return 0


def cmd_stock(args: argparse.Namespace) -> int:
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


def cmd_factor_list(args: argparse.Namespace) -> int:
    from .factors import cmd_factors_list as _cmd_factors_list

    return _cmd_factors_list(args)


def cmd_factor_describe(args: argparse.Namespace) -> int:
    from .factors import cmd_factors_describe as _cmd_factors_describe

    return _cmd_factors_describe(args)


def cmd_factor_schema(args: argparse.Namespace) -> int:
    from .factors import cmd_factors_schema as _cmd_factors_schema

    return _cmd_factors_schema(args)


def cmd_factor_rank(args: argparse.Namespace) -> int:
    from .factors import cmd_factors_rank as _cmd_factors_rank

    return _cmd_factors_rank(args)
