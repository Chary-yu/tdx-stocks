from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from tdx_stocks import __version__
from tdx_stocks.cli import build_parser, main as cli_main, _rewrite_legacy_argv, _validate_output_aliases
from tdx_stocks.config import AppConfig, PathsConfig
from tdx_stocks.daily.models import DailyRunReport
from tdx_stocks.daily.report import render_daily_markdown
from tdx_stocks.daily.store import load_daily_report, load_latest_daily_report, save_daily_report
from tdx_stocks.daily.workflow import run_daily_workflow
from tdx_stocks.portfolio import build_portfolio


class ReleaseConfigTest(unittest.TestCase):
    def test_version_is_0_6_0(self) -> None:
        self.assertEqual(__version__, "0.6.0")

    def test_pyproject_contains_hatch_targets(self) -> None:
        payload = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.hatch.build.targets.wheel]", payload)
        self.assertIn("[tool.hatch.build.targets.sdist]", payload)

    def test_root_help_has_no_legacy_alias_noise(self) -> None:
        help_text = build_parser().format_help()
        self.assertNotIn("build ==SUPPRESS==", help_text)
        self.assertNotIn("stock ==SUPPRESS==", help_text)
        self.assertNotIn("sql ==SUPPRESS==", help_text)

    def test_legacy_rewrite(self) -> None:
        self.assertEqual(_rewrite_legacy_argv(["build", "--config", "x"]), ["data", "build", "--config", "x"])
        self.assertEqual(_rewrite_legacy_argv(["stock", "600000.SH"]), ["query", "price", "600000.SH"])

    def test_output_alias_conflict_is_rejected(self) -> None:
        with self.assertRaisesRegex(Exception, "use either --output or --to"):
            _validate_output_aliases(["query", "export", "--output", "a.csv", "--to", "b.csv"])

    def test_portfolio_report_requires_strategy_for_report_source(self) -> None:
        with self.assertRaisesRegex(ValueError, "strategy is required"):
            build_portfolio(AppConfig(), source="report", as_of=None)


class DailyStoreTest(unittest.TestCase):
    def test_save_and_load_daily_report(self) -> None:
        report = DailyRunReport(
            schema_version="daily-report-v1",
            app_version="0.6.0",
            as_of="2024-01-31",
            generated_at="2024-02-01T10:00:00",
            data_run_id="run-1",
            status="success",
            steps=[],
            summary={"step_count": 0, "warning_count": 0, "error_count": 0},
            data_quality={},
            strategy_summary={},
            consensus_summary={},
            portfolio_summary={},
            rebalance_summary={},
            warnings=[],
            errors=[],
            outputs={"latest_json": "/tmp/latest.json"},
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            markdown = render_daily_markdown(report)
            paths = save_daily_report(data_root, report, markdown)
            self.assertTrue(Path(paths["latest_json"]).exists())
            self.assertTrue(Path(paths["daily_md"]).exists())
            self.assertIsNotNone(load_latest_daily_report(data_root))
            self.assertIsNotNone(load_daily_report(data_root, "2024-01-31"))


class DailyWorkflowTest(unittest.TestCase):
    def test_daily_workflow_skip_flags_and_outputs(self) -> None:
        fake_ctx = SimpleNamespace(con=object(), manifest={"run_id": "run-1"}, close=lambda: None)
        fake_strategy_step = SimpleNamespace(
            to_dict=lambda: {
                "step_name": "strategy:trend-strength",
                "status": "success",
                "message": "saved",
                "output_paths": ["/tmp/strategy.json"],
                "metrics": {"picked": 1},
                "duration_seconds": 0.01,
            }
        )
        fake_strategy_payload = {"steps": [fake_strategy_step], "warnings": [], "errors": []}
        fake_report = SimpleNamespace(
            to_dict=lambda: {
                "schema_version": "daily-report-v1",
                "app_version": "0.6.0",
                "as_of": "2024-01-31",
                "generated_at": "2024-02-01T10:00:00",
                "data_run_id": "run-1",
                "status": "success",
                "steps": [fake_strategy_step.to_dict()],
                "summary": {"step_count": 1, "warning_count": 0, "error_count": 0},
                "data_quality": {"checks": []},
                "strategy_summary": {"strategies": ["trend-strength"]},
                "consensus_summary": {"min_hit": 2},
                "portfolio_summary": {"summary": "skipped"},
                "rebalance_summary": {"summary": "skipped"},
                "warnings": [],
                "errors": [],
                "outputs": {"strategy_json": "/tmp/strategy.json"},
            },
        )
        config = AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-daily-test"))
        with patch("tdx_stocks.daily.workflow.build_dataset", return_value={"run_id": "run-1"}):
            with patch("tdx_stocks.daily.workflow.open_query_context", return_value=fake_ctx):
                with patch("tdx_stocks.daily.workflow._load_latest_trade_date", return_value=date(2024, 1, 31)):
                    with patch("tdx_stocks.daily.workflow._run_strategies", return_value=(fake_strategy_payload, {"strategy_json": "/tmp/strategy.json"})):
                        with patch("tdx_stocks.daily.workflow.compare_strategies", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})):
                            with patch("tdx_stocks.daily.workflow.build_consensus", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})):
                                with patch("tdx_stocks.daily.workflow.build_portfolio", return_value=SimpleNamespace(to_dict=lambda: {"holdings": [], "risk_summary": {}}, holdings=[])):
                                    with patch("tdx_stocks.daily.workflow.save_portfolio_report", return_value={"latest_json": "/tmp/portfolio.json"}):
                                        with patch("tdx_stocks.daily.workflow.build_rebalance_plan") as mocked_rebalance:
                                            with patch("tdx_stocks.daily.workflow.save_rebalance_plan", return_value=(Path("/tmp/rebalance.json"), Path("/tmp/rebalance.csv"))):
                                                with patch("tdx_stocks.daily.workflow.save_daily_report", return_value={"latest_json": "/tmp/daily.json", "latest_md": "/tmp/daily.md", "daily_json": "/tmp/daily.json", "daily_md": "/tmp/daily.md", "manifest": "/tmp/manifest.json"}):
                                                    with patch("tdx_stocks.daily.workflow._write_daily_json_file", return_value=Path("/tmp/daily-compare.json")):
                                                        mocked_rebalance.return_value = SimpleNamespace(to_dict=lambda: {"turnover": 0.0}, turnover=0.0)
                                                        result = run_daily_workflow(
                                                            config,
                                                            as_of=date(2024, 1, 31),
                                                            skip_portfolio=True,
                                                            skip_report=True,
                                                        )
        self.assertEqual(result.report.status, "success")
        self.assertIn("strategy_json", result.outputs)

    def test_daily_report_markdown_has_sections(self) -> None:
        report = DailyRunReport(
            schema_version="daily-report-v1",
            app_version="0.6.0",
            as_of="2024-01-31",
            generated_at="2024-02-01T10:00:00",
            data_run_id="run-1",
            status="success",
            steps=[],
            summary={"step_count": 0, "warning_count": 1, "error_count": 0},
            data_quality={},
            strategy_summary={},
            consensus_summary={},
            portfolio_summary={},
            rebalance_summary={},
            warnings=["warn"],
            errors=[],
            outputs={},
        )
        markdown = render_daily_markdown(report)
        self.assertIn("## Summary", markdown)
        self.assertIn("## Data Quality", markdown)
        self.assertIn("## Strategy Summary", markdown)
        self.assertIn("## Consensus", markdown)
        self.assertIn("## Portfolio", markdown)
        self.assertIn("## Rebalance Plan", markdown)
        self.assertIn("## Warnings", markdown)
        self.assertIn("## Errors", markdown)

    def test_cli_main_rejects_output_conflict(self) -> None:
        buffer = StringIO()
        with redirect_stderr(buffer):
            code = cli_main(["query", "export", "factors", "--output", "a.csv", "--to", "b.csv"])
        self.assertEqual(code, 6)
        self.assertIn("use either --output or --to", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
