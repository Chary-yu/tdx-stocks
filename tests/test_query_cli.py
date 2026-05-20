from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tdx_stocks.cli import main as cli_main
from tdx_stocks.config import AppConfig, PathsConfig
from tdx_stocks.commands.query import parse_columns
from tdx_stocks.query import build_select_sql, build_stock_sql, fetch_dicts, register_query_macros

duckdb = pytest.importorskip("duckdb")
pytestmark = pytest.mark.integration


class QueryCliSmokeTest(unittest.TestCase):
    def _make_context(self):
        con = duckdb.connect(":memory:")
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
            CREATE TABLE adj_daily (
                market VARCHAR,
                symbol VARCHAR,
                trade_date DATE,
                trade_year BIGINT,
                adj_open DOUBLE,
                adj_high DOUBLE,
                adj_low DOUBLE,
                adj_close DOUBLE,
                adj_factor DOUBLE
            )
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
                ret_1 DOUBLE,
                ret_20 DOUBLE,
                ma20 DOUBLE,
                ma60 DOUBLE,
                pos_20 DOUBLE,
                dd_20 DOUBLE,
                vol_ratio_20 DOUBLE,
                amount_ma20 DOUBLE
            )
            """
        )
        con.execute(
            """
            INSERT INTO raw_daily VALUES
                ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0, 100.0, 101.5, 1100, 111650.0)
            """
        )
        con.execute(
            """
            INSERT INTO adj_daily VALUES
                ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0, 100.0, 101.5, 1.0)
            """
        )
        con.execute(
            """
            INSERT INTO factors VALUES
                ('sh', '600519', DATE '2024-01-04', 2024, 0.01, 0.01, 0.02, 101.0, 100.0, 0.8, -0.01, 0.2, 120000000.0)
            """
        )
        register_query_macros(con)
        return SimpleNamespace(con=con, manifest={"run_id": "run-1"}, close=lambda: None)

    def test_query_status_schema_head_sql_stock_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            export_path = Path(tmp) / "export.csv"
            config = AppConfig(paths=PathsConfig(data_root=data_root, tdx_export=Path(tmp)))
            ctx = self._make_context()
            try:
                with (
                    patch("tdx_stocks.commands.query.load_config", return_value=config),
                    patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                ):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(["query", "status", "--config", "dummy.toml", "--json"])
                    self.assertEqual(status_code, 0)
                    self.assertIn("run_id", stdout.getvalue())

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(["query", "schema", "raw_daily", "--config", "dummy.toml", "--json"])
                    self.assertEqual(status_code, 0)
                    self.assertIn("trade_date", stdout.getvalue())

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(
                            [
                                "query",
                                "table",
                                "raw_daily",
                                "--json",
                                "--columns",
                                "market,symbol,trade_date",
                                "--limit",
                                "1",
                            ]
                        )
                    self.assertEqual(status_code, 0)
                    self.assertIn("600519", stdout.getvalue())

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(
                            [
                                "query",
                                "sql",
                                "--config",
                                "dummy.toml",
                                "--json",
                                "--unsafe-sql",
                                "SELECT symbol, close FROM raw_daily",
                            ]
                        )
                    self.assertEqual(status_code, 0)
                    self.assertIn("600519", stdout.getvalue())

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(
                            [
                                "query",
                                "price",
                                "600519.SH",
                                "--json",
                                "--limit",
                                "1",
                            ]
                        )
                    self.assertEqual(status_code, 0)
                    self.assertIn("adj_close", stdout.getvalue())

                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        status_code = cli_main(
                            [
                                "query",
                                "export",
                                "raw_daily",
                                "--output",
                                export_path.as_posix(),
                                "--json",
                                "--limit",
                                "1",
                            ]
                        )
                    self.assertEqual(status_code, 0)
                    self.assertTrue(export_path.exists())
                    self.assertIn("exported_rows", stdout.getvalue())
            finally:
                ctx.con.close()

    def test_query_helpers_support_column_parsing_and_fetching(self) -> None:
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
                    ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0, 100.0, 101.5, 1100, 111650.0)
                """
            )
            sql = build_select_sql(con, "raw_daily", columns=parse_columns("market,symbol"), limit=1)
            columns, rows = fetch_dicts(con, sql)
        finally:
            con.close()

        self.assertEqual(columns, ["market", "symbol"])
        self.assertEqual(rows[0]["symbol"], "600519")
        self.assertIn("SELECT market, symbol", sql)

    def test_query_sql_requires_explicit_unsafe_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root, tdx_export=Path(tmp)))
            ctx = self._make_context()
            try:
                with (
                    patch("tdx_stocks.commands.query.load_config", return_value=config),
                    patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                ):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        status_code = cli_main(
                            [
                                "query",
                                "sql",
                                "--config",
                                "dummy.toml",
                                "SELECT symbol FROM raw_daily",
                            ]
                        )
                    self.assertEqual(status_code, 6)
                    self.assertIn("--unsafe-sql", stderr.getvalue())
            finally:
                ctx.con.close()

    def test_query_sql_preserves_existing_multiline_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root, tdx_export=Path(tmp)))
            ctx = self._make_context()
            try:
                with (
                    patch("tdx_stocks.commands.query.load_config", return_value=config),
                    patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                ):
                    captured_sql: list[str] = []

                    def fake_fetch_dicts(_con, sql):
                        captured_sql.append(sql)
                        return ["symbol", "close"], [{"symbol": "600519", "close": 101.5}]

                    with patch("tdx_stocks.commands.query.fetch_dicts", side_effect=fake_fetch_dicts):
                        stdout = io.StringIO()
                        with contextlib.redirect_stdout(stdout):
                            status_code = cli_main(
                                [
                                    "query",
                                    "sql",
                                    "--config",
                                    "dummy.toml",
                                    "--unsafe-sql",
                                    "--json",
                                    "--limit",
                                    "2",
                                    "SELECT symbol, close FROM raw_daily\n  LIMIT   1",
                                ]
                            )
                    self.assertEqual(status_code, 0)
                    self.assertIn("600519", stdout.getvalue())
                    self.assertEqual(len(captured_sql), 1)
                    self.assertEqual(captured_sql[0].count("LIMIT"), 1)
            finally:
                ctx.con.close()
