from __future__ import annotations

from datetime import date
from pathlib import Path

from .factor_sql import build_factors_statements


def connect_duckdb(temp_directory: Path, memory_limit: str):
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "duckdb is required for checks and factor calculation. Install dependencies first."
        ) from exc

    temp_directory.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET temp_directory='{temp_directory.as_posix()}'")
    con.execute(f"SET memory_limit='{memory_limit}'")
    return con


def parquet_glob(path: Path) -> str:
    return (path / "**" / "*.parquet").as_posix()


def has_parquet_files(path: Path | None) -> bool:
    return path is not None and path.exists() and any(path.rglob("*.parquet"))


def sql_literal(value: str | Path) -> str:
    return str(value).replace("'", "''")


def copy_adj_daily(
    con,
    raw_daily_dir: Path,
    output_dir: Path,
    compression: str,
    adjustment_factors_dir: Path | None = None,
    factor_column: str = "qfq_factor",
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    factor_source = None
    if has_parquet_files(adjustment_factors_dir):
        factor_source = (
            f"read_parquet('{sql_literal(parquet_glob(adjustment_factors_dir))}', hive_partitioning=true)"
        )
    raw_source = f"read_parquet('{sql_literal(parquet_glob(raw_daily_dir))}', hive_partitioning=true)"
    if factor_source is None:
        con.execute(
            f"""
            COPY (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    open AS adj_open,
                    high AS adj_high,
                    low AS adj_low,
                    close AS adj_close,
                    volume,
                    amount,
                    1.0::DOUBLE AS adj_factor
                FROM {raw_source}
            )
            TO '{sql_literal(output_dir.as_posix())}'
            (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
            """
        )
        return

    con.execute(
        f"""
        COPY (
            WITH raw_daily AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    amount
                FROM {raw_source}
            ),
            adjustment_factors AS (
                SELECT
                    market,
                    symbol,
                    COALESCE(start_date, trade_date) AS start_date,
                    COALESCE({factor_column}, 1.0) AS factor
                FROM {factor_source}
                WHERE COALESCE(start_date, trade_date) IS NOT NULL
            )
            SELECT
                raw_daily.market,
                raw_daily.symbol,
                raw_daily.trade_date,
                raw_daily.trade_year,
                raw_daily.open * COALESCE(factor, 1.0) AS adj_open,
                raw_daily.high * COALESCE(factor, 1.0) AS adj_high,
                raw_daily.low * COALESCE(factor, 1.0) AS adj_low,
                raw_daily.close * COALESCE(factor, 1.0) AS adj_close,
                CASE
                    WHEN factor IS NULL OR factor = 0 THEN raw_daily.volume
                    ELSE CAST(ROUND(raw_daily.volume / factor, 0) AS BIGINT)
                END AS volume,
                raw_daily.amount AS amount,
                COALESCE(factor, 1.0) AS adj_factor
            FROM raw_daily
            ASOF LEFT JOIN adjustment_factors
                ON raw_daily.market = adjustment_factors.market
                AND raw_daily.symbol = adjustment_factors.symbol
                AND raw_daily.trade_date >= adjustment_factors.start_date
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )


def copy_parquet_dataset(con, source_dir: Path, output_dir: Path, compression: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"""
        COPY (
            SELECT *
            FROM read_parquet('{sql_literal(parquet_glob(source_dir))}', hive_partitioning=true)
        )
        TO '{sql_literal((output_dir / "data.parquet").as_posix())}'
        (FORMAT PARQUET, COMPRESSION {compression.upper()})
        """
    )


def build_factors(
    con,
    adj_daily_dir: Path,
    output_dir: Path,
    compression: str,
    factor_windows: tuple[int, ...] | None = None,
    from_date: date | None = None,
    max_window_days: int | None = None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for statement in build_factors_statements(
        adj_daily_dir,
        output_dir,
        compression,
        factor_windows,
        from_date=from_date,
        max_window_days=max_window_days,
    ):
        con.execute(statement)
