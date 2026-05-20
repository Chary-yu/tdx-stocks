from __future__ import annotations

import unittest
import re
from pathlib import Path

import pytest

from tdx_stocks.cli import build_parser
from tdx_stocks.factor_sql import render_copy_factors_sql
from tdx_stocks.factors.catalog import list_factor_definitions
from tdx_stocks.factors.reports import build_data_quality_report, build_factor_catalog_report
from tdx_stocks.factors.xsec import build_xsec_factors
from tdx_stocks.query import register_latest_views
from tdx_stocks.strategies.registry import list_strategies

duckdb = pytest.importorskip("duckdb")


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

    def test_factors_copy_sql_includes_std_pctchg_columns(self) -> None:
        sql = render_copy_factors_sql(Path("/tmp/factors"), "zstd")
        self.assertIn("std_pctchg_20", sql)
        self.assertIn("std_pctchg_60", sql)
        self.assertIn("vol_ratio_5_60", sql)
        self.assertIn("price_vol_corr_20", sql)

    def test_xsec_builder_emits_pct_rank_ret_60(self) -> None:
        statements: list[str] = []

        class FakeCon:
            def execute(self, sql: str):
                statements.append(sql)
                return self

        build_xsec_factors(FakeCon(), Path("/tmp/factors"), Path("/tmp/out"), "zstd")
        self.assertTrue(any("pct_rank_ret_60" in sql for sql in statements))

    def test_factor_full_view_includes_pct_rank_ret_60(self) -> None:
        statements: list[str] = []

        class FakeResult:
            def __init__(self, rows):
                self._rows = rows

            def fetchall(self):
                return self._rows

        class FakeCon:
            def execute(self, sql: str):
                statements.append(sql)
                if sql.startswith("DESCRIBE factors_xsec"):
                    return FakeResult([
                        ("rank_ret_20", "DOUBLE"),
                        ("rank_ret_60", "DOUBLE"),
                        ("pct_rank_ret_20", "DOUBLE"),
                        ("pct_rank_ret_60", "DOUBLE"),
                        ("pct_rank_amount_ma20", "DOUBLE"),
                        ("pct_rank_vol_20", "DOUBLE"),
                        ("rs_ret_20", "DOUBLE"),
                        ("rs_ret_60", "DOUBLE"),
                        ("rs_score", "DOUBLE"),
                        ("is_top_ret_20", "INTEGER"),
                        ("is_top_ret_60", "INTEGER"),
                        ("is_new_high_60", "INTEGER"),
                        ("is_new_high_120", "INTEGER"),
                        ("is_new_high_250", "INTEGER"),
                        ("pct_from_high_60", "DOUBLE"),
                        ("pct_from_high_120", "DOUBLE"),
                        ("amount_stability_20", "DOUBLE"),
                        ("vol_20_pct_rank", "DOUBLE"),
                        ("amount_ma20_pct_rank", "DOUBLE"),
                        ("atr_pct_14_pct_rank", "DOUBLE"),
                        ("risk_score", "DOUBLE"),
                        ("is_high_volatility", "INTEGER"),
                    ])
                if sql.startswith("DESCRIBE factors_quality"):
                    return FakeResult([("quality_score", "DOUBLE")])
                return FakeResult([])

        register_latest_views(FakeCon(), {"factors": "x", "factors_xsec": "y", "factors_quality": "z"})
        self.assertTrue(any("pct_rank_ret_60" in sql for sql in statements if "CREATE OR REPLACE VIEW factor_full" in sql))

    def test_strategy_required_fields_exist_in_factor_tables(self) -> None:
        factors = _factor_columns()
        factor_full = set(factors)
        factor_full.update(_xsec_columns())
        factor_full.update(_factor_full_columns())

        missing: list[str] = []
        for definition in list_strategies():
            source_table = _strategy_source_table(definition.name)
            available = factor_full if source_table == "factor_full" else factors
            absent = [field for field in definition.required_fields if field not in available]
            if absent:
                missing.append(f"{definition.name} -> {source_table}: {', '.join(absent)}")

        self.assertEqual(missing, [], msg="\n".join(missing))

    def test_data_quality_report_has_expected_shape(self) -> None:
        report = build_data_quality_report({"run_id": "run-1"}, [{"name": "check-1"}], factor_quality={"summary": {"missing_price_flag": 1}})
        self.assertEqual(report["schema_version"], "data-quality-report-v1")
        self.assertEqual(report["summary"]["run_id"], "run-1")
        self.assertEqual(report["checks"][0]["name"], "check-1")
        self.assertEqual(report["factor_quality"]["summary"]["missing_price_flag"], 1)
        self.assertEqual(report["factor_quality_report"]["summary"]["missing_price_flag"], 1)

    def test_parser_contains_factors_and_quality_report_commands(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["query", "factor", "list"])
        self.assertEqual(args.command, "query")
        self.assertEqual(args.query_command, "factor")
        self.assertEqual(args.factor_command, "list")
        args = parser.parse_args(["query", "factor", "rank", "rs_score", "--as-of", "latest"])
        self.assertEqual(args.query_command, "factor")
        self.assertEqual(args.factor_command, "rank")
        self.assertEqual(args.factor, "rs_score")
        args = parser.parse_args(["query", "tables"])
        self.assertEqual(args.query_command, "tables")

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


def _factor_columns() -> set[str]:
    text = Path("src/tdx_stocks/factor_sql.py").read_text(encoding="utf-8")
    start = text.index("columns = [", text.index("def render_copy_factors_sql("))
    end = text.index("    for window in _extra_windows", start)
    return set(re.findall(r'"([A-Za-z0-9_]+)"', text[start:end]))


def _xsec_columns() -> set[str]:
    statements: list[str] = []

    class FakeCon:
        def execute(self, sql: str):
            statements.append(sql)
            return self

    build_xsec_factors(FakeCon(), Path("/tmp/factors"), Path("/tmp/out"), "zstd")
    if not statements:
        return set()
    sql = statements[0]
    return set(re.findall(r"AS ([A-Za-z0-9_]+)", sql))


def _factor_full_columns() -> set[str]:
    text = Path("src/tdx_stocks/query.py").read_text(encoding="utf-8")
    start = text.index("xsec_selects = _build_factor_full_selects")
    mid = text.index("quality_selects = _build_factor_full_selects", start)
    end = text.index("table_name=\"factors_quality\"", mid)
    return set(re.findall(r'"([A-Za-z0-9_]+)"', text[start:end]))


def _strategy_source_table(strategy_name: str) -> str:
    if strategy_name in {"smart-money", "multi-factor"}:
        return "factor_full"
    root = Path("src/tdx_stocks/strategies")
    for path in root.glob("**/*.py"):
        payload = path.read_text(encoding="utf-8")
        if f'name="{strategy_name}"' not in payload and f"name='{strategy_name}'" not in payload:
            continue
        return "factor_full" if 'source_table="factor_full"' in payload else "factors"
    return "factors"
