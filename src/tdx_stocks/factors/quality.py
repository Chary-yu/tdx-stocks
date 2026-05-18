from __future__ import annotations

from pathlib import Path

from ..duckdb_ops import parquet_glob, sql_literal


def build_factor_quality(con, adj_daily_dir: Path, factors_dir: Path, output_dir: Path, compression: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    adj_source = f"read_parquet('{sql_literal(parquet_glob(adj_daily_dir))}', hive_partitioning=true)"
    factors_source = f"read_parquet('{sql_literal(parquet_glob(factors_dir))}', hive_partitioning=true)"
    con.execute(
        f"""
        COPY (
            WITH adj AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    adj_open,
                    adj_high,
                    adj_low,
                    adj_close,
                    volume,
                    amount,
                    row_number() OVER (PARTITION BY market, symbol ORDER BY trade_date) AS rn,
                    lag(adj_close) OVER (PARTITION BY market, symbol ORDER BY trade_date) AS prev_close
                FROM {adj_source}
            ),
            joined AS (
                SELECT
                    adj.market,
                    adj.symbol,
                    adj.trade_date,
                    adj.trade_year,
                    adj.adj_open,
                    adj.adj_high,
                    adj.adj_low,
                    adj.adj_close,
                    adj.volume,
                    adj.amount,
                    adj.rn,
                    adj.prev_close,
                    fac.pct_chg,
                    fac.ret_5,
                    fac.amount_ma20,
                    fac.atr_pct_14,
                    fac.vol_20
                FROM adj
                LEFT JOIN {factors_source} AS fac
                    USING (market, symbol, trade_date, trade_year)
            )
            SELECT
                market,
                symbol,
                trade_date,
                trade_year,
                CASE WHEN adj_open IS NULL OR adj_high IS NULL OR adj_low IS NULL OR adj_close IS NULL THEN 1 ELSE 0 END AS missing_price_flag,
                CASE WHEN amount IS NULL OR amount <= 0 OR amount_ma20 IS NULL OR amount_ma20 <= 0 THEN 1 ELSE 0 END AS zero_amount_flag,
                CASE
                    WHEN adj_open IS NULL OR adj_high IS NULL OR adj_low IS NULL OR adj_close IS NULL THEN 1
                    WHEN adj_low > adj_high OR adj_open > adj_high OR adj_close > adj_high OR adj_open < adj_low OR adj_close < adj_low THEN 1
                    ELSE 0
                END AS invalid_ohlc_flag,
                CASE WHEN prev_close IS NOT NULL AND adj_close = prev_close AND COALESCE(volume, 0) = 0 THEN 1 ELSE 0 END AS stale_price_flag,
                CASE WHEN pct_chg IS NOT NULL AND abs(pct_chg) > 0.2 THEN 1 WHEN ret_5 IS NOT NULL AND abs(ret_5) > 0.3 THEN 1 ELSE 0 END AS extreme_return_flag,
                CASE WHEN rn IS NOT NULL AND rn < 60 THEN 1 ELSE 0 END AS low_history_flag,
                CASE
                    WHEN adj_open IS NULL OR adj_high IS NULL OR adj_low IS NULL OR adj_close IS NULL THEN 0
                    ELSE 100
                        - 20 * (CASE WHEN amount IS NULL OR amount <= 0 OR amount_ma20 IS NULL OR amount_ma20 <= 0 THEN 1 ELSE 0 END)
                        - 20 * (CASE WHEN adj_low > adj_high OR adj_open > adj_high OR adj_close > adj_high OR adj_open < adj_low OR adj_close < adj_low THEN 1 ELSE 0 END)
                        - 15 * (CASE WHEN prev_close IS NOT NULL AND adj_close = prev_close AND COALESCE(volume, 0) = 0 THEN 1 ELSE 0 END)
                        - 25 * (CASE WHEN pct_chg IS NOT NULL AND abs(pct_chg) > 0.2 THEN 1 WHEN ret_5 IS NOT NULL AND abs(ret_5) > 0.3 THEN 1 ELSE 0 END)
                        - 20 * (CASE WHEN rn IS NOT NULL AND rn < 60 THEN 1 ELSE 0 END)
                END AS quality_score
            FROM joined
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )


def build_factor_quality_summary(con, factors_dir: Path) -> dict[str, object]:
    source = f"read_parquet('{sql_literal(parquet_glob(factors_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            min(trade_date) AS min_date,
            max(trade_date) AS max_date,
            sum(CASE WHEN adj_close IS NULL THEN 1 ELSE 0 END) AS missing_adj_close_rows,
            sum(CASE WHEN pct_chg IS NULL THEN 1 ELSE 0 END) AS missing_pct_chg_rows,
            sum(CASE WHEN amount_ma20 IS NULL THEN 1 ELSE 0 END) AS missing_amount_ma20_rows,
            sum(CASE WHEN vol_20 IS NULL THEN 1 ELSE 0 END) AS missing_vol_20_rows,
            sum(CASE WHEN atr_pct_14 IS NULL THEN 1 ELSE 0 END) AS missing_atr_pct_14_rows
        FROM {source}
        """
    ).fetchone()
    return {
        "rows": row[0],
        "symbols": row[1],
        "min_date": str(row[2]) if row[2] is not None else None,
        "max_date": str(row[3]) if row[3] is not None else None,
        "missing_adj_close_rows": row[4],
        "missing_pct_chg_rows": row[5],
        "missing_amount_ma20_rows": row[6],
        "missing_vol_20_rows": row[7],
        "missing_atr_pct_14_rows": row[8],
    }
