from __future__ import annotations

import json
import shutil
from datetime import date, datetime

from .checks import CheckResult, check_adj_daily, check_factors, check_raw_daily
from .config import AppConfig
from .duckdb_ops import build_factors, connect_duckdb, copy_adj_daily
from .parquet_io import RawDailyWriter, write_empty_corporate_actions
from .paths import RunPaths, ensure_base_dirs
from .tdx_day import iter_day_files, read_day_records


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

    files = list(
        iter_day_files(
            config.paths.tdx_vipdoc,
            markets=config.build.markets,
            universe=config.build.universe,
        )
    )
    if limit_symbols is not None:
        files = files[:limit_symbols]

    raw_writer = RawDailyWriter(
        run_paths.raw_daily_dir,
        compression=config.build.compression,
        batch_rows=config.build.batch_rows,
    )
    parsed_files = 0
    for path in files:
        raw_writer.add_many(read_day_records(path, from_date=from_date, to_date=to_date))
        parsed_files += 1
    raw_writer.close()
    if raw_writer.rows_written == 0:
        raise RuntimeError("No raw_daily rows were parsed from the selected TDX day files")

    write_empty_corporate_actions(
        run_paths.corporate_actions_dir,
        compression=config.build.compression,
    )

    con = connect_duckdb(run_paths.duckdb_tmp_dir, config.build.duckdb_memory_limit)
    checks: list[CheckResult] = []
    try:
        checks.append(check_raw_daily(con, run_paths.raw_daily_dir))
        _raise_on_errors(checks)

        copy_adj_daily(
            con,
            run_paths.raw_daily_dir,
            run_paths.adj_daily_dir,
            config.build.compression,
        )
        checks.append(check_adj_daily(con, run_paths.adj_daily_dir))
        _raise_on_errors(checks)

        build_factors(
            con,
            run_paths.adj_daily_dir,
            run_paths.factors_dir,
            config.build.compression,
        )
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
        "checks": [check.to_dict() for check in checks],
    }
    (run_paths.reports_dir / "build_report.json").write_text(
        json.dumps(report, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    commit_version(run_paths, report)
    return report | {"version_dir": run_paths.version_dir.as_posix()}


def rebuild_dataset(
    config: AppConfig,
    from_date: date | None = None,
    to_date: date | None = None,
    limit_symbols: int | None = None,
    overwrite_staging: bool | None = None,
) -> dict:
    if config.paths.data_root.exists():
        shutil.rmtree(config.paths.data_root)
    return build_dataset(
        config,
        from_date=from_date,
        to_date=to_date,
        limit_symbols=limit_symbols,
        overwrite_staging=overwrite_staging,
    )


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
        "adj_daily": (run_paths.version_dir / "parquet" / "adj_daily").as_posix(),
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
