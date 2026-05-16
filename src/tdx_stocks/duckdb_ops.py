from __future__ import annotations

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


def sql_literal(value: str | Path) -> str:
    return str(value).replace("'", "''")


def copy_adj_daily(con, raw_daily_dir: Path, output_dir: Path, compression: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
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
            FROM read_parquet('{sql_literal(parquet_glob(raw_daily_dir))}', hive_partitioning=true)
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )


def build_factors(con, adj_daily_dir: Path, output_dir: Path, compression: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for statement in build_factors_statements(adj_daily_dir, output_dir, compression):
        con.execute(statement)
