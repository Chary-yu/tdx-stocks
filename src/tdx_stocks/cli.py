from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .adjustment_verify import build_adjustment_verification_report
from .commands.audit import register_audit_group, register_legacy_audit_aliases
from .commands.common import legacy_notice as _legacy_notice, stderr_progress, write_lock as _write_lock
from .commands.data import register_data_group, register_legacy_data_aliases
from .commands.query import register_legacy_query_aliases, register_query_group
from .commands.strategy import register_strategy_group
from .config import load_config, write_default_config
from .console import print_json, print_key_values, print_table
from .duckdb_ops import connect_duckdb, parquet_glob, sql_literal
from .exit_codes import (
    CliError,
    ExitCode,
    UsageError,
    VerificationFailedError,
)
from .help_summary import write_markdown
from .pipeline import build_dataset, parse_iso_date, rebuild_dataset, update_actions
from .query import (
    TABLES,
    build_select_sql,
    build_stock_sql,
    ensure_read_only_sql,
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
from .strategy import StrategyParams, run_trend_strength_strategy
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

    register_data_group(
        subparsers,
        cmd_build=cmd_build,
        cmd_rebuild=cmd_rebuild,
        cmd_update_actions=cmd_update_actions,
        cmd_actions_status=cmd_actions_status,
    )
    register_audit_group(
        subparsers,
        cmd_doctor=cmd_doctor,
        cmd_verify_adjustment=cmd_verify_adjustment,
    )
    register_query_group(
        subparsers,
        tables=tuple(TABLES),
        cmd_status=cmd_status,
        cmd_stock=cmd_stock,
        cmd_head=cmd_head,
        cmd_tables=cmd_tables,
        cmd_schema=cmd_schema,
        cmd_sql=cmd_sql,
        cmd_export=cmd_export,
    )
    register_strategy_group(
        subparsers,
        cmd_strategy_list=cmd_strategy_list,
        cmd_strategy_run=cmd_strategy_run,
    )
    init_parser = subparsers.add_parser("init-config", help="Write a default TOML config.")
    init_parser.add_argument("--path", type=Path, default=Path("tdx_stocks.toml"))
    init_parser.set_defaults(func=cmd_init_config)

    sync_parser = subparsers.add_parser("sync", help="Synchronize export-derived data and rebuild.")
    sync_parser.add_argument("--config", type=Path)
    sync_parser.add_argument("--from-date", dest="from_date")
    sync_parser.add_argument("--to-date", dest="to_date")
    sync_parser.add_argument("--limit-symbols", type=int)
    sync_parser.add_argument("--overwrite-staging", action="store_true")
    sync_parser.add_argument("--dry-run", action="store_true")
    sync_parser.add_argument("--json", action="store_true")
    sync_parser.set_defaults(func=cmd_sync)

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
    _register_legacy_aliases(subparsers)
    return parser


def _register_legacy_aliases(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    register_legacy_data_aliases(
        subparsers,
        cmd_build=cmd_build,
        cmd_rebuild=cmd_rebuild,
        cmd_update_actions=cmd_update_actions,
        cmd_actions_status=cmd_actions_status,
    )
    register_legacy_audit_aliases(
        subparsers,
        cmd_doctor=cmd_doctor,
        cmd_verify_adjustment=cmd_verify_adjustment,
    )
    register_legacy_query_aliases(
        subparsers,
        tables=tuple(TABLES),
        cmd_status=cmd_status,
        cmd_tables=cmd_tables,
        cmd_schema=cmd_schema,
        cmd_head=cmd_head,
        cmd_stock=cmd_stock,
        cmd_sql=cmd_sql,
        cmd_export=cmd_export,
    )


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [column.strip() for column in value.split(",")]
    return [column for column in columns if column]


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
        report = build_dataset(
            config,
            from_date=parse_iso_date(args.from_date),
            to_date=parse_iso_date(args.to_date),
            limit_symbols=args.limit_symbols,
            overwrite_staging=args.overwrite_staging or None,
            progress=stderr_progress,
        )
    print_json(normalize_output_data(report))
    return 0


def cmd_rebuild(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    with _write_lock(config, "data rebuild"):
        report = rebuild_dataset(
            config,
            from_date=parse_iso_date(args.from_date),
            to_date=parse_iso_date(args.to_date),
            limit_symbols=args.limit_symbols,
            overwrite_staging=args.overwrite_staging or None,
            progress=stderr_progress,
        )
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
        execution = execute_sync(
            config,
            plan,
            from_date=parse_iso_date(args.from_date),
            to_date=parse_iso_date(args.to_date),
            limit_symbols=args.limit_symbols,
            overwrite_staging=args.overwrite_staging or None,
            progress=stderr_progress,
        )

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


def _print_strategy_table(rows: list[dict[str, object]]) -> None:
    if not rows:
        print("(no rows)")
        return
    display_rows = []
    for row in rows:
        display_rows.append(
            {
                "rank": row.get("rank"),
                "symbol": row.get("display_symbol") or row.get("symbol"),
                "score": row.get("score"),
                "type": row.get("candidate_type"),
                "tags": _join_tokens(row.get("tags")),
                "risks": _join_tokens(row.get("risk_flags")),
                "plan": row.get("watch_plan"),
            }
        )
    print_table(["rank", "symbol", "score", "type", "tags", "risks", "plan"], display_rows)


def _join_tokens(values: object, max_items: int = 4) -> str:
    if not isinstance(values, list):
        return "" if values is None else str(values)
    items = [str(item) for item in values]
    if len(items) <= max_items:
        return "/".join(items)
    return "/".join(items[:max_items]) + "..."


def _build_strategy_params(args: argparse.Namespace) -> StrategyParams:
    return StrategyParams(
        limit=args.limit,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
        market=args.market,
        candidate_type=args.candidate_type,
        include_excluded=args.include_excluded,
        show_excluded_limit=args.show_excluded_limit,
        explain_symbol=args.explain_symbol,
        as_of=parse_iso_date(args.as_of),
        to=args.to,
        json=args.json,
    )


def _write_strategy_output(report, args: argparse.Namespace) -> None:
    report_dict = report.to_dict()
    if args.to is not None:
        args.to.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report_dict, ensure_ascii=False, indent=2, default=str)
        args.to.write_text(payload, encoding="utf-8")
    if args.json:
        print_json(report_dict)
    else:
        _print_strategy_table(report.picks)


def cmd_strategy_run(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    from .strategies.registry import get_strategy

    config = load_config(args.config)
    definition = get_strategy(args.strategy_name)
    report = definition.runner(config, _build_strategy_params(args))
    _write_strategy_output(report, args)
    return 0


def cmd_strategy_run_trend_strength(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    report = run_trend_strength_strategy(config, _build_strategy_params(args))
    _write_strategy_output(report, args)
    return 0


def cmd_strategy_list(args: argparse.Namespace) -> int:
    from .strategies.registry import list_strategies

    strategies = [
        {
            "name": definition.name,
            "description": definition.description,
            "aliases": list(definition.aliases),
        }
        for definition in list_strategies()
    ]
    if getattr(args, "json", False):
        print_json(normalize_output_data(strategies))
    else:
        print_table(["name", "aliases", "description"], strategies)
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
