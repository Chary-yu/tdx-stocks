from __future__ import annotations

from pathlib import Path

from ..duckdb_ops import parquet_glob, sql_literal


def build_xsec_factors(con, factors_dir: Path, output_dir: Path, compression: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    source = f"read_parquet('{sql_literal(parquet_glob(factors_dir))}', hive_partitioning=true)"
    con.execute(
        f"""
        COPY (
            WITH base AS (
                SELECT
                    market,
                    symbol,
                    trade_date,
                    trade_year,
                    ret_20,
                    ret_60,
                    amount_ma20,
                    amount_ma60,
                    vol_20,
                    atr_pct_14,
                    adj_close,
                    high_60,
                    high_120,
                    high_250,
                    adj_close / NULLIF(high_60, 0) - 1 AS pct_from_high_60,
                    adj_close / NULLIF(high_120, 0) - 1 AS pct_from_high_120,
                    CASE WHEN high_60 IS NOT NULL AND adj_close >= high_60 THEN 1 ELSE 0 END AS is_new_high_60,
                    CASE WHEN high_120 IS NOT NULL AND adj_close >= high_120 THEN 1 ELSE 0 END AS is_new_high_120,
                    CASE WHEN high_250 IS NOT NULL AND adj_close >= high_250 THEN 1 ELSE 0 END AS is_new_high_250
                FROM {source}
            ),
            ranked AS (
                SELECT
                    *,
                rank() OVER (PARTITION BY trade_date ORDER BY ret_20 DESC NULLS LAST, market, symbol) AS rank_ret_20,
                rank() OVER (PARTITION BY trade_date ORDER BY ret_60 DESC NULLS LAST, market, symbol) AS rank_ret_60,
                rank() OVER (PARTITION BY trade_date ORDER BY amount_ma20 DESC NULLS LAST, market, symbol) AS rank_amount_ma20,
                rank() OVER (PARTITION BY trade_date ORDER BY vol_20 ASC NULLS LAST, market, symbol) AS rank_vol_20,
                rank() OVER (PARTITION BY trade_date ORDER BY atr_pct_14 ASC NULLS LAST, market, symbol) AS rank_atr_pct_14,
                count(*) OVER (PARTITION BY trade_date) AS trade_day_count
                FROM base
            )
            SELECT
                market,
                symbol,
                trade_date,
                trade_year,
                rank_ret_20,
                rank_ret_60,
                CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_ret_20 - 1)::DOUBLE / (trade_day_count - 1) END AS pct_rank_ret_20,
                CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_amount_ma20 - 1)::DOUBLE / (trade_day_count - 1) END AS pct_rank_amount_ma20,
                CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_vol_20 - 1)::DOUBLE / (trade_day_count - 1) END AS pct_rank_vol_20,
                ret_20 - avg(ret_20) OVER (PARTITION BY trade_date) AS rs_ret_20,
                ret_60 - avg(ret_60) OVER (PARTITION BY trade_date) AS rs_ret_60,
                0.6 * CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_ret_20 - 1)::DOUBLE / (trade_day_count - 1) END
                    + 0.4 * CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_ret_60 - 1)::DOUBLE / (trade_day_count - 1) END AS rs_score,
                CASE WHEN rank_ret_20 <= 10 THEN 1 ELSE 0 END AS is_top_ret_20,
                CASE WHEN rank_ret_60 <= 10 THEN 1 ELSE 0 END AS is_top_ret_60,
                is_new_high_60,
                is_new_high_120,
                is_new_high_250,
                pct_from_high_60,
                pct_from_high_120,
                CASE WHEN amount_ma20 IS NULL OR amount_ma60 IS NULL OR amount_ma60 = 0 THEN NULL ELSE 1 - abs(amount_ma20 - amount_ma60) / amount_ma60 END AS amount_stability_20,
                1.0 - CASE WHEN trade_day_count <= 1 THEN 0.0 ELSE (rank_vol_20 - 1)::DOUBLE / (trade_day_count - 1) END AS vol_20_pct_rank,
                1.0 - CASE WHEN trade_day_count <= 1 THEN 0.0 ELSE (rank_amount_ma20 - 1)::DOUBLE / (trade_day_count - 1) END AS amount_ma20_pct_rank,
                CASE WHEN trade_day_count <= 1 THEN 1.0 ELSE 1.0 - (rank_atr_pct_14 - 1)::DOUBLE / (trade_day_count - 1) END AS atr_pct_14_pct_rank,
                CASE WHEN vol_20 IS NULL OR atr_pct_14 IS NULL THEN NULL ELSE 0.5 * vol_20 + 0.5 * atr_pct_14 END AS risk_score,
                CASE WHEN vol_20 IS NOT NULL AND atr_pct_14 IS NOT NULL AND (vol_20 > 0.08 OR atr_pct_14 > 0.1) THEN 1 ELSE 0 END AS is_high_volatility
            FROM ranked
        )
        TO '{sql_literal(output_dir.as_posix())}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION {compression.upper()})
        """
    )
