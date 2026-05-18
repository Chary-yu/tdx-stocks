from __future__ import annotations

import unittest

from tdx_stocks.cli import build_parser
from tdx_stocks.factors.catalog import list_factor_definitions
from tdx_stocks.factors.reports import build_data_quality_report, build_factor_catalog_report


class FactorCatalogTest(unittest.TestCase):
    def test_factor_catalog_contains_core_xsec_and_quality_items(self) -> None:
        names = [definition.name for definition in list_factor_definitions()]
        self.assertIn("rank_ret_20", names)
        self.assertIn("rs_score", names)
        self.assertIn("missing_price_flag", names)

    def test_factor_catalog_report_has_expected_schema(self) -> None:
        report = build_factor_catalog_report(data_run_id="run-1", factor_version="windowed-v1")
        self.assertEqual(report["schema_version"], "factor-catalog-v1")
        self.assertEqual(report["data_run_id"], "run-1")
        self.assertEqual(report["factor_version"], "windowed-v1")
        self.assertGreater(len(report["factors"]), 0)

    def test_data_quality_report_has_expected_shape(self) -> None:
        report = build_data_quality_report({"run_id": "run-1"}, [{"name": "check-1"}])
        self.assertEqual(report["schema_version"], "data-quality-report-v1")
        self.assertEqual(report["summary"]["run_id"], "run-1")
        self.assertEqual(report["checks"][0]["name"], "check-1")

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
