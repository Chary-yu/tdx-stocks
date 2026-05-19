from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .actions_io import (
    load_adjustment_factor_rows,
    load_corporate_action_rows,
    resolve_action_inputs,
)
from .checks import (
    CheckResult,
    check_adj_daily,
    check_adjustment_factors,
    check_factors,
    check_raw_daily,
)
from .config import AppConfig
from .duckdb_ops import (
    build_factors,
    connect_duckdb,
    copy_adj_daily,
    copy_parquet_dataset,
    has_parquet_files,
    parquet_glob,
    sql_literal,
)
from .exit_codes import BuildCheckFailedError, NoDataError
from .export_io import build_export_adjustment_factor_result
from .factor_sql import build_factor_spec, factor_build_report
from .factors.quality import build_factor_quality, build_factor_quality_summary
from .factors.reports import (
    build_data_quality_report,
    build_factor_catalog_report,
    build_factor_quality_report,
)
from .factors.xsec import build_xsec_factors
from .io_utils import write_json_atomic
from .parquet_io import (
    RawDailyWriter,
    adjustment_factors_schema,
    clear_parquet_files,
    corporate_actions_schema,
    write_empty_adjustment_factors,
    write_empty_corporate_actions,
    write_records_table,
)
from .paths import RunPaths, ensure_base_dirs
from .tdx_day import iter_day_files, read_day_records

ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class FactorIncrementalPlan:
    enabled: bool
    from_date: date | None
    previous_factors_dir: Path | None
    max_window_days: int
    reason: str


def make_run_id(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y%m%d%H%M%S%f")


def parse_iso_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def build_dataset(
    config: AppConfig,
    from_date: date | None = None,
    to_date: date | None = None,
    limit_symbols: int | None = None,
    overwrite_staging: bool | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    run_id = make_run_id()
    run_paths = RunPaths(config.paths.data_root, run_id)
    ensure_base_dirs(config.paths.data_root)
    previous_manifest = _load_latest_manifest(config.paths.data_root)

    overwrite = config.build.overwrite_staging if overwrite_staging is None else overwrite_staging
    if run_paths.staging_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Staging directory already exists: {run_paths.staging_dir}")
        shutil.rmtree(run_paths.staging_dir)
    run_paths.staging_dir.mkdir(parents=True)
    run_paths.reports_dir.mkdir(parents=True)

    cache_root = config.paths.data_root / "cache"
    cache_corporate_actions_dir = cache_root / "corporate_actions"
    cache_adjustment_factors_dir = cache_root / "adjustment_factors"
    raw_writer = RawDailyWriter(
        run_paths.raw_daily_dir,
        compression=config.build.compression,
        batch_rows=config.build.batch_rows,
    )
    con = None
    checks: list[CheckResult] = []
    parsed_files = 0
    success = False
    try:
        _progress(progress, f"Scanning local TDX files under {config.paths.tdx_vipdoc}")
        files = list(
            iter_day_files(
                config.paths.tdx_vipdoc,
                markets=config.build.markets,
                universe=config.build.universe,
            )
        )
        if not files:
            raise NoDataError(
                f"No TDX day files found under: {config.paths.tdx_vipdoc}.\n"
                "Expected a TDX vipdoc tree such as vipdoc/sh/lday/*.day and vipdoc/sz/lday/*.day."
            )
        if limit_symbols is not None:
            files = files[:limit_symbols]
        total_files = len(files)
        _progress(progress, f"Parsing {total_files} day files")

        report_every = max(1, total_files // 20) if total_files else 1
        for path in files:
            raw_writer.add_many(read_day_records(path, from_date=from_date, to_date=to_date))
            parsed_files += 1
            if parsed_files == 1 or parsed_files == total_files or parsed_files % report_every == 0:
                _progress(progress, f"Parsed {parsed_files}/{total_files} day files")
        raw_writer.flush()
        if raw_writer.rows_written == 0:
            filters: list[str] = []
            if from_date is not None:
                filters.append(f"from_date={from_date.isoformat()}")
            if to_date is not None:
                filters.append(f"to_date={to_date.isoformat()}")
            filter_text = f" with filters: {', '.join(filters)}" if filters else ""
            raise NoDataError(
                f"No raw_daily rows were parsed from {total_files} selected TDX day files{filter_text}.\n"
                f"Check that {config.paths.tdx_vipdoc} contains valid .day records."
            )
        _progress(progress, f"Wrote {raw_writer.rows_written} raw rows")

        con = connect_duckdb(run_paths.duckdb_tmp_dir, config.build.duckdb_memory_limit)
        if has_parquet_files(cache_corporate_actions_dir):
            _progress(progress, "Copying cached corporate_actions")
            copy_parquet_dataset(
                con,
                cache_corporate_actions_dir,
                run_paths.corporate_actions_dir,
                config.build.compression,
            )
        else:
            write_empty_corporate_actions(
                run_paths.corporate_actions_dir,
                compression=config.build.compression,
            )
            _progress(progress, "Wrote empty corporate_actions table")

        if has_parquet_files(cache_adjustment_factors_dir):
            _progress(progress, "Copying cached adjustment_factors")
            copy_parquet_dataset(
                con,
                cache_adjustment_factors_dir,
                run_paths.adjustment_factors_dir,
                config.build.compression,
            )
        else:
            write_empty_adjustment_factors(
                run_paths.adjustment_factors_dir,
                compression=config.build.compression,
            )
            _progress(progress, "Wrote empty adjustment_factors table")

        _progress(progress, "Checking raw_daily")
        checks.append(check_raw_daily(con, run_paths.raw_daily_dir))
        _raise_on_errors(checks)

        _progress(progress, "Checking adjustment_factors")
        checks.append(check_adjustment_factors(con, run_paths.adjustment_factors_dir))
        _raise_on_errors(checks)

        _progress(progress, "Building adj_daily")
        copy_adj_daily(
            con,
            run_paths.raw_daily_dir,
            run_paths.adj_daily_dir,
            config.build.compression,
            run_paths.adjustment_factors_dir,
            factor_column="qfq_factor",
        )
        _progress(progress, "Checking adj_daily")
        checks.append(check_adj_daily(con, run_paths.adj_daily_dir))
        _raise_on_errors(checks)

        _progress(progress, "Building hfq_daily")
        copy_adj_daily(
            con,
            run_paths.raw_daily_dir,
            run_paths.hfq_daily_dir,
            config.build.compression,
            run_paths.adjustment_factors_dir,
            factor_column="hfq_factor",
        )
        _progress(progress, "Checking hfq_daily")
        checks.append(check_adj_daily(con, run_paths.hfq_daily_dir, name="hfq_daily"))
        _raise_on_errors(checks)

        factor_spec = build_factor_spec(config.factors.windows)
        factor_incremental_plan = _plan_factor_incremental_build(
            con,
            run_paths.adjustment_factors_dir,
            previous_manifest,
            factor_spec,
        )
        if factor_incremental_plan.enabled and factor_incremental_plan.previous_factors_dir is not None:
            _progress(
                progress,
                f"Building factors incrementally from {factor_incremental_plan.from_date}",
            )
            shutil.copytree(
                factor_incremental_plan.previous_factors_dir,
                run_paths.factors_dir,
                dirs_exist_ok=True,
            )
        else:
            _progress(progress, f"Building factors full ({factor_incremental_plan.reason})")
        build_factors(
            con,
            run_paths.adj_daily_dir,
            run_paths.factors_dir,
            config.build.compression,
            factor_windows=config.factors.windows,
            from_date=factor_incremental_plan.from_date if factor_incremental_plan.enabled else None,
            max_window_days=factor_incremental_plan.max_window_days,
        )
        _progress(progress, "Building factors_xsec")
        build_xsec_factors(con, run_paths.factors_dir, run_paths.factors_xsec_dir, config.build.compression)
        _progress(progress, "Building factors_quality")
        build_factor_quality(
            con,
            run_paths.adj_daily_dir,
            run_paths.factors_dir,
            run_paths.factors_quality_dir,
            config.build.compression,
        )
        _progress(progress, "Checking factors")
        checks.append(check_factors(con, run_paths.factors_dir))
        _raise_on_errors(checks)
        summary_checks = [check.to_dict() for check in checks]
        build_report = {
            "run_id": run_id,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "tdx_vipdoc": config.paths.tdx_vipdoc.as_posix(),
            "data_root": config.paths.data_root.as_posix(),
            "from_date": from_date.isoformat() if from_date else None,
            "to_date": to_date.isoformat() if to_date else None,
            "markets": list(config.build.markets),
            "universe": config.build.universe,
            "parsed_files": parsed_files,
            "raw_rows_written": raw_writer.rows_written,
            "compression": config.build.compression,
            "cached_corporate_actions": has_parquet_files(cache_corporate_actions_dir),
            "cached_adjustment_factors": has_parquet_files(cache_adjustment_factors_dir),
            "factor_incremental": factor_incremental_plan.enabled,
            "factor_incremental_from_date": (
                factor_incremental_plan.from_date.isoformat()
                if factor_incremental_plan.from_date is not None
                else None
            ),
            "factor_incremental_reason": factor_incremental_plan.reason,
            "factor_max_window_days": factor_incremental_plan.max_window_days,
            **factor_build_report(factor_spec),
            "checks": summary_checks,
        }
        write_json_atomic(
            run_paths.reports_dir / "factor_catalog_report.json",
            build_factor_catalog_report(run_id, build_report["factor_version"]),
        )
        factor_quality_report = build_factor_quality_report(
            build_factor_quality_summary(con, run_paths.factors_dir),
            [
                {"name": "missing_price_flag", "description": "缺失价格标记"},
                {"name": "zero_amount_flag", "description": "零成交额标记"},
                {"name": "invalid_ohlc_flag", "description": "OHLC 异常标记"},
                {"name": "stale_price_flag", "description": "价格停滞标记"},
                {"name": "extreme_return_flag", "description": "极端收益标记"},
                {"name": "low_history_flag", "description": "历史长度不足标记"},
            ],
        )
        write_json_atomic(
            run_paths.reports_dir / "factor_quality_report.json",
            factor_quality_report,
        )
        write_json_atomic(
            run_paths.reports_dir / "data_quality_report.json",
            build_data_quality_report(
                {
                    "run_id": run_id,
                    "data_root": config.paths.data_root.as_posix(),
                    "raw_rows_written": raw_writer.rows_written,
                    "parsed_files": parsed_files,
                    "factor_version": build_report["factor_version"],
                    "checks": summary_checks,
                },
                summary_checks,
                factor_quality=factor_quality_report,
            ),
        )
        report = build_report
        write_json_atomic(run_paths.reports_dir / "build_report.json", report)

        _progress(progress, "Writing build report")
        commit_version(run_paths, report)
        _progress(progress, f"Completed run_id={run_id}")
        success = True
        return report | {"version_dir": run_paths.version_dir.as_posix()}
    finally:
        raw_writer.close()
        if con is not None:
            con.close()
        if not success:
            shutil.rmtree(run_paths.staging_dir, ignore_errors=True)


def rebuild_dataset(
    config: AppConfig,
    from_date: date | None = None,
    to_date: date | None = None,
    limit_symbols: int | None = None,
    overwrite_staging: bool | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    files = list(
        iter_day_files(
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
    )
    if not files:
        raise NoDataError(
            f"No TDX day files found under: {config.paths.tdx_vipdoc}.\n"
            "Set [paths].tdx_vipdoc to the real vipdoc root, then run: tdx-stocks data sync"
        )
    if config.paths.data_root.exists():
        _progress(progress, f"Clearing database root except cache: {config.paths.data_root}")
        clear_database_root_preserving_cache(config.paths.data_root)
    return build_dataset(
        config,
        from_date=from_date,
        to_date=to_date,
        limit_symbols=limit_symbols,
        overwrite_staging=overwrite_staging,
        progress=progress,
    )


def _load_latest_manifest(data_root: Path) -> dict | None:
    path = data_root / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _plan_factor_incremental_build(
    con,
    current_adjustment_factors_dir: Path,
    previous_manifest: dict | None,
    factor_spec,
) -> FactorIncrementalPlan:
    max_window_days = max(factor_spec.effective_windows)
    disabled = FactorIncrementalPlan(
        enabled=False,
        from_date=None,
        previous_factors_dir=None,
        max_window_days=max_window_days,
        reason="no_previous_version",
    )
    if previous_manifest is None:
        return disabled

    previous_factors_dir = _manifest_table_path(previous_manifest, "factors")
    if previous_factors_dir is None or not has_parquet_files(previous_factors_dir):
        return FactorIncrementalPlan(
            enabled=False,
            from_date=None,
            previous_factors_dir=previous_factors_dir,
            max_window_days=max_window_days,
            reason="no_previous_factors",
        )

    previous_windows = previous_manifest.get("summary", {}).get("configured_windows")
    if previous_windows is None or tuple(int(window) for window in previous_windows) != factor_spec.configured_windows:
        return FactorIncrementalPlan(
            enabled=False,
            from_date=None,
            previous_factors_dir=previous_factors_dir,
            max_window_days=max_window_days,
            reason="factor_window_config_changed",
        )

    if not _factor_schema_supports_incremental(con, previous_factors_dir):
        return FactorIncrementalPlan(
            enabled=False,
            from_date=None,
            previous_factors_dir=previous_factors_dir,
            max_window_days=max_window_days,
            reason="factor_schema_changed",
        )

    last_trade_date = _max_trade_date(con, previous_factors_dir)
    if last_trade_date is None:
        return FactorIncrementalPlan(
            enabled=False,
            from_date=None,
            previous_factors_dir=previous_factors_dir,
            max_window_days=max_window_days,
            reason="empty_previous_factors",
        )

    previous_adjustment_factors_dir = _manifest_table_path(previous_manifest, "adjustment_factors")
    if _has_historical_adjustment_factor_changes(
        con,
        current_adjustment_factors_dir,
        previous_adjustment_factors_dir,
        last_trade_date,
    ):
        return FactorIncrementalPlan(
            enabled=False,
            from_date=None,
            previous_factors_dir=previous_factors_dir,
            max_window_days=max_window_days,
            reason="historical_adjustment_changed",
        )

    return FactorIncrementalPlan(
        enabled=True,
        from_date=last_trade_date,
        previous_factors_dir=previous_factors_dir,
        max_window_days=max_window_days,
        reason="append_new_trade_dates",
    )


def _manifest_table_path(manifest: dict, table: str) -> Path | None:
    value = manifest.get(table)
    return Path(value) if value else None


def _max_trade_date(con, table_dir: Path) -> date | None:
    source = f"read_parquet('{sql_literal(parquet_glob(table_dir))}', hive_partitioning=true)"
    row = con.execute(f"SELECT max(trade_date) FROM {source}").fetchone()
    return row[0] if row is not None else None


def _factor_schema_supports_incremental(con, factors_dir: Path) -> bool:
    source = f"read_parquet('{sql_literal(parquet_glob(factors_dir))}', hive_partitioning=true)"
    result = con.execute(f"SELECT * FROM {source} LIMIT 0")
    columns = {description[0] for description in result.description}
    return {"is_limit_up", "is_limit_down", "is_suspended"}.issubset(columns)


def _has_historical_adjustment_factor_changes(
    con,
    current_dir: Path,
    previous_dir: Path | None,
    through_date: date,
) -> bool:
    if not has_parquet_files(current_dir):
        return has_parquet_files(previous_dir)
    if not has_parquet_files(previous_dir):
        return _has_adjustment_rows_through(con, current_dir, through_date)
    return _has_adjustment_except(con, current_dir, previous_dir, through_date) or _has_adjustment_except(
        con,
        previous_dir,
        current_dir,
        through_date,
    )


def _has_adjustment_rows_through(con, table_dir: Path, through_date: date) -> bool:
    source = f"read_parquet('{sql_literal(parquet_glob(table_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT 1
        FROM {source}
        WHERE COALESCE(start_date, trade_date) <= DATE '{sql_literal(through_date.isoformat())}'
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _has_adjustment_except(con, left_dir: Path, right_dir: Path, through_date: date) -> bool:
    left_source = f"read_parquet('{sql_literal(parquet_glob(left_dir))}', hive_partitioning=true)"
    right_source = f"read_parquet('{sql_literal(parquet_glob(right_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        WITH left_hist AS (
            {_adjustment_compare_sql(left_source, through_date)}
        ),
        right_hist AS (
            {_adjustment_compare_sql(right_source, through_date)}
        )
        SELECT 1
        FROM (
            SELECT * FROM left_hist
            EXCEPT
            SELECT * FROM right_hist
        ) AS diff
        LIMIT 1
        """
    ).fetchone()
    return row is not None


def _adjustment_compare_sql(source: str, through_date: date) -> str:
    return f"""
            SELECT
                market,
                symbol,
                trade_date,
                start_date,
                end_date,
                qfq_factor,
                hfq_factor
            FROM {source}
            WHERE COALESCE(start_date, trade_date) <= DATE '{sql_literal(through_date.isoformat())}'
    """


def clear_database_root_preserving_cache(data_root: Path) -> None:
    for child in data_root.iterdir():
        if child.name == "cache":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _progress(progress: ProgressCallback | None, message: str) -> None:
    if progress is not None:
        progress(message)


def commit_version(run_paths: RunPaths, report: dict) -> None:
    if run_paths.version_dir.exists():
        raise FileExistsError(f"Version directory already exists: {run_paths.version_dir}")
    run_paths.version_dir.parent.mkdir(parents=True, exist_ok=True)
    run_paths.staging_dir.replace(run_paths.version_dir)

    manifest = {
        "run_id": run_paths.run_id,
        "version_dir": run_paths.version_dir.as_posix(),
        "parquet_dir": (run_paths.version_dir / "parquet").as_posix(),
        "raw_daily": (run_paths.version_dir / "parquet" / "raw_daily").as_posix(),
        "corporate_actions": (run_paths.version_dir / "parquet" / "corporate_actions").as_posix(),
        "adjustment_factors": (run_paths.version_dir / "parquet" / "adjustment_factors").as_posix(),
        "adj_daily": (run_paths.version_dir / "parquet" / "adj_daily").as_posix(),
        "hfq_daily": (run_paths.version_dir / "parquet" / "hfq_daily").as_posix(),
        "factors": (run_paths.version_dir / "parquet" / "factors").as_posix(),
        "factors_xsec": (run_paths.version_dir / "parquet" / "factors_xsec").as_posix(),
        "factors_quality": (run_paths.version_dir / "parquet" / "factors_quality").as_posix(),
        "report": (run_paths.version_dir / "reports" / "build_report.json").as_posix(),
        "factor_catalog_report": (run_paths.version_dir / "reports" / "factor_catalog_report.json").as_posix(),
        "data_quality_report": (run_paths.version_dir / "reports" / "data_quality_report.json").as_posix(),
        "factor_quality_report": (run_paths.version_dir / "reports" / "factor_quality_report.json").as_posix(),
        "summary": report,
    }
    write_json_atomic(run_paths.latest_manifest, manifest)


def _raise_on_errors(checks: list[CheckResult]) -> None:
    errors = [error for check in checks for error in check.errors]
    if errors:
        rendered = "\n".join(f"- {error}" for error in errors)
        raise BuildCheckFailedError(f"Build checks failed:\n{rendered}")


def update_actions(
    config: AppConfig,
    source: str = "local",
    input_path: Path | None = None,
    dry_run: bool = False,
    overwrite_staging: bool | None = None,
    write_report: bool = True,
    progress: ProgressCallback | None = None,
) -> dict:
    del overwrite_staging
    if source == "official":
        raise ValueError("source=official is not implemented yet; use local, file, or export")
    cache_root = config.paths.data_root / "cache"
    cache_corporate_actions_dir = cache_root / "corporate_actions"
    cache_adjustment_factors_dir = cache_root / "adjustment_factors"
    report: dict[str, object] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "input_path": input_path.as_posix() if input_path else None,
        "corporate_actions_rows": 0,
        "adjustment_factors_rows": 0,
        "corporate_actions_state": "unchanged",
        "adjustment_factors_state": "unchanged",
        "dry_run": dry_run,
    }

    if not dry_run or write_report:
        cache_root.mkdir(parents=True, exist_ok=True)

    if source == "export":
        export_dir = input_path or config.paths.tdx_export
        result = build_export_adjustment_factor_result(
            export_dir,
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
        rows = result.rows
        report["adjustment_factors_report"] = result.report
        if not dry_run:
            clear_parquet_files(cache_adjustment_factors_dir)
            if rows:
                write_records_table(
                    cache_adjustment_factors_dir,
                    adjustment_factors_schema(),
                    rows,
                    compression=config.build.compression,
                )
            else:
                write_empty_adjustment_factors(
                    cache_adjustment_factors_dir,
                    compression=config.build.compression,
                )
        if not rows:
            _progress(progress, f"No export adjustment factors were loaded from {export_dir}")
        report["adjustment_factors_rows"] = len(rows)
        report["adjustment_factors_state"] = "updated" if not dry_run else "dry-run"
        report["input_path"] = export_dir.as_posix()
        if dry_run:
            _progress(progress, f"Dry run: derived {len(rows)} export adjustment_factors rows")
        else:
            _progress(progress, f"Wrote {len(rows)} export adjustment_factors rows")
        if not dry_run and not has_parquet_files(cache_corporate_actions_dir):
            write_empty_corporate_actions(
                cache_corporate_actions_dir,
                compression=config.build.compression,
            )
            report["corporate_actions_state"] = "initialized"
            _progress(progress, "Wrote empty corporate_actions cache")
        elif not dry_run:
            _progress(progress, "Kept existing corporate_actions cache")
    else:
        inputs = resolve_action_inputs(input_path)
        if inputs.corporate_actions is not None:
            rows = load_corporate_action_rows(inputs.corporate_actions)
            if not dry_run:
                clear_parquet_files(cache_corporate_actions_dir)
                if rows:
                    write_records_table(
                        cache_corporate_actions_dir,
                        corporate_actions_schema(),
                        rows,
                        compression=config.build.compression,
                    )
                else:
                    write_empty_corporate_actions(
                        cache_corporate_actions_dir,
                        compression=config.build.compression,
                    )
            report["corporate_actions_rows"] = len(rows)
            report["corporate_actions_state"] = "updated" if not dry_run else "dry-run"
            _progress(
                progress,
                f"{'Dry run:' if dry_run else 'Wrote'} {len(rows)} corporate_actions rows",
            )
        elif not has_parquet_files(cache_corporate_actions_dir):
            if not dry_run:
                write_empty_corporate_actions(
                    cache_corporate_actions_dir,
                    compression=config.build.compression,
                )
            report["corporate_actions_state"] = "initialized" if not dry_run else "dry-run"
            _progress(progress, "Wrote empty corporate_actions cache" if not dry_run else "Dry run: empty corporate_actions cache")
        else:
            _progress(progress, "Kept existing corporate_actions cache")

        if inputs.adjustment_factors is not None:
            rows = load_adjustment_factor_rows(inputs.adjustment_factors)
            if not dry_run:
                clear_parquet_files(cache_adjustment_factors_dir)
                if rows:
                    write_records_table(
                        cache_adjustment_factors_dir,
                        adjustment_factors_schema(),
                        rows,
                        compression=config.build.compression,
                    )
                else:
                    write_empty_adjustment_factors(
                        cache_adjustment_factors_dir,
                        compression=config.build.compression,
                    )
            report["adjustment_factors_rows"] = len(rows)
            report["adjustment_factors_state"] = "updated" if not dry_run else "dry-run"
            _progress(
                progress,
                f"{'Dry run:' if dry_run else 'Wrote'} {len(rows)} adjustment_factors rows",
            )
        elif not has_parquet_files(cache_adjustment_factors_dir):
            if not dry_run:
                write_empty_adjustment_factors(
                    cache_adjustment_factors_dir,
                    compression=config.build.compression,
                )
            report["adjustment_factors_state"] = "initialized" if not dry_run else "dry-run"
            _progress(
                progress,
                "Wrote empty adjustment_factors cache"
                if not dry_run
                else "Dry run: empty adjustment_factors cache",
            )
        else:
            _progress(progress, "Kept existing adjustment_factors cache")

    if write_report:
        legacy_report_path = cache_root / "action_update_report.json"
        report_path = cache_root / "action_update_report.dry_run.json" if dry_run else legacy_report_path
        write_json_atomic(report_path, report)
        if dry_run:
            write_json_atomic(legacy_report_path, report)
    return report
