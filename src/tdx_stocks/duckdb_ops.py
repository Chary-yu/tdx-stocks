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
            WITH RECURSIVE source AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    adj_close::DOUBLE AS adj_close,
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
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 119 PRECEDING AND CURRENT ROW
                    ) AS ma120,
                    avg(adj_close) OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                        ROWS BETWEEN 249 PRECEDING AND CURRENT ROW
                    ) AS ma250,
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
                    ) AS low_20,
                    row_number() OVER (
                        PARTITION BY market, symbol
                        ORDER BY trade_date
                    ) AS rn
                FROM read_parquet(
                    '{sql_literal(parquet_glob(adj_daily_dir))}',
                    hive_partitioning=true
                )
                WINDOW w AS (PARTITION BY market, symbol ORDER BY trade_date)
            ),
            macd AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    rn,
                    adj_close::DOUBLE AS adj_close,
                    adj_close::DOUBLE AS ema12_state,
                    adj_close::DOUBLE AS ema26_state,
                    0.0::DOUBLE AS macd_dif,
                    0.0::DOUBLE AS macd_dea,
                    0.0::DOUBLE AS macd_hist
                FROM source
                WHERE rn = 1
                UNION ALL
                SELECT
                    s.market,
                    s.symbol,
                    s.trade_date,
                    s.trade_year,
                    s.rn,
                    s.adj_close::DOUBLE,
                    2.0 / 13.0 * s.adj_close::DOUBLE
                    + (1.0 - 2.0 / 13.0) * m.ema12_state AS ema12_state,
                    2.0 / 27.0 * s.adj_close::DOUBLE
                    + (1.0 - 2.0 / 27.0) * m.ema26_state AS ema26_state,
                    (
                        2.0 / 13.0 * s.adj_close::DOUBLE
                        + (1.0 - 2.0 / 13.0) * m.ema12_state
                    ) - (
                        2.0 / 27.0 * s.adj_close::DOUBLE
                        + (1.0 - 2.0 / 27.0) * m.ema26_state
                    ) AS macd_dif,
                    2.0 / 10.0 * (
                        (
                            2.0 / 13.0 * s.adj_close::DOUBLE
                            + (1.0 - 2.0 / 13.0) * m.ema12_state
                        ) - (
                            2.0 / 27.0 * s.adj_close::DOUBLE
                            + (1.0 - 2.0 / 27.0) * m.ema26_state
                        )
                    ) + (1.0 - 2.0 / 10.0) * m.macd_dea AS macd_dea,
                    2.0 * (
                        (
                            2.0 / 13.0 * s.adj_close::DOUBLE
                            + (1.0 - 2.0 / 13.0) * m.ema12_state
                        ) - (
                            2.0 / 27.0 * s.adj_close::DOUBLE
                            + (1.0 - 2.0 / 27.0) * m.ema26_state
                        )
                    ) - 2.0 * (
                        2.0 / 10.0 * (
                            (
                                2.0 / 13.0 * s.adj_close::DOUBLE
                                + (1.0 - 2.0 / 13.0) * m.ema12_state
                            ) - (
                                2.0 / 27.0 * s.adj_close::DOUBLE
                                + (1.0 - 2.0 / 27.0) * m.ema26_state
                            )
                        ) + (1.0 - 2.0 / 10.0) * m.macd_dea
                    ) AS macd_hist
                FROM macd AS m
                JOIN source AS s
                    ON s.market = m.market
                    AND s.symbol = m.symbol
                    AND s.rn = m.rn + 1
            )
            SELECT
                source.market,
                source.symbol,
                source.trade_date,
                source.trade_year,
                CASE
                    WHEN source.prev_close IS NULL OR source.prev_close = 0 THEN NULL
                    ELSE source.adj_close / source.prev_close - 1
                END AS pct_chg,
                source.ma5,
                source.ma10,
                source.ma20,
                source.ma60,
                source.ma120,
                source.ma250,
                source.vol_ma5,
                source.vol_ma20,
                source.high_20,
                source.low_20,
                CASE
                    WHEN source.low_20 IS NULL OR source.low_20 = 0 THEN NULL
                    ELSE source.high_20 / source.low_20 - 1
                END AS range_20,
                macd.macd_dif,
                macd.macd_dea,
                macd.macd_hist
            FROM source
            JOIN macd
                USING (market, symbol, trade_date, trade_year, rn)
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )
