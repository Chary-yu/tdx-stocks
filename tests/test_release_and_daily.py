from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks import __version__
from tdx_stocks.cli import _rewrite_legacy_argv, _validate_output_aliases, build_parser
from tdx_stocks.cli import main as cli_main
from tdx_stocks.config import AppConfig, PathsConfig, load_config, write_default_config
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

    def test_web_package_modules_are_importable(self) -> None:
        self.assertIsNotNone(importlib.util.find_spec("tdx_stocks.web.app"))
        self.assertIsNotNone(importlib.util.find_spec("tdx_stocks.web.data_loader"))

    def test_write_default_config_uses_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tdx_stocks.toml"
            write_default_config(path)
            payload = path.read_text(encoding="utf-8")
        self.assertIn('tdx_vipdoc = ""', payload)
        self.assertIn('tdx_export = ""', payload)
        self.assertIn('data_root = "./Database"', payload)
        self.assertIn('plugin_dir = "~/.tdx-stocks/plugins"', payload)

    def test_load_config_uses_environment_path_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            vipdoc = Path(tmp) / "vipdoc"
            export_dir = Path(tmp) / "export"
            plugin_dir = Path(tmp) / "plugins"
            config_path = Path(tmp) / "tdx_stocks.toml"
            config_path.write_text(
                """
[paths]
tdx_vipdoc = ""
tdx_export = ""
data_root = ""
plugin_dir = ""
""".strip(),
                encoding="utf-8",
            )
            with patch.dict(
                os.environ,
                {
                    "TDX_STOCKS_TDX_VIPDOC": vipdoc.as_posix(),
                    "TDX_STOCKS_TDX_EXPORT": export_dir.as_posix(),
                    "TDX_STOCKS_DATA_ROOT": data_root.as_posix(),
                    "TDX_STOCKS_PLUGIN_DIR": plugin_dir.as_posix(),
                },
                clear=False,
            ):
                config = load_config(config_path)
        self.assertEqual(config.paths.tdx_vipdoc, vipdoc)
        self.assertEqual(config.paths.tdx_export, export_dir)
        self.assertEqual(config.paths.data_root, data_root)
        self.assertEqual(config.paths.plugin_dir, plugin_dir)

    def test_audit_doctor_reports_missing_required_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "tdx_stocks.toml"
            config_path.write_text(
                """
[paths]
tdx_vipdoc = ""
tdx_export = ""
data_root = ""
""".strip(),
                encoding="utf-8",
            )
            buffer = StringIO()
            with redirect_stderr(buffer):
                code = cli_main(["audit", "doctor", "--config", str(config_path)])
        self.assertEqual(code, 6)
        self.assertIn("tdx_vipdoc is not configured", buffer.getvalue())
        self.assertIn("TDX_STOCKS_TDX_VIPDOC", buffer.getvalue())


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

    def test_save_daily_report_keeps_existing_json_when_replace_fails(self) -> None:
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
            outputs={},
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            latest_json = data_root / "reports" / "daily" / "latest.json"
            latest_json.parent.mkdir(parents=True, exist_ok=True)
            latest_json.write_text('{"old": true}', encoding="utf-8")
            markdown = render_daily_markdown(report)
            original_replace = Path.replace
            calls = {"count": 0}

            def failing_replace(self, target):
                calls["count"] += 1
                if calls["count"] == 1:
                    raise RuntimeError("boom")
                return original_replace(self, target)

            with patch.object(Path, "replace", failing_replace):
                with self.assertRaises(RuntimeError):
                    save_daily_report(data_root, report, markdown)

            self.assertEqual(latest_json.read_text(encoding="utf-8"), '{"old": true}')


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
                                                    with patch("tdx_stocks.daily.workflow.write_daily_json_file", return_value=Path("/tmp/daily-compare.json")):
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
