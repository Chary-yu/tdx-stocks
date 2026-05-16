from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from .checks import (
    CheckResult,
    check_adj_daily,
    check_adjustment_factors,
    check_factors,
    check_raw_daily,
)
from .actions_io import load_adjustment_factor_rows, load_corporate_action_rows, resolve_action_inputs
from .config import AppConfig
from .duckdb_ops import build_factors, connect_duckdb, copy_adj_daily, copy_parquet_dataset, has_parquet_files
from .export_io import load_export_adjustment_factor_rows
from .parquet_io import (
    RawDailyWriter,
    adjustment_factors_schema,
    corporate_actions_schema,
    clear_parquet_files,
    write_empty_adjustment_factors,
    write_empty_corporate_actions,
    write_records_table,
)
from .paths import RunPaths, ensure_base_dirs
from .tdx_day import iter_day_files, read_day_records

ProgressCallback = Callable[[str], None]


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

    overwrite = config.build.overwrite_staging if overwrite_staging is None else overwrite_staging
    if run_paths.staging_dir.exists():
        if not overwrite:
            raise FileExistsError(f"Staging directory already exists: {run_paths.staging_dir}")
        shutil.rmtree(run_paths.staging_dir)
    run_paths.staging_dir.mkdir(parents=True)
    run_paths.reports_dir.mkdir(parents=True)

    _progress(progress, f"Scanning local TDX files under {config.paths.tdx_vipdoc}")
    files = list(
        iter_day_files(
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
    )
    if limit_symbols is not None:
        files = files[:limit_symbols]
    total_files = len(files)
    _progress(progress, f"Parsing {total_files} day files")

    raw_writer = RawDailyWriter(
        run_paths.raw_daily_dir,
        compression=config.build.compression,
        batch_rows=config.build.batch_rows,
    )
    parsed_files = 0
    report_every = max(1, total_files // 20) if total_files else 1
    for path in files:
        raw_writer.add_many(read_day_records(path, from_date=from_date, to_date=to_date))
        parsed_files += 1
        if parsed_files == 1 or parsed_files == total_files or parsed_files % report_every == 0:
            _progress(progress, f"Parsed {parsed_files}/{total_files} day files")
    raw_writer.close()
    if raw_writer.rows_written == 0:
        raise RuntimeError("No raw_daily rows were parsed from the selected TDX day files")
    _progress(progress, f"Wrote {raw_writer.rows_written} raw rows")

    con = connect_duckdb(run_paths.duckdb_tmp_dir, config.build.duckdb_memory_limit)
    cache_root = config.paths.data_root / "cache"
    cache_corporate_actions_dir = cache_root / "corporate_actions"
    cache_adjustment_factors_dir = cache_root / "adjustment_factors"
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

    checks: list[CheckResult] = []
    try:
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
            cache_adjustment_factors_dir,
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
            cache_adjustment_factors_dir,
            factor_column="hfq_factor",
        )
        _progress(progress, "Checking hfq_daily")
        checks.append(check_adj_daily(con, run_paths.hfq_daily_dir, name="hfq_daily"))
        _raise_on_errors(checks)

        _progress(progress, "Building factors")
        build_factors(
            con,
            run_paths.adj_daily_dir,
            run_paths.factors_dir,
            config.build.compression,
        )
        _progress(progress, "Checking factors")
        checks.append(check_factors(con, run_paths.factors_dir))
        _raise_on_errors(checks)
    finally:
        con.close()

    report = {
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
        "checks": [check.to_dict() for check in checks],
    }
    (run_paths.reports_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    _progress(progress, "Writing build report")
    commit_version(run_paths, report)
    _progress(progress, f"Completed run_id={run_id}")
    return report | {"version_dir": run_paths.version_dir.as_posix()}


def rebuild_dataset(
    config: AppConfig,
    from_date: date | None = None,
    to_date: date | None = None,
    limit_symbols: int | None = None,
    overwrite_staging: bool | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    if config.paths.data_root.exists():
        _progress(progress, f"Clearing database root: {config.paths.data_root}")
        shutil.rmtree(config.paths.data_root)
    return build_dataset(
        config,
        from_date=from_date,
        to_date=to_date,
        limit_symbols=limit_symbols,
        overwrite_staging=overwrite_staging,
        progress=progress,
    )


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
        "report": (run_paths.version_dir / "reports" / "build_report.json").as_posix(),
        "summary": report,
    }
    tmp_path = run_paths.latest_manifest.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")
    tmp_path.replace(run_paths.latest_manifest)


def _raise_on_errors(checks: list[CheckResult]) -> None:
    errors = [error for check in checks for error in check.errors]
    if errors:
        rendered = "\n".join(f"- {error}" for error in errors)
        raise RuntimeError(f"Build checks failed:\n{rendered}")


def update_actions(
    config: AppConfig,
    source: str = "local",
    input_path: Path | None = None,
    overwrite_staging: bool | None = None,
    progress: ProgressCallback | None = None,
) -> dict:
    del overwrite_staging
    cache_root = config.paths.data_root / "cache"
    cache_root.mkdir(parents=True, exist_ok=True)
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
    }

    if source == "export":
        export_dir = input_path or config.paths.tdx_export
        rows = load_export_adjustment_factor_rows(
            export_dir,
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
        if not rows:
            raise RuntimeError(f"No export adjustment factors were loaded from {export_dir}")
        clear_parquet_files(cache_adjustment_factors_dir)
        write_records_table(
            cache_adjustment_factors_dir,
            adjustment_factors_schema(),
            rows,
            compression=config.build.compression,
        )
        report["adjustment_factors_rows"] = len(rows)
        report["adjustment_factors_state"] = "updated"
        report["input_path"] = export_dir.as_posix()
        _progress(progress, f"Wrote {len(rows)} export adjustment_factors rows")
        if not has_parquet_files(cache_corporate_actions_dir):
            write_empty_corporate_actions(
                cache_corporate_actions_dir,
                compression=config.build.compression,
            )
            report["corporate_actions_state"] = "initialized"
            _progress(progress, "Wrote empty corporate_actions cache")
        else:
            _progress(progress, "Kept existing corporate_actions cache")
    else:
        inputs = resolve_action_inputs(input_path)
        if inputs.corporate_actions is not None:
            rows = load_corporate_action_rows(inputs.corporate_actions)
            clear_parquet_files(cache_corporate_actions_dir)
            write_records_table(
                cache_corporate_actions_dir,
                corporate_actions_schema(),
                rows,
                compression=config.build.compression,
            )
            report["corporate_actions_rows"] = len(rows)
            report["corporate_actions_state"] = "updated"
            _progress(progress, f"Wrote {len(rows)} corporate_actions rows")
        elif not has_parquet_files(cache_corporate_actions_dir):
            write_empty_corporate_actions(
                cache_corporate_actions_dir,
                compression=config.build.compression,
            )
            report["corporate_actions_state"] = "initialized"
            _progress(progress, "Wrote empty corporate_actions cache")
        else:
            _progress(progress, "Kept existing corporate_actions cache")

        if inputs.adjustment_factors is not None:
            rows = load_adjustment_factor_rows(inputs.adjustment_factors)
            clear_parquet_files(cache_adjustment_factors_dir)
            write_records_table(
                cache_adjustment_factors_dir,
                adjustment_factors_schema(),
                rows,
                compression=config.build.compression,
            )
            report["adjustment_factors_rows"] = len(rows)
            report["adjustment_factors_state"] = "updated"
            _progress(progress, f"Wrote {len(rows)} adjustment_factors rows")
        elif not has_parquet_files(cache_adjustment_factors_dir):
            write_empty_adjustment_factors(
                cache_adjustment_factors_dir,
                compression=config.build.compression,
            )
            report["adjustment_factors_state"] = "initialized"
            _progress(progress, "Wrote empty adjustment_factors cache")
        else:
            _progress(progress, "Kept existing adjustment_factors cache")

    (cache_root / "action_update_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return report
