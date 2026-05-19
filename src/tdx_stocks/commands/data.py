from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from ..config import load_config
from ..console import print_json, print_key_values
from ..duckdb_ops import connect_duckdb, parquet_glob, sql_literal
from ..factors.reports import build_data_quality_report, write_json_atomic
from ..pipeline import build_dataset, parse_iso_date, rebuild_dataset, update_actions
from ..query import normalize_output_data
from .common import add_build_args, add_config_arg, stderr_progress
from .common import legacy_notice as _legacy_notice
from .common import write_lock as _write_lock


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


def register_data_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_build: Callable[[argparse.Namespace], int],
    cmd_rebuild: Callable[[argparse.Namespace], int],
    cmd_update_actions: Callable[[argparse.Namespace], int],
    cmd_actions_status: Callable[[argparse.Namespace], int],
    cmd_quality_report: Callable[[argparse.Namespace], int],
) -> None:
    data_parser = subparsers.add_parser(
        "data",
        help="Data pipeline commands.",
        description="Commands that refresh caches and rebuild versioned data.",
    )
    data_subparsers = data_parser.add_subparsers(dest="data_command", required=True)

    update_parser = data_subparsers.add_parser("update", help="Refresh cached corporate actions.")
    add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "file", "export"),
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
    add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_actions_status)

    build_parser = data_subparsers.add_parser("build", help="Build a versioned local dataset.")
    add_config_arg(build_parser)
    add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_build)

    rebuild_parser = data_subparsers.add_parser(
        "rebuild",
        help="Clear the current database and rebuild from local TDX data.",
    )
    add_config_arg(rebuild_parser)
    add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=cmd_rebuild)

    quality_parser = data_subparsers.add_parser(
        "quality-report",
        help="Write a data quality report for the latest dataset.",
    )
    add_config_arg(quality_parser)
    quality_parser.add_argument("--json", action="store_true")
    quality_parser.set_defaults(func=cmd_quality_report)


def register_legacy_data_aliases(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_build: Callable[[argparse.Namespace], int],
    cmd_rebuild: Callable[[argparse.Namespace], int],
    cmd_update_actions: Callable[[argparse.Namespace], int],
    cmd_actions_status: Callable[[argparse.Namespace], int],
) -> None:
    build_parser = subparsers.add_parser("build", help=argparse.SUPPRESS)
    build_parser._legacy_target = "data build"
    add_config_arg(build_parser)
    add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_build)

    rebuild_parser = subparsers.add_parser("rebuild", help=argparse.SUPPRESS)
    rebuild_parser._legacy_target = "data rebuild"
    add_config_arg(rebuild_parser)
    add_build_args(rebuild_parser)
    rebuild_parser.set_defaults(func=cmd_rebuild)

    update_parser = subparsers.add_parser("update-actions", help=argparse.SUPPRESS)
    update_parser._legacy_target = "data update"
    add_config_arg(update_parser)
    update_parser.add_argument(
        "--source",
        choices=("local", "file", "export"),
        default="local",
    )
    update_parser.add_argument(
        "--input",
        type=Path,
        help="Optional CSV file or directory containing corporate_actions.csv and adjustment_factors.csv.",
    )
    update_parser.add_argument("--dry-run", action="store_true")
    update_parser.add_argument("--json", action="store_true")
    update_parser.set_defaults(func=cmd_update_actions)

    actions_status_parser = subparsers.add_parser("actions-status", help=argparse.SUPPRESS)
    actions_status_parser._legacy_target = "data status"
    add_config_arg(actions_status_parser)
    actions_status_parser.add_argument("--json", action="store_true")
    actions_status_parser.set_defaults(func=cmd_actions_status)


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
            write_report=True,
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

    report_path = _latest_action_update_report_path(cache_root)
    if report_path is not None:
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


def _latest_action_update_report_path(cache_root: Path) -> Path | None:
    candidates = [
        cache_root / "action_update_report.json",
        cache_root / "action_update_report.dry_run.json",
    ]
    existing = [path for path in candidates if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def cmd_quality_report(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    latest = config.paths.data_root / "latest.json"
    if not latest.exists():
        raise FileNotFoundError(f"latest manifest not found: {latest}")
    manifest = json.loads(latest.read_text(encoding="utf-8"))
    summary = manifest.get("summary", {})
    version_dir = config.paths.data_root / "versions" / str(manifest.get("run_id") or "latest") / "reports"
    factor_quality_report = None
    factor_quality_path = version_dir / "factor_quality_report.json"
    if factor_quality_path.exists():
        factor_quality_report = json.loads(factor_quality_path.read_text(encoding="utf-8"))
    report = build_data_quality_report(
        {
            "run_id": manifest.get("run_id"),
            "data_root": config.paths.data_root.as_posix(),
            "version_dir": manifest.get("version_dir"),
            "generated_at": summary.get("generated_at") if isinstance(summary, dict) else None,
            "factor_version": summary.get("factor_version") if isinstance(summary, dict) else None,
        },
        summary.get("checks", []) if isinstance(summary, dict) else [],
        factor_quality=factor_quality_report,
    )
    report_path = (
        config.paths.data_root
        / "versions"
        / str(manifest.get("run_id") or "latest")
        / "reports"
        / "data_quality_report.json"
    )
    write_json_atomic(report_path, report)
    if getattr(args, "json", False):
        print_json(normalize_output_data(report))
    else:
        factor_quality = report.get("factor_quality_report") or report.get("factor_quality") or {}
        factor_quality_summary = factor_quality.get("summary") if isinstance(factor_quality, dict) else {}
        print_key_values(
            "data quality report",
            [
                ("run_id", report["summary"].get("run_id")),
                ("factor_version", report["summary"].get("factor_version")),
                ("generated_at", report["generated_at"]),
                ("checks", len(report["checks"])),
                ("missing_adj_close_rows", factor_quality_summary.get("missing_adj_close_rows")),
                ("missing_pct_chg_rows", factor_quality_summary.get("missing_pct_chg_rows")),
                ("missing_amount_ma20_rows", factor_quality_summary.get("missing_amount_ma20_rows")),
                ("missing_vol_20_rows", factor_quality_summary.get("missing_vol_20_rows")),
                ("missing_atr_pct_14_rows", factor_quality_summary.get("missing_atr_pct_14_rows")),
                ("report_path", report_path.as_posix()),
            ],
        )
    return 0
