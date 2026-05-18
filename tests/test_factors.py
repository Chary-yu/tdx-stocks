from __future__ import annotations

import unittest

from tdx_stocks.cli import build_parser
from tdx_stocks.factors.catalog import list_factor_definitions
from tdx_stocks.factors.reports import build_data_quality_report, build_factor_catalog_report

try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None


class FactorCatalogTest(unittest.TestCase):
    def test_factor_catalog_contains_core_xsec_and_quality_items(self) -> None:
        names = [definition.name for definition in list_factor_definitions()]
        self.assertIn("rank_ret_20", names)
        self.assertIn("rs_score", names)
        self.assertIn("missing_price_flag", names)
        self.assertTrue(next(definition for definition in list_factor_definitions() if definition.name == "pct_rank_ret_20").higher_is_better)

    def test_factor_catalog_report_has_expected_schema(self) -> None:
        report = build_factor_catalog_report(data_run_id="run-1", factor_version="windowed-v1")
        self.assertEqual(report["schema_version"], "factor-catalog-v1")
        self.assertEqual(report["data_run_id"], "run-1")
        self.assertEqual(report["factor_version"], "windowed-v1")
        self.assertGreater(len(report["factors"]), 0)

    def test_data_quality_report_has_expected_shape(self) -> None:
        report = build_data_quality_report({"run_id": "run-1"}, [{"name": "check-1"}], factor_quality={"summary": {"missing_price_flag": 1}})
        self.assertEqual(report["schema_version"], "data-quality-report-v1")
        self.assertEqual(report["summary"]["run_id"], "run-1")
        self.assertEqual(report["checks"][0]["name"], "check-1")
        self.assertEqual(report["factor_quality"]["summary"]["missing_price_flag"], 1)
        self.assertEqual(report["factor_quality_report"]["summary"]["missing_price_flag"], 1)

    def test_parser_contains_factors_and_quality_report_commands(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["factors", "list"])
        self.assertEqual(args.command, "factors")
        self.assertEqual(args.factors_command, "list")
        args = parser.parse_args(["factors", "rank", "rs_score", "--as-of", "latest"])
        self.assertEqual(args.factors_command, "rank")
        self.assertEqual(args.factor, "rs_score")
        args = parser.parse_args(["data", "quality-report"])
        self.assertEqual(args.command, "data")
        self.assertEqual(args.data_command, "quality-report")

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_factor_rank_respects_higher_is_better(self) -> None:
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import patch

        from tdx_stocks.commands.factors import cmd_factors_rank
        from tdx_stocks.config import AppConfig, PathsConfig

        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE factor_full (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    pct_rank_ret_20 DOUBLE,
                    rank_ret_20 DOUBLE,
                    rs_score DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO factor_full VALUES
                    ('sh', '600001', DATE '2024-01-04', 0.2, 10, 0.3),
                    ('sh', '600000', DATE '2024-01-04', 0.9, 1, 0.8)
                """
            )
            args = SimpleNamespace(
                config=None,
                factor="pct_rank_ret_20",
                as_of="2024-01-04",
                limit=10,
                market=None,
                json=False,
            )

            class FakeContext:
                def __init__(self, con):
                    self.con = con

                def close(self) -> None:
                    return None

            with patch("tdx_stocks.commands.factors.load_config", return_value=AppConfig(paths=PathsConfig(data_root=Path("/tmp")))):
                with patch("tdx_stocks.commands.factors.open_query_context", return_value=FakeContext(con)):
                    from io import StringIO
                    from contextlib import redirect_stdout

                    stdout = StringIO()
                    with redirect_stdout(stdout):
                        cmd_factors_rank(args)

            self.assertIn("600000", stdout.getvalue())
            self.assertTrue(stdout.getvalue().find("600000") < stdout.getvalue().find("600001"))
        finally:
            con.close()
