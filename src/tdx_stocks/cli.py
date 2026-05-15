from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import load_config, write_default_config
from .pipeline import build_dataset, parse_iso_date
from .query import (
    TABLES,
    build_select_sql,
    disk_usage,
    export_query_csv,
    fetch_dicts,
    format_bytes,
    open_query_context,
    print_rows,
    table_columns,
    table_summary,
)
from .tdx_day import iter_day_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tdx-stocks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-config", help="Write a default TOML config.")
    init_parser.add_argument("--path", type=Path, default=Path("tdx_stocks.toml"))
    init_parser.set_defaults(func=cmd_init_config)

    doctor_parser = subparsers.add_parser("doctor", help="Check paths and dependency imports.")
    doctor_parser.add_argument("--config", type=Path)
    doctor_parser.set_defaults(func=cmd_doctor)

    build_parser = subparsers.add_parser("build", help="Build a versioned local dataset.")
    build_parser.add_argument("--config", type=Path)
    build_parser.add_argument("--from-date", dest="from_date")
    build_parser.add_argument("--to-date", dest="to_date")
    build_parser.add_argument("--limit-symbols", type=int)
    build_parser.add_argument("--overwrite-staging", action="store_true")
    build_parser.set_defaults(func=cmd_build)

    status_parser = subparsers.add_parser("status", help="Show latest dataset status.")
    status_parser.add_argument("--config", type=Path)
    status_parser.set_defaults(func=cmd_status)

    tables_parser = subparsers.add_parser("tables", help="Show latest table summaries.")
    tables_parser.add_argument("--config", type=Path)
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = subparsers.add_parser("schema", help="Show a table schema.")
    schema_parser.add_argument("table", choices=TABLES)
    schema_parser.add_argument("--config", type=Path)
    schema_parser.set_defaults(func=cmd_schema)

    head_parser = subparsers.add_parser("head", help="Show rows from a latest table.")
    add_query_args(head_parser, default_limit=20)
    head_parser.set_defaults(func=cmd_head)

    sql_parser = subparsers.add_parser("sql", help="Run SQL against latest table views.")
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--config", type=Path)
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = subparsers.add_parser("export", help="Export a filtered table query to CSV.")
    add_query_args(export_parser, default_limit=1000)
    export_parser.add_argument("--to", type=Path, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


def cmd_init_config(args: argparse.Namespace) -> int:
    write_default_config(args.path)
    print(f"wrote {args.path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"tdx_vipdoc={config.paths.tdx_vipdoc}")
    print(f"data_root={config.paths.data_root}")
    print(f"tdx_vipdoc_exists={config.paths.tdx_vipdoc.exists()}")
    print(f"data_root_exists={config.paths.data_root.exists()}")

    files = list(
        iter_day_files(
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
    )
    print(f"day_files={len(files)}")
    for path in files[:5]:
        print(f"sample={path}")

    for module in ("duckdb", "pyarrow"):
        try:
            imported = __import__(module)
        except ModuleNotFoundError:
            print(f"{module}=missing")
        else:
            print(f"{module}={getattr(imported, '__version__', 'installed')}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = build_dataset(
        config,
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        limit_symbols=args.limit_symbols,
        overwrite_staging=args.overwrite_staging or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def add_query_args(parser: argparse.ArgumentParser, default_limit: int) -> None:
    parser.add_argument("table", choices=TABLES)
    parser.add_argument("--config", type=Path)
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


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        manifest = ctx.manifest
        summary = manifest.get("summary", {})
        print(f"run_id={manifest.get('run_id')}")
        print(f"generated_at={summary.get('generated_at')}")
        print(f"version_dir={manifest.get('version_dir')}")
        print(f"data_root={config.paths.data_root}")
        print(f"disk_usage={format_bytes(disk_usage(config.paths.data_root))}")
        print("")
        print("checks:")
        for check in summary.get("checks", []):
            errors = len(check.get("errors", []))
            warnings = len(check.get("warnings", []))
            metrics = check.get("metrics", {})
            rows = metrics.get("rows")
            symbols = metrics.get("symbols")
            print(f"- {check.get('name')}: rows={rows} symbols={symbols} errors={errors} warnings={warnings}")
    finally:
        ctx.close()
    return 0


def cmd_tables(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [table_summary(ctx.con, ctx.manifest, table) for table in TABLES]
        columns = ["table", "rows", "symbols", "min_date", "max_date", "disk", "path"]
        print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [{"column": name, "type": type_} for name, type_ in table_columns(ctx.con, args.table)]
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
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = args.sql
        if args.limit and _is_select_like(sql) and " limit " not in f" {sql.lower()} ":
            sql = f"{sql.rstrip().rstrip(';')}\nLIMIT {args.limit}"
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
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
        print(f"exported rows={count} path={args.to}")
    finally:
        ctx.close()
    return 0


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [item.strip() for item in value.split(",") if item.strip()]
    return columns or None


def _is_select_like(sql: str) -> bool:
    stripped = sql.lstrip().lower()
    return stripped.startswith(("select", "with"))


if __name__ == "__main__":
    raise SystemExit(main())
