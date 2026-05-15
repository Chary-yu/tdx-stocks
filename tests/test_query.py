from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.duckdb_ops import build_factors
from tdx_stocks.query import (
    build_stock_sql,
    format_bytes,
    normalize_output_data,
    print_rows,
    register_query_macros,
    validate_table,
)

try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None


class QueryHelpersTest(unittest.TestCase):
    def test_validate_table(self) -> None:
        validate_table("raw_daily")
        with self.assertRaises(ValueError):
            validate_table("not_a_table")

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1536), "1.5 KB")

    def test_print_rows_empty(self) -> None:
        with patch("builtins.print") as mocked_print:
            print_rows(["a"], [])
        mocked_print.assert_called_once_with("(no rows)")

    def test_print_rows_formats_numbers(self) -> None:
        with patch("builtins.print") as mocked_print:
            print_rows(
                ["price", "volume", "amount"],
                [{"price": 101.239, "volume": 1234567, "amount": 987654321.0}],
            )
        rendered = "\n".join(call.args[0] for call in mocked_print.call_args_list)
        self.assertIn("101.24", rendered)
        self.assertIn("1.23M", rendered)
        self.assertIn("987.65M", rendered)

    def test_normalize_output_data_rounds_values(self) -> None:
        normalized = normalize_output_data(
            [{"price": 101.239, "volume": 1234567, "amount": 987654321.0}]
        )
        self.assertEqual(normalized[0]["price"], 101.24)
        self.assertEqual(normalized[0]["volume"], "1.23M")
        self.assertEqual(normalized[0]["amount"], "987.65M")

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_register_query_macros_last_n_days(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE adj_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    adj_close DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO adj_daily VALUES
                    ('sh', '600519', DATE '2024-01-02', 100.0),
                    ('sh', '600519', DATE '2024-01-03', 101.0),
                    ('sh', '600519', DATE '2024-01-04', 102.0),
                    ('sz', '000001', DATE '2024-01-04', 10.0)
                """
            )
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    pct_chg DOUBLE
                )
                """
            )
            register_query_macros(con)

            rows = con.execute(
                """
                SELECT market, symbol, trade_date, adj_close
                FROM last_n_days('600519.SH', 2)
                """
            ).fetchall()

            self.assertEqual(
                rows,
                [
                    ("sh", "600519", date(2024, 1, 4), 102.0),
                    ("sh", "600519", date(2024, 1, 3), 101.0),
                ],
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_code('sh600519')").fetchone()[0],
                "600519",
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_market('600519.SH')").fetchone()[0],
                "sh",
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_market('sh600519')").fetchone()[0],
                "sh",
            )
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_stock_sql_joins_daily_and_factors(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE raw_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume BIGINT,
                    amount DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO raw_daily VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, 100.0, 101.0,
                     99.0, 100.5, 1000, 100500.0),
                    ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0,
                     100.0, 101.5, 1100, 111650.0)
                """
            )
            con.execute(
                """
                CREATE TABLE adj_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    adj_open DOUBLE,
                    adj_high DOUBLE,
                    adj_low DOUBLE,
                    adj_close DOUBLE,
                    adj_factor DOUBLE,
                    volume BIGINT,
                    amount DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO adj_daily VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, 100.0, 101.0,
                     99.0, 100.5, 1.0, 1000, 100500.0),
                    ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0,
                     100.0, 101.5, 1.0, 1100, 111650.0)
                """
            )
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    pct_chg DOUBLE,
                    ma5 DOUBLE,
                    ma10 DOUBLE,
                    ma20 DOUBLE,
                    ma60 DOUBLE,
                    ma120 DOUBLE,
                    ma250 DOUBLE,
                    vol_ma5 DOUBLE,
                    vol_ma20 DOUBLE,
                    high_20 DOUBLE,
                    low_20 DOUBLE,
                    range_20 DOUBLE,
                    macd_dif DOUBLE,
                    macd_dea DOUBLE,
                    macd_hist DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO factors VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, NULL, 100.5, 100.5,
                     100.5, 100.5, 100.5, 100.5, 1000.0, 1000.0, 101.0, 99.0,
                     0.0202020202, 0.0, 0.0, 0.0),
                    ('sh', '600519', DATE '2024-01-04', 2024, 0.0099502488, 101.0,
                     101.0, 101.0, 101.0, 101.0, 101.0, 1100.0, 1100.0, 102.0, 100.0,
                     0.02, 0.01, 0.01, 0.0)
                """
            )
            register_query_macros(con)

            sql = build_stock_sql(con, "600519.SH", limit=1)
            result = con.execute(sql)
            row = result.fetchone()
            columns = [item[0] for item in result.description]
            row_map = dict(zip(columns, row, strict=True))

            self.assertEqual(
                columns[:5],
                ["market", "symbol", "trade_date", "trade_year", "open"],
            )
            self.assertEqual(row_map["market"], "sh")
            self.assertEqual(row_map["symbol"], "600519")
            self.assertEqual(row_map["trade_date"], date(2024, 1, 4))
            self.assertEqual(row_map["adj_close"], 101.5)
            self.assertEqual(row_map["pct_chg"], 0.0099502488)
            self.assertEqual(row_map["ma120"], 101.0)
            self.assertEqual(row_map["macd_hist"], 0.0)
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_factors_generates_ma120_ma250_macd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "adj_daily"
            output_dir = tmp_path / "factors"
            con = duckdb.connect(":memory:")
            try:
                con.execute(
                    f"""
                    COPY (
                        SELECT *
                        FROM (
                            VALUES
                                (
                                    'sh',
                                    '600519',
                                    DATE '2024-01-02',
                                    2024,
                                    10.0,
                                    10.5,
                                    9.5,
                                    10.0,
                                    1000,
                                    10000.0,
                                    1.0
                                ),
                                (
                                    'sh',
                                    '600519',
                                    DATE '2024-01-03',
                                    2024,
                                    12.0,
                                    12.5,
                                    11.5,
                                    12.0,
                                    1100,
                                    13200.0,
                                    1.0
                                ),
                                (
                                    'sh',
                                    '600519',
                                    DATE '2024-01-04',
                                    2024,
                                    11.0,
                                    11.5,
                                    10.5,
                                    11.0,
                                    1200,
                                    13200.0,
                                    1.0
                                )
                        ) AS t(
                            market, symbol, trade_date, trade_year, adj_open, adj_high,
                            adj_low, adj_close, volume, amount, adj_factor
                        )
                    )
                    TO '{input_dir.as_posix()}'
                    (FORMAT PARQUET, PARTITION_BY (trade_year, market))
                    """
                )

                build_factors(con, input_dir, output_dir, "zstd")

                rows = con.execute(
                    f"""
                    SELECT trade_date, ma120, ma250, macd_dif, macd_dea, macd_hist
                    FROM read_parquet(
                        '{output_dir.as_posix()}/**/*.parquet',
                        hive_partitioning=true
                    )
                    ORDER BY trade_date
                    """
                ).fetchall()

                closes = [10.0, 12.0, 11.0]
                alpha12 = 2.0 / 13.0
                alpha26 = 2.0 / 27.0
                alpha9 = 2.0 / 10.0
                ema12 = closes[0]
                ema26 = closes[0]
                dea = 0.0
                expected = []
                for close in closes:
                    ema12 = alpha12 * close + (1.0 - alpha12) * ema12
                    ema26 = alpha26 * close + (1.0 - alpha26) * ema26
                    dif = ema12 - ema26
                    dea = alpha9 * dif + (1.0 - alpha9) * dea
                    hist = 2.0 * (dif - dea)
                    expected.append((dif, dea, hist))

                self.assertEqual(rows[0][1], 10.0)
                self.assertEqual(rows[0][2], 10.0)
                self.assertAlmostEqual(rows[0][3], 0.0, places=10)
                self.assertAlmostEqual(rows[0][4], 0.0, places=10)
                self.assertAlmostEqual(rows[0][5], 0.0, places=10)
                self.assertEqual(rows[1][1], 11.0)
                self.assertEqual(rows[1][2], 11.0)
                self.assertAlmostEqual(rows[1][3], expected[1][0], places=10)
                self.assertAlmostEqual(rows[1][4], expected[1][1], places=10)
                self.assertAlmostEqual(rows[1][5], expected[1][2], places=10)
                self.assertEqual(rows[2][1], 11.0)
                self.assertEqual(rows[2][2], 11.0)
                self.assertAlmostEqual(rows[2][3], expected[2][0], places=10)
                self.assertAlmostEqual(rows[2][4], expected[2][1], places=10)
                self.assertAlmostEqual(rows[2][5], expected[2][2], places=10)
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
