from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

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
                    vol_ma5 DOUBLE,
                    vol_ma20 DOUBLE,
                    high_20 DOUBLE,
                    low_20 DOUBLE,
                    range_20 DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO factors VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, NULL, 100.5, 100.5,
                     100.5, 100.5, 1000.0, 1000.0, 101.0, 99.0, 0.0202020202),
                    ('sh', '600519', DATE '2024-01-04', 2024, 0.0099502488, 101.0,
                     101.0, 101.0, 101.0, 1100.0, 1100.0, 102.0, 100.0, 0.02)
                """
            )
            register_query_macros(con)

            sql = build_stock_sql(con, "600519.SH", limit=1)
            result = con.execute(sql)
            row = result.fetchone()
            columns = [item[0] for item in result.description]

            self.assertEqual(columns[:5], ["market", "symbol", "trade_date", "trade_year", "open"])
            self.assertEqual(row[0], "sh")
            self.assertEqual(row[1], "600519")
            self.assertEqual(row[2], date(2024, 1, 4))
            self.assertEqual(row[13], 101.5)
            self.assertEqual(row[15], 0.0099502488)
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
