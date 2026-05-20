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

    def test_stock_default_columns_and_full_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ctx = self._fake_context()
            rows = [
                {
                    "market": "sh",
                    "symbol": "600519",
                    "trade_date": "2024-01-31",
                    "open": 1,
                    "high": 2,
                    "low": 1,
                    "close": 2,
                    "volume": 10,
                    "amount": 20,
                    "adj_close": 2,
                    "adj_factor": 1,
                    "pct_chg": 0.1,
                    "ret_5": 0.2,
                    "ma20": 1.5,
                    "extra": "x",
                }
            ]
            with (
                patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
                patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                patch("tdx_stocks.commands.query.build_stock_sql", return_value="SELECT symbol FROM raw_daily"),
                patch("tdx_stocks.commands.query.fetch_dicts", return_value=(list(rows[0].keys()), rows)),
                patch("tdx_stocks.commands.query.write_rows") as mocked_write,
            ):
                code = cli_main(["query", "stock", "600519.SH"])
                self.assertEqual(code, 0)
                self.assertEqual(mocked_write.call_args_list[0].kwargs["columns"], [
                    "market",
                    "symbol",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                    "amount",
                    "adj_close",
                    "adj_factor",
                    "pct_chg",
                    "ret_5",
                    "ma20",
                ])

                code = cli_main(["query", "stock", "600519.SH", "--full", "--json"])
                self.assertEqual(code, 0)
                self.assertEqual(mocked_write.call_args_list[1].kwargs["columns"], list(rows[0].keys()))

    def test_stock_columns_and_output_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_path = Path(tmp) / "stock.csv"
            ctx = self._fake_context()
            rows = [{"market": "sh", "symbol": "600519", "close": 2.0, "volume": 10}]
            with (
                patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
                patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
                patch("tdx_stocks.commands.query.build_stock_sql", return_value="SELECT symbol FROM raw_daily"),
                patch("tdx_stocks.commands.query.fetch_dicts", return_value=(list(rows[0].keys()), rows)),
                patch("tdx_stocks.commands.query.write_rows") as mocked_write,
            ):
                code = cli_main(
                    [
                        "query",
                        "stock",
                        "600519.SH",
                        "--columns",
                        "market,symbol,close",
                        "--format",
                        "csv",
                        "--output",
                        export_path.as_posix(),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertEqual(mocked_write.call_args.kwargs["columns"], ["market", "symbol", "close"])
            self.assertEqual(mocked_write.call_args.kwargs["format_name"], "csv")
            self.assertEqual(mocked_write.call_args.kwargs["to"], export_path)

    def test_stock_unknown_columns_and_full_notice(self) -> None:
        ctx = self._fake_context()
        rows = [{"market": "sh", "symbol": "600519", "close": 2.0}]
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
            patch("tdx_stocks.commands.query.build_stock_sql", return_value="SELECT symbol FROM raw_daily"),
            patch("tdx_stocks.commands.query.fetch_dicts", return_value=(list(rows[0].keys()), rows)),
            patch("tdx_stocks.commands.query.write_rows"),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(["query", "stock", "600519.SH", "--full"])
            self.assertEqual(code, 0)
            self.assertIn("建议使用 --columns", stderr.getvalue())

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(["query", "stock", "600519.SH", "--columns", "missing"])
            self.assertEqual(code, 6)
            self.assertIn("unknown stock columns", stderr.getvalue())

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
                ["query", "strategies", "--grouped", "--json"],
                ["query", "strategy", "trend-strength"],
            ):
                with self.subTest(argv=argv):
                    stdout = io.StringIO()
                    with contextlib.redirect_stdout(stdout):
                        code = cli_main(argv)
                    self.assertEqual(code, 0, stdout.getvalue())

    def test_rank_delegates_to_factor_rank_helper(self) -> None:
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.factors.cmd_factors_rank", return_value=0) as mocked_rank,
        ):
            code = cli_main(["query", "rank", "pct_rank_ret_20", "--json"])
        self.assertEqual(code, 0)
        mocked_rank.assert_called_once()

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

    def test_legacy_factor_syntax_is_rejected_with_clear_guidance(self) -> None:
        ctx = self._fake_context()
        with (
            patch("tdx_stocks.commands.query.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.query.open_query_context", return_value=ctx),
        ):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(["query", "factor", "describe", "rsi_14"])
        self.assertEqual(code, 6)
        self.assertIn("legacy query factor subcommands are no longer supported", stderr.getvalue())
