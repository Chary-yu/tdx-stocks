from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main


class QueryCommandTest(unittest.TestCase):
    def _fake_context(self):
        return SimpleNamespace(con=SimpleNamespace(close=lambda: None), manifest={"run_id": "run-1"}, close=lambda: None)

    def test_stock_json_and_csv_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "stock.csv"
            ctx = self._fake_context()
            with (
                patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
                patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                patch("tdx_stocks.commands.query.build_stock_sql", return_value="SELECT symbol FROM raw_daily"),
                patch("tdx_stocks.commands.query.fetch_dicts", return_value=(["symbol"], [{"symbol": "600519"}])),
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["query", "stock", "600519.SH", "--json"])
                self.assertEqual(code, 0)
                self.assertIn("600519", stdout.getvalue())

                code = cli_main(["query", "stock", "600519.SH", "--format", "csv", "--output", export_path.as_posix()])
                self.assertEqual(code, 0)
                self.assertTrue(export_path.exists())

    def test_factor_and_strategy_queries_work(self) -> None:
        ctx = self._fake_context()
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
            patch("tdx_stocks.commands.query.list_strategies", return_value=[]),
        ):
            for argv in (
                ["query", "factors", "--json"],
                ["query", "factor", "pct_rank_ret_20", "--json"],
                ["query", "rank", "pct_rank_ret_20", "--json"],
                ["query", "strategies", "--grouped", "--json"],
            ):
                with self.subTest(argv=argv):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(argv)
                    self.assertEqual(code, 0, stdout.getvalue())

    def test_strategy_explain_via_query_entrypoint(self) -> None:
        ctx = self._fake_context()
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
            patch("tdx_stocks.commands.query.get_strategy") as mocked_get_strategy,
            patch("tdx_stocks.commands.strategy.cmd_strategy_explain", return_value=0) as mocked_explain,
        ):
            mocked_get_strategy.return_value = SimpleNamespace(name="trend-strength")
            code = cli_main([
                "query",
                "strategy",
                "trend-strength",
                "--symbol",
                "600519.SH",
                "--explain",
            ])
        self.assertEqual(code, 0)
        mocked_explain.assert_called_once()

    def test_query_sql_requires_unsafe_flag(self) -> None:
        ctx = self._fake_context()
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(["query", "sql", "SELECT 1"])
        self.assertEqual(code, 6)
        self.assertIn("--unsafe-sql", stderr.getvalue())
