from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pytest

from tdx_stocks.config_validators import validate_compression
from tdx_stocks.duckdb_ops import connect_duckdb, copy_adj_daily, copy_parquet_dataset, sql_literal

duckdb = pytest.importorskip("duckdb")


class CopyAdjDailyTest(unittest.TestCase):
    def test_dense_factor_map_matches_exact_trade_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            con = duckdb.connect(":memory:")
            try:
                raw_dir = tmp_path / "raw_daily"
                factor_dir = tmp_path / "adjustment_factors"
                output_dir = tmp_path / "adj_daily"
                _write_raw_daily(
                    con,
                    raw_dir,
                    [
                        ("sh", "600000", "2024-01-02", 2024, 10.0, 11.0, 9.0, 10.0, 100, 1000.0),
                        ("sh", "600000", "2024-01-03", 2024, 15.0, 16.0, 14.0, 15.0, 300, 4500.0),
                    ],
                )
                _write_adjustment_factors(
                    con,
                    factor_dir,
                    [
                        ("sh", "600000", "2024-01-02", "2024-01-02", 0.5, 2.0),
                        ("sh", "600000", "2024-01-03", "2024-01-03", 0.75, 3.0),
                    ],
                )

                copy_adj_daily(con, raw_dir, output_dir, "zstd", factor_dir, "qfq_factor")

                rows = _read_adj_daily(con, output_dir)
                self.assertEqual(rows, _read_exact_left_join_expected(con))
                self.assertEqual(
                    rows,
                    [
                        ("2024-01-02", 5.0, 200, 1000.0, 0.5),
                        ("2024-01-03", 11.25, 400, 4500.0, 0.75),
                    ],
                )
            finally:
                con.close()

    def test_sparse_interval_map_crosses_suspended_ex_date_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            con = duckdb.connect(":memory:")
            try:
                raw_dir = tmp_path / "raw_daily"
                factor_dir = tmp_path / "adjustment_factors"
                output_dir = tmp_path / "adj_daily"
                _write_raw_daily(
                    con,
                    raw_dir,
                    [
                        ("sh", "600000", "2024-01-02", 2024, 10.0, 10.0, 10.0, 10.0, 100, 1000.0),
                        ("sh", "600000", "2024-01-05", 2024, 5.0, 5.0, 5.0, 5.0, 200, 1000.0),
                    ],
                )
                _write_adjustment_factors(
                    con,
                    factor_dir,
                    [
                        ("sh", "600000", "2024-01-03", "2024-01-03", 0.5, 2.0),
                    ],
                )

                copy_adj_daily(con, raw_dir, output_dir, "zstd", factor_dir, "qfq_factor")

                rows = _read_adj_daily(con, output_dir)
                self.assertEqual(
                    rows,
                    [
                        ("2024-01-02", 10.0, 100, 1000.0, 1.0),
                        ("2024-01-05", 2.5, 400, 1000.0, 0.5),
                    ],
                )
            finally:
                con.close()

    def test_copy_parquet_dataset_writes_file_under_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            con = duckdb.connect(":memory:")
            try:
                source_dir = tmp_path / "corporate_actions"
                output_dir = tmp_path / "staging" / "corporate_actions"
                _write_adjustment_factors(
                    con,
                    source_dir,
                    [
                        ("sh", "600000", "2024-01-02", "2024-01-02", 1.0, 1.0),
                        ("sh", "600000", "2024-01-03", "2024-01-03", 1.0, 1.0),
                    ],
                )

                copy_parquet_dataset(con, source_dir, output_dir, "zstd")

                self.assertTrue((output_dir / "data.parquet").exists())
                rows = _read_generic_parquet(con, output_dir)
                self.assertEqual(len(rows), 2)
            finally:
                con.close()

    def test_connect_duckdb_rejects_invalid_memory_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp) / "duckdb tmp"
            with self.assertRaises(ValueError):
                connect_duckdb(temp_dir, "not-a-limit")

    def test_validate_compression_normalizes_and_rejects_injection(self) -> None:
        self.assertEqual(validate_compression("zstd"), "ZSTD")
        self.assertEqual(validate_compression("snappy"), "SNAPPY")
        with self.assertRaises(ValueError):
            validate_compression("zstd); drop table; --")

    def test_sql_literal_escapes_single_quotes(self) -> None:
        self.assertEqual(sql_literal("O'Reilly"), "O''Reilly")

    def test_connect_duckdb_accepts_special_characters_in_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temp_dir = Path(tmp) / "tmp'space"
            con = connect_duckdb(temp_dir, "1GB")
            try:
                self.assertTrue(temp_dir.exists())
            finally:
                con.close()


def _write_raw_daily(con, root: Path, rows: list[tuple]) -> None:
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE raw_input (
            market VARCHAR,
            symbol VARCHAR,
            trade_date DATE,
            trade_year INTEGER,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume BIGINT,
            amount DOUBLE
        )
        """
    )
    con.executemany("INSERT INTO raw_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    con.execute(
        f"""
        COPY raw_input
        TO '{root.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION ZSTD)
        """
    )


def _write_adjustment_factors(con, root: Path, rows: list[tuple]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    con.execute(
        """
        CREATE OR REPLACE TEMP TABLE factor_input (
            market VARCHAR,
            symbol VARCHAR,
            trade_date DATE,
            start_date DATE,
            end_date DATE,
            qfq_factor DOUBLE,
            hfq_factor DOUBLE,
            source VARCHAR
        )
        """
    )
    con.executemany(
        """
        INSERT INTO factor_input (
            market,
            symbol,
            trade_date,
            start_date,
            end_date,
            qfq_factor,
            hfq_factor,
            source
        )
        VALUES (?, ?, ?, ?, NULL, ?, ?, 'test')
        """,
        rows,
    )
    con.execute(
        f"""
        COPY factor_input
        TO '{(root / "data.parquet").as_posix()}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )


def _read_adj_daily(con, root: Path) -> list[tuple]:
    return [
        (str(trade_date), adj_close, volume, amount, adj_factor)
        for trade_date, adj_close, volume, amount, adj_factor in con.execute(
            f"""
            SELECT trade_date, adj_close, volume, amount, adj_factor
            FROM read_parquet('{root.as_posix()}/**/*.parquet', hive_partitioning=true)
            ORDER BY trade_date
            """
        ).fetchall()
    ]


def _read_generic_parquet(con, root: Path) -> list[tuple]:
    return con.execute(
        f"""
        SELECT market, symbol, trade_date, start_date, end_date, qfq_factor, hfq_factor, source
        FROM read_parquet('{root.as_posix()}/**/*.parquet', hive_partitioning=true)
        ORDER BY trade_date
        """
    ).fetchall()


def _read_exact_left_join_expected(con) -> list[tuple]:
    return [
        (str(trade_date), adj_close, volume, amount, adj_factor)
        for trade_date, adj_close, volume, amount, adj_factor in con.execute(
            """
            SELECT
                raw_input.trade_date,
                raw_input.close * factor_input.qfq_factor AS adj_close,
                CAST(ROUND(raw_input.volume / factor_input.qfq_factor, 0) AS BIGINT) AS volume,
                raw_input.amount,
                factor_input.qfq_factor AS adj_factor
            FROM raw_input
            LEFT JOIN factor_input
                ON raw_input.market = factor_input.market
                AND raw_input.symbol = factor_input.symbol
                AND raw_input.trade_date = factor_input.trade_date
            ORDER BY raw_input.trade_date
            """
        ).fetchall()
    ]


if __name__ == "__main__":
    unittest.main()
