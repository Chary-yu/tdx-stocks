from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adjustment_verify import build_adjustment_verification_report
from .config import load_config, write_default_config
from .console import print_json, print_key_values, print_notice
from .duckdb_ops import connect_duckdb, parquet_glob, sql_literal
from .exit_codes import (
    BuildCheckFailedError,
    CliError,
    ExitCode,
    NoDataError,
    UsageError,
    VerificationFailedError,
)
from .help_summary import write_markdown
from .lock import acquire_database_lock
from .pipeline import build_dataset, parse_iso_date, rebuild_dataset, update_actions
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
from .sync import build_sync_plan, execute_sync
from .tdx_day import iter_day_files


class TdxArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401
        raise UsageError(message)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(exc.code)

    try:
        result = args.func(args)
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return int(ExitCode.INTERRUPTED)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(exc.code)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.INPUT_MISSING)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE_ERROR)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.UNKNOWN_ERROR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.UNKNOWN_ERROR)
    return int(result)


def build_parser() -> argparse.ArgumentParser:
    parser = TdxArgumentParser(
        prog="tdx-stocks",
        epilog="Tip: use `tdx-stocks help-summary` to generate the markdown CLI manual.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _register_init_config(subparsers)
    _register_sync(subparsers)
    _register_data_group(subparsers)
    _register_audit_group(subparsers)
    _register_query_group(subparsers)
    _register_help_summary(subparsers)
    _register_legacy_aliases(subparsers)
    return parser


def _register_init_config(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    init_parser = subparsers.add_parser("init-config", help="Write a default TOML config.")
    init_parser.add_argument("--path", type=Path, default=Path("tdx_stocks.toml"))
    init_parser.set_defaults(func=cmd_init_config)


def _register_sync(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    sync_parser = subparsers.add_parser("sync", help="Synchronize export-derived data and rebuild.")
    sync_parser.add_argument("--config", type=Path)
    sync_parser.add_argument("--from-date", dest="from_date")
    sync_parser.add_argument("--to-date", dest="to_date")
    sync_parser.add_argument("--limit-symbols", type=int)
    sync_parser.add_argument("--overwrite-staging", action="store_true")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.add_argument("--json", action="store_true")
    sync_parser.set_defaults(func=cmd_sync)


def _register_data_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    data_parser = subparsers.add_parser(
        "data",
        help="Data pipeline commands.",
        description="Commands that refresh caches and rebuild versioned data.",
    )
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)

    update_parser = data_subparsers.add_parser("update", help="Refresh cached corporate actions.")
    _add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "official", "file", "export"),
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
    _add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_actions_status)

    build_parser = data_subparsers.add_parser("build", help="Build a versioned local dataset.")
    _add_config_arg(build_parser)
    _add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_build)

    rebuild_parser = data_subparsers.add_parser(
        "rebuild",
        help="Clear the current database and rebuild from local TDX data.",
    )
    _add_config_arg(rebuild_parser)
    _add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=cmd_rebuild)


def _register_audit_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit and diagnostics commands.",
        description="Commands for environment checks and adjustment verification.",
    )
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command", required=True)

    doctor_parser = audit_subparsers.add_parser("doctor", help="Check paths and dependency imports.")
    _add_config_arg(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    verify_parser = audit_subparsers.add_parser(
        "verify",
        help="Compare adj_daily against TDX export front-adjusted text.",
    )
    _add_config_arg(verify_parser)
    verify_parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    verify_parser.add_argument("--input", type=Path, help="Optional export file or directory override.")
    verify_parser.add_argument("--from-date", dest="from_date")
    verify_parser.add_argument("--to-date", dest="to_date")
    verify_parser.add_argument("--threshold", type=float, default=0.01)
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(func=cmd_verify_adjustment)


def _register_query_group(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    query_parser = subparsers.add_parser(
        "query",
        help="Read-only inspection and query commands.",
        description="Commands that inspect the latest versioned dataset.",
    )
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    status_parser = query_subparsers.add_parser("status", help="Show latest dataset status.")
    _add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    price_parser = query_subparsers.add_parser(
        "price",
        help="Show merged daily rows and factors for one stock code.",
    )
    _add_stock_args(price_parser)
    price_parser.set_defaults(func=cmd_stock)

    table_parser = query_subparsers.add_parser("table", help="Show rows from a latest table.")
    _add_query_args(table_parser, default_limit=20)
    table_parser.set_defaults(func=cmd_head)

    tables_parser = query_subparsers.add_parser("tables", help="Show latest table summaries.")
    _add_config_arg(tables_parser)
    tables_parser.add_argument("--json", action="store_true")
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = query_subparsers.add_parser("schema", help="Show a table schema.")
    _add_config_arg(schema_parser)
    schema_parser.add_argument("table", choices=TABLES)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=cmd_schema)

    sql_parser = query_subparsers.add_parser("sql", help="Run SQL against latest table views.")
    _add_config_arg(sql_parser)
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = query_subparsers.add_parser("export", help="Export a filtered table query to CSV.")
    _add_query_args(export_parser, default_limit=1000)
    export_parser.add_argument("--to", type=Path, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)


def _register_help_summary(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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


def _register_legacy_aliases(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    build_parser = subparsers.add_parser("build", help=argparse.SUPPRESS)
    setattr(build_parser, "_legacy_target", "data build")
    _add_config_arg(build_parser)
    _add_build_args(build_parser)
    build_parser.set_defaults(func=_legacy_build_alias)

    rebuild_parser = subparsers.add_parser("rebuild", help=argparse.SUPPRESS)
    setattr(rebuild_parser, "_legacy_target", "data rebuild")
    _add_config_arg(rebuild_parser)
    _add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=_legacy_rebuild_alias)

    update_parser = subparsers.add_parser("update-actions", help=argparse.SUPPRESS)
    setattr(update_parser, "_legacy_target", "data update")
    _add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "official", "file", "export"),
        default="local",
    )
    update_parser.add_argument(
        "--input",
        type=Path,
        help="Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv.",
    )
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.add_argument("--json", action="store_true")
    update_parser.set_defaults(func=_legacy_update_actions_alias)

    actions_status_parser = subparsers.add_parser("actions-status", help=argparse.SUPPRESS)
    setattr(actions_status_parser, "_legacy_target", "data status")
    _add_config_arg(actions_status_parser)
    actions_status_parser.add_argument("--json", action="store_true")
    actions_status_parser.set_defaults(func=cmd_actions_status)

    verify_parser = subparsers.add_parser("verify-adjustment", help=argparse.SUPPRESS)
    setattr(verify_parser, "_legacy_target", "audit verify")
    _add_config_arg(verify_parser)
    verify_parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    verify_parser.add_argument("--input", type=Path, help="Optional export file or directory override.")
    verify_parser.add_argument("--from-date", dest="from_date")
    verify_parser.add_argument("--to-date", dest="to_date")
    verify_parser.add_argument("--threshold", type=float, default=0.01)
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(func=_legacy_verify_alias)

    doctor_parser = subparsers.add_parser("doctor", help=argparse.SUPPRESS)
    setattr(doctor_parser, "_legacy_target", "audit doctor")
    _add_config_arg(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    status_parser = subparsers.add_parser("status", help=argparse.SUPPRESS)
    setattr(status_parser, "_legacy_target", "query status")
    _add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_status)

    tables_parser = subparsers.add_parser("tables", help=argparse.SUPPRESS)
    setattr(tables_parser, "_legacy_target", "query tables")
    _add_config_arg(tables_parser)
    tables_parser.add_argument("--json", action="store_true")
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = subparsers.add_parser("schema", help=argparse.SUPPRESS)
    setattr(schema_parser, "_legacy_target", "query schema")
    _add_config_arg(schema_parser)
    schema_parser.add_argument("table", choices=TABLES)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=_legacy_schema_alias)

    head_parser = subparsers.add_parser("head", help=argparse.SUPPRESS)
    setattr(head_parser, "_legacy_target", "query table")
    _add_config_arg(head_parser)
    _add_query_args(head_parser, default_limit=20)
    head_parser.set_defaults(func=_legacy_head_alias)

    stock_parser = subparsers.add_parser("stock", help=argparse.SUPPRESS)
    setattr(stock_parser, "_legacy_target", "query price")
    _add_config_arg(stock_parser)
    _add_stock_args(stock_parser)
    stock_parser.set_defaults(func=_legacy_stock_alias)

    sql_parser = subparsers.add_parser("sql", help=argparse.SUPPRESS)
    setattr(sql_parser, "_legacy_target", "query sql")
    _add_config_arg(sql_parser)
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=_legacy_sql_alias)

    export_parser = subparsers.add_parser("export", help=argparse.SUPPRESS)
    setattr(export_parser, "_legacy_target", "query export")
    _add_config_arg(export_parser)
    _add_query_args(export_parser, default_limit=1000)
    export_parser.add_argument("--to", type=Path, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=_legacy_export_alias)


def _add_config_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)


def _add_build_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--limit-symbols", type=int)
    parser.add_argument("--overwrite-staging", action="store_true")


def _add_query_args(parser: argparse.ArgumentParser, default_limit: int) -> None:
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


def _add_stock_args(parser: argparse.ArgumentParser, default_limit: int = 100) -> None:
    parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    parser.add_argument("--limit", type=int, default=default_limit)
    parser.add_argument("--adjust", choices=("raw", "qfq", "hfq"), default="qfq")
    parser.add_argument("--from-date", dest="from_date")
    parser.add_argument("--to-date", dest="to_date")
    parser.add_argument("--asc", dest="desc", action="store_false")
    parser.set_defaults(desc=True)
    parser.add_argument("--no-limit", action="store_true")
    parser.add_argument("--json", action="store_true")


def _legacy_notice(args: argparse.Namespace) -> None:
    target = getattr(args, "_legacy_target", None)
    if target and not getattr(args, "json", False):
        print_notice(f"提示: 该命令已升级。建议下次使用 {target}。")


def _lock_path(config) -> Path:
    return config.paths.data_root / ".lock"


def _write_lock(config, command: str):
    return acquire_database_lock(_lock_path(config), command)


def _map_pipeline_error(exc: RuntimeError) -> CliError:
    message = str(exc)
    if message.startswith("Build checks failed:"):
        return BuildCheckFailedError(message)
    if "No raw_daily rows were parsed" in message:
        return NoDataError(message)
    return CliError(message)


def cmd_init_config(args: argparse.Namespace) -> int:
    write_default_config(args.path)
    print(f"wrote {args.path}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    items: list[tuple[str, object]] = [
        ("tdx_vipdoc", config.paths.tdx_vipdoc),
        ("tdx_export", config.paths.tdx_export),
        ("data_root", config.paths.data_root),
        ("tdx_vipdoc_exists", config.paths.tdx_vipdoc.exists()),
        ("tdx_export_exists", config.paths.tdx_export.exists()),
        ("data_root_exists", config.paths.data_root.exists()),
    ]
    files = list(
        iter_day_files(
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
    )
    items.append(("day_files", len(files)))
    for index, path in enumerate(files[:5], start=1):
        items.append((f"sample_{index}", path))

    for module in ("duckdb", "pyarrow"):
        try:
            imported = __import__(module)
        except ModuleNotFoundError:
            items.append((module, "missing"))
        else:
            items.append((module, getattr(imported, "__version__", "installed")))
    print_key_values("doctor", items)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    with _write_lock(config, "data build"):
        try:
            report = build_dataset(
                config,
                from_date=parse_iso_date(args.from_date),
                to_date=parse_iso_date(args.to_date),
                limit_symbols=args.limit_symbols,
                overwrite_staging=args.overwrite_staging or None,
                progress=stderr_progress,
            )
        except RuntimeError as exc:
            raise _map_pipeline_error(exc) from exc
    print_json(normalize_output_data(report))
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    with _write_lock(config, "data rebuild"):
        try:
            report = rebuild_dataset(
                config,
                from_date=parse_iso_date(args.from_date),
                to_date=parse_iso_date(args.to_date),
                limit_symbols=args.limit_symbols,
                overwrite_staging=args.overwrite_staging or None,
                progress=stderr_progress,
            )
        except RuntimeError as exc:
            raise _map_pipeline_error(exc) from exc
    print_json(normalize_output_data(report))
    return 0


def cmd_update_actions(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    lock_cm = None if args.dry_run else _write_lock(config, "data update")
    if lock_cm is None:
        report = update_actions(
            config,
            source=args.source,
            input_path=args.input,
            dry_run=args.dry_run,
            progress=stderr_progress,
            write_report=False,
        )
    else:
        with lock_cm:
            report = update_actions(
                config,
                source=args.source,
                input_path=args.input,
                dry_run=args.dry_run,
                progress=stderr_progress,
                write_report=True,
            )
    print_json(normalize_output_data(report))
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    plan = build_sync_plan(config)
    if args.dry_run or not plan.needs_write:
        print_json(_build_sync_report(plan, status="dry-run" if args.dry_run else "up-to-date"))
        return 0

    with _write_lock(config, "sync"):
        try:
            execution = execute_sync(
                config,
                plan,
                from_date=parse_iso_date(args.from_date),
                to_date=parse_iso_date(args.to_date),
                limit_symbols=args.limit_symbols,
                overwrite_staging=args.overwrite_staging or None,
                progress=stderr_progress,
            )
        except RuntimeError as exc:
            raise _map_pipeline_error(exc) from exc

    report = _build_sync_report(plan, status="updated")
    report["update_report"] = normalize_output_data(execution.update_report)
    report["build_report"] = normalize_output_data(execution.build_report)
    print_json(report)
    return 0


def _build_sync_report(plan, status: str) -> dict[str, object]:
    report = plan.to_dict()
    report["status"] = status
    return report


def stderr_progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


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


def cmd_actions_status(args: argparse.Namespace) -> int:
    _legacy_notice(args)
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
        report["generated_at"] = report["action_update_report"].get("generated_at")
    if args.json:
        print_json(normalize_output_data(report))
        return 0

    rows = [
        ("data_root", report["data_root"]),
        ("cache_root", report["cache_root"]),
    ]
    print_key_values("actions status", rows)
    for key in ("corporate_actions", "adjustment_factors"):
        table = report[key]
        print_key_values(
            key,
            [
                (f"{key}.exists", table["exists"]),
                (f"{key}.parquet_files", table["parquet_files"]),
                (f"{key}.rows", table["rows"]),
                (f"{key}.symbols", table["symbols"]),
                (f"{key}.min_date", table["min_date"]),
                (f"{key}.max_date", table["max_date"]),
                (f"{key}.cache_path", table["cache_path"]),
            ],
        )
    if "action_update_report" in report:
        update_report = report["action_update_report"]
        metrics = update_report.get("metrics", {})
        rows = [
            ("action_update_report.source", update_report.get("source")),
            ("action_update_report.generated_at", update_report.get("generated_at")),
            ("action_update_report.dry_run", update_report.get("dry_run")),
            (
                "action_update_report.total_scanned",
                metrics.get("total_scanned") if isinstance(metrics, dict) else None,
            ),
            (
                "action_update_report.successful",
                metrics.get("successful") if isinstance(metrics, dict) else None,
            ),
            (
                "action_update_report.skipped",
                metrics.get("skipped") if isinstance(metrics, dict) else None,
            ),
            (
                "action_update_report.bad_rows_dropped",
                metrics.get("bad_rows_dropped") if isinstance(metrics, dict) else None,
            ),
            (
                "action_update_report.adjustment_factors_state",
                update_report.get("adjustment_factors_state"),
            ),
            (
                "action_update_report.corporate_actions_state",
                update_report.get("corporate_actions_state"),
            ),
            (
                "action_update_report.adjustment_factors_rows",
                update_report.get("adjustment_factors_rows"),
            ),
            (
                "action_update_report.corporate_actions_rows",
                update_report.get("corporate_actions_rows"),
            ),
        ]
        if isinstance(metrics, dict):
            date_range = metrics.get("date_range", {})
            if isinstance(date_range, dict):
                rows.append(("action_update_report.date_range.min", date_range.get("min")))
                rows.append(("action_update_report.date_range.max", date_range.get("max")))
        print_key_values("action update report", rows)
    return 0


def cmd_verify_adjustment(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    report = build_adjustment_verification_report(
        config,
        args.symbol,
        input_path=args.input,
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        threshold=args.threshold,
    )
    if args.json:
        print_json(normalize_output_data(report))
    else:
        print_key_values(
            "verify adjustment",
            [
                ("symbol", report["symbol"]),
                ("export_path", report["export_path"]),
                ("threshold", report["threshold"]),
                ("export_rows", report["export_rows"]),
                ("adj_rows", report["adj_rows"]),
                ("common_rows", report["common_rows"]),
                ("export_only_rows", report["export_only_rows"]),
                ("adj_only_rows", report["adj_only_rows"]),
                ("max_abs_error", report["max_abs_error"]),
                ("max_abs_error_date", report["max_abs_error_date"]),
                ("mean_abs_error", report["mean_abs_error"]),
                ("mismatch_count", report["mismatch_count"]),
                ("ok", report["ok"]),
            ],
        )
        if report["mismatch_samples"]:
            print("mismatch_samples:")
            for item in report["mismatch_samples"][:10]:
                print(
                    f"- {item['trade_date']}: export={item['export_close']} adj={item['adj_close']} "
                    f"abs_error={item['abs_error']}"
                )
        if report["export_only_dates"]:
            print(f"export_only_dates={', '.join(report['export_only_dates'][:10])}")
        if report["adj_only_dates"]:
            print(f"adj_only_dates={', '.join(report['adj_only_dates'][:10])}")
    return 0 if report["ok"] else int(VerificationFailedError.code)


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
        sql = args.sql
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


def cmd_help_summary(args: argparse.Namespace) -> int:
    parser = build_parser()
    result = write_markdown(parser, args.output)
    if result is not None:
        print(f"wrote {result}")
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


def _is_select_like(sql: str) -> bool:
    stripped = sql.lstrip().lower()
    return stripped.startswith(("select", "with"))


def _legacy_build_alias(args: argparse.Namespace) -> int:
    return cmd_build(args)


def _legacy_rebuild_alias(args: argparse.Namespace) -> int:
    return cmd_rebuild(args)


def _legacy_update_actions_alias(args: argparse.Namespace) -> int:
    return cmd_update_actions(args)


def _legacy_verify_alias(args: argparse.Namespace) -> int:
    return cmd_verify_adjustment(args)


def _legacy_schema_alias(args: argparse.Namespace) -> int:
    return cmd_schema(args)


def _legacy_head_alias(args: argparse.Namespace) -> int:
    return cmd_head(args)


def _legacy_stock_alias(args: argparse.Namespace) -> int:
    return cmd_stock(args)


def _legacy_sql_alias(args: argparse.Namespace) -> int:
    return cmd_sql(args)


def _legacy_export_alias(args: argparse.Namespace) -> int:
    return cmd_export(args)


if __name__ == "__main__":
    raise SystemExit(main())
