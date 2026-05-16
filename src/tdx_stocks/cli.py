from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_config, write_default_config
from .help_summary import write_markdown
from .pipeline import build_dataset, parse_iso_date, rebuild_dataset, update_actions
from .duckdb_ops import connect_duckdb, parquet_glob, sql_literal
from .query import (
    TABLES,
    build_select_sql,
    build_stock_sql,
    disk_usage,
    export_query_csv,
    fetch_dicts,
    format_bytes,
    normalize_output_data,
    open_query_context,
    print_rows,
    table_columns,
    table_summary,
)
from .tdx_day import iter_day_files


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tdx-stocks",
        epilog="Tip: use `tdx-stocks help-summary` to generate the markdown CLI manual.",
    )
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

    rebuild_parser = subparsers.add_parser(
        "rebuild",
        help="Clear the current database and rebuild from local TDX data.",
    )
    rebuild_parser.add_argument("--config", type=Path)
    rebuild_parser.add_argument("--from-date", dest="from_date")
    rebuild_parser.add_argument("--to-date", dest="to_date")
    rebuild_parser.add_argument("--limit-symbols", type=int)
    rebuild_parser.add_argument("--overwrite-staging", action="store_true")
    rebuild_parser.set_defaults(func=cmd_rebuild)

    update_actions_parser = subparsers.add_parser(
        "update-actions",
        help="Refresh cached corporate actions or adjustment factors.",
    )
    update_actions_parser.add_argument("--config", type=Path)
    update_actions_parser.add_argument(
        "--source",
        choices=("local", "official", "file", "export"),
        default="local",
        help="Update source label for the report.",
    )
    update_actions_parser.add_argument(
        "--input",
        type=Path,
        help="Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv.",
    )
    update_actions_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Derive the update report without writing cache files.",
    )
    update_actions_parser.set_defaults(func=cmd_update_actions)

    status_parser = subparsers.add_parser("status", help="Show latest dataset status.")
    status_parser.add_argument("--config", type=Path)
    status_parser.set_defaults(func=cmd_status)

    actions_status_parser = subparsers.add_parser(
        "actions-status",
        help="Show cached corporate actions and adjustment factor status.",
    )
    actions_status_parser.add_argument("--config", type=Path)
    actions_status_parser.add_argument("--json", action="store_true")
    actions_status_parser.set_defaults(func=cmd_actions_status)

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

    stock_parser = subparsers.add_parser(
        "stock",
        help="Show merged daily rows and factors for one stock code.",
    )
    add_stock_args(stock_parser, default_limit=100)
    stock_parser.set_defaults(func=cmd_stock)

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

    help_summary_parser = subparsers.add_parser(
        "help-summary",
        help="Generate a markdown summary of the CLI.",
    )
    help_summary_parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/cli_help_summary.md"),
        help="Output markdown path, or - for stdout.",
    )
    help_summary_parser.set_defaults(func=cmd_help_summary)
    return parser


def cmd_init_config(args: argparse.Namespace) -> int:
    write_default_config(args.path)
    print(f"wrote {args.path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print(f"tdx_vipdoc={config.paths.tdx_vipdoc}")
    print(f"tdx_export={config.paths.tdx_export}")
    print(f"data_root={config.paths.data_root}")
    print(f"tdx_vipdoc_exists={config.paths.tdx_vipdoc.exists()}")
    print(f"tdx_export_exists={config.paths.tdx_export.exists()}")
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
        progress=stderr_progress,
    )
    print(json.dumps(normalize_output_data(report), ensure_ascii=False, indent=2))
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = rebuild_dataset(
        config,
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        limit_symbols=args.limit_symbols,
        overwrite_staging=args.overwrite_staging or None,
        progress=stderr_progress,
    )
    print(json.dumps(normalize_output_data(report), ensure_ascii=False, indent=2))
    return 0


def cmd_update_actions(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = update_actions(
        config,
        source=args.source,
        input_path=args.input,
        dry_run=args.dry_run,
        progress=stderr_progress,
    )
    print(json.dumps(normalize_output_data(report), ensure_ascii=False, indent=2))
    return 0


def stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


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


def add_stock_args(parser: argparse.ArgumentParser, default_limit: int) -> None:
    parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--limit", type=int, default=default_limit)
    parser.add_argument("--adjust", choices=("raw", "qfq", "hfq"), default="qfq")
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--asc", dest="desc", action="store_false")
    parser.set_defaults(desc=True)
    parser.add_argument("--no-limit", action="store_true")
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
            print(
                f"- {check.get('name')}: rows={rows} symbols={symbols} "
                f"errors={errors} warnings={warnings}"
            )
    finally:
        ctx.close()
    return 0


def cmd_actions_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    cache_root = config.paths.data_root / "cache"
    con = connect_duckdb(config.paths.data_root / "duckdb" / "tmp", config.build.duckdb_memory_limit)
    try:
        report = {
            "generated_at": None,
            "data_root": config.paths.data_root.as_posix(),
            "cache_root": cache_root.as_posix(),
            "corporate_actions": summarize_cached_table(
                con,
                cache_root / "corporate_actions",
                "ex_date",
            ),
            "adjustment_factors": summarize_cached_table(
                con,
                cache_root / "adjustment_factors",
                "trade_date",
            ),
        }
    finally:
        con.close()

    report_path = cache_root / "action_update_report.json"
    if report_path.exists():
        report["action_update_report"] = json.loads(report_path.read_text(encoding="utf-8"))
    if args.json:
        print(json.dumps(normalize_output_data(report), ensure_ascii=False, indent=2))
        return 0

    print(f"data_root={report['data_root']}")
    print(f"cache_root={report['cache_root']}")
    for key in ("corporate_actions", "adjustment_factors"):
        table = report[key]
        print(f"{key}.exists={table['exists']}")
        print(f"{key}.parquet_files={table['parquet_files']}")
        print(f"{key}.rows={table['rows']}")
        print(f"{key}.symbols={table['symbols']}")
        print(f"{key}.min_date={table['min_date']}")
        print(f"{key}.max_date={table['max_date']}")
        print(f"{key}.cache_path={table['cache_path']}")
    if "action_update_report" in report:
        update_report = report["action_update_report"]
        print(f"action_update_report.source={update_report.get('source')}")
        print(f"action_update_report.generated_at={update_report.get('generated_at')}")
        print(f"action_update_report.dry_run={update_report.get('dry_run')}")
        print(f"action_update_report.adjustment_factors_state={update_report.get('adjustment_factors_state')}")
        print(f"action_update_report.corporate_actions_state={update_report.get('corporate_actions_state')}")
        print(f"action_update_report.adjustment_factors_rows={update_report.get('adjustment_factors_rows')}")
        print(f"action_update_report.corporate_actions_rows={update_report.get('corporate_actions_rows')}")
    return 0


def summarize_cached_table(con, root: Path, date_column: str) -> dict:
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    summary = {
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
        rows = [
            {"column": name, "type": type_}
            for name, type_ in table_columns(ctx.con, args.table)
        ]
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
            print(
                json.dumps(
                    normalize_output_data(rows),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
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
            print(
                json.dumps(
                    normalize_output_data(rows),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
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


def cmd_help_summary(args: argparse.Namespace) -> int:
    parser = build_parser()
    result = write_markdown(parser, args.output)
    if result is not None:
        print(f"wrote {result}")
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
            print(
                json.dumps(
                    normalize_output_data(rows),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        else:
            print_rows(columns, rows)
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
