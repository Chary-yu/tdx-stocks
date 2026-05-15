from __future__ import annotations

from pathlib import Path


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
    con.execute(
        f"""
        COPY (
            WITH base AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    adj_close,
                    volume,
                    amount,
                    lag(adj_close) OVER w AS prev_close,
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) AS ma5,
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
                    ) AS ma10,
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS ma20,
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                    ) AS ma60,
                    avg(volume) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) AS vol_ma5,
                    avg(volume) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS vol_ma20,
                    max(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS high_20,
                    min(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS low_20
                FROM read_parquet('{sql_literal(parquet_glob(adj_daily_dir))}', hive_partitioning=true)
                WINDOW w AS (PARTITION BY market, symbol ORDER BY trade_date)
            )
            SELECT
                market,
                symbol,
                trade_date,
                trade_year,
                CASE
                    WHEN prev_close IS NULL OR prev_close = 0 THEN NULL
                    ELSE adj_close / prev_close - 1
                END AS pct_chg,
                ma5,
                ma10,
                ma20,
                ma60,
                vol_ma5,
                vol_ma20,
                high_20,
                low_20,
                CASE
                    WHEN low_20 IS NULL OR low_20 = 0 THEN NULL
                    ELSE high_20 / low_20 - 1
                END AS range_20
            FROM base
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )
