from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from tdx_stocks.query import format_bytes, print_rows, register_query_macros, validate_table

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
                con.execute("SELECT tdx_symbol_code('sh600519')").fetchone()[0],
                "600519",
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_market('sh600519')").fetchone()[0],
                "sh",
            )
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
