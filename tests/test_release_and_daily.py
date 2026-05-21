from __future__ import annotations

import argparse
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

import pytest

from tdx_stocks import __version__
from tdx_stocks.cli import build_parser
from tdx_stocks.cli import main as cli_main
from tdx_stocks.config import AppConfig, PathsConfig, load_config, write_default_config
from tdx_stocks.commands.ui import cmd_ui
from tdx_stocks.daily.models import DailyRunReport
from tdx_stocks.daily.report import render_daily_markdown
from tdx_stocks.daily.store import list_daily_reports, load_daily_report, load_latest_daily_report, save_daily_report
from tdx_stocks.daily.workflow import run_daily_workflow
from tdx_stocks.commands.common import validate_output_alias
from tdx_stocks.portfolio import build_portfolio


class ReleaseConfigTest(unittest.TestCase):
    def test_version_is_0_6_0(self) -> None:
        self.assertEqual(__version__, "0.7.0")

    def test_pyproject_contains_hatch_targets(self) -> None:
        payload = Path("pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("[tool.hatch.build.targets.wheel]", payload)
        self.assertIn("[tool.hatch.build.targets.sdist]", payload)

    def test_root_help_has_no_legacy_alias_noise(self) -> None:
        help_text = build_parser().format_help()
        self.assertNotIn("build ==SUPPRESS==", help_text)
        self.assertNotIn("stock ==SUPPRESS==", help_text)
        self.assertNotIn("sql ==SUPPRESS==", help_text)

    def test_root_surface_matches_expected_commands(self) -> None:
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        visible = [choice.dest for choice in subparsers_action._choices_actions if choice.help != argparse.SUPPRESS]
        self.assertEqual(visible, ["init", "doctor", "sync", "run", "report", "query", "status", "ui", "help"])
        self.assertNotIn("data", visible)
        self.assertNotIn("audit", visible)
        self.assertNotIn("examples", visible)
        self.assertNotIn("factors", visible)
        self.assertNotIn("help-summary", visible)

    def test_output_alias_conflict_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "use either --output or --to"):
            validate_output_alias(SimpleNamespace(_output_option_strings=["--output", "--to"]))

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
        self.assertIn('tdx_vipdoc = "./vipdoc"', payload)
        self.assertIn('tdx_export = "./export"', payload)
        self.assertIn('data_root = "./Database"', payload)
        self.assertIn('portfolio_max_weight = 0.10', payload)
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

    def test_load_config_auto_detects_standard_tdx_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vipdoc = root / "vipdoc"
            export_dir = root / "T0002" / "export"
            (vipdoc / "sh" / "lday").mkdir(parents=True)
            (vipdoc / "sh" / "lday" / "sh600000.day").write_bytes(b"day")
            export_dir.mkdir(parents=True)
            (export_dir / "sh600000.txt").write_text("code,date,open,high,low,close,volume,amount\n", encoding="utf-8")
            with patch("tdx_stocks.config._candidate_tdx_roots", return_value=(root,)):
                config = load_config(None)
        self.assertEqual(config.paths.tdx_vipdoc, vipdoc)
        self.assertEqual(config.paths.tdx_export, export_dir)

    def test_doctor_reports_missing_required_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "tdx_stocks.toml"
            data_root = Path(tmp) / "missing-Database"
            vipdoc = Path(tmp) / "missing-vipdoc"
            export_dir = Path(tmp) / "missing-export"
            config_path.write_text(
                f"""
[paths]
tdx_vipdoc = "{vipdoc.as_posix()}"
tdx_export = "{export_dir.as_posix()}"
data_root = "{data_root.as_posix()}"
""".strip(),
                encoding="utf-8",
            )
            buffer = StringIO()
            with redirect_stderr(buffer):
                code = cli_main(["doctor", "--config", str(config_path)])
        self.assertEqual(code, 1)
        self.assertIn("tdx_vipdoc is not configured or missing", buffer.getvalue())
        self.assertIn("tdx_export is not configured or missing", buffer.getvalue())


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
            self.assertTrue(Path(paths["payload_json"]).exists())
            self.assertTrue(Path(paths["report_markdown"]).exists())
            self.assertIsNotNone(load_latest_daily_report(data_root))
            self.assertIsNotNone(load_daily_report(data_root, "2024-01-31"))

            rows = list_daily_reports(data_root)
            self.assertEqual(rows[0]["status"], "success")
            self.assertEqual(rows[0]["warnings"], 0)

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
            latest_json = data_root / "report_payloads" / "daily_2024-01-31.json"
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
                                    with patch("tdx_stocks.daily.workflow.save_portfolio_report", return_value={"payload_json": "/tmp/portfolio.json"}):
                                        with patch("tdx_stocks.daily.workflow.build_rebalance_plan") as mocked_rebalance:
                                            with patch("tdx_stocks.daily.workflow.save_rebalance_plan", return_value=(Path("/tmp/rebalance.json"), Path("/tmp/rebalance.csv"))):
                                                with patch("tdx_stocks.daily.workflow.save_daily_report", return_value={"payload_json": "/tmp/daily.json", "report_markdown": "/tmp/daily.md", "manifest": "/tmp/manifest.json"}):
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
        self.assertEqual(result.report.steps[-1]["step_name"], "daily_report")
        self.assertEqual(result.report.steps[-1]["status"], "skipped")

    def test_daily_workflow_preserves_zero_values_and_namespaces_outputs(self) -> None:
        fake_ctx = SimpleNamespace(con=object(), manifest={"run_id": "run-1"}, close=lambda: None)
        fake_portfolio = SimpleNamespace(
            as_of="2024-01-31",
            holdings=[{"market": "sh", "symbol": "600000", "weight": 1.0}],
            to_dict=lambda: {"holdings": [{"market": "sh", "symbol": "600000", "weight": 1.0}]},
        )
        config = AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-daily-test"))
        with (
            patch("tdx_stocks.daily.workflow.build_dataset", return_value={"run_id": "run-1"}),
            patch("tdx_stocks.daily.workflow.open_query_context", return_value=fake_ctx),
            patch("tdx_stocks.daily.workflow._load_latest_trade_date", return_value=date(2024, 1, 31)),
            patch("tdx_stocks.daily.workflow._run_strategies", return_value=({"steps": [], "warnings": [], "errors": []}, {})) as run_strategies_mock,
            patch("tdx_stocks.daily.workflow._run_compare", return_value={"rows": []}),
            patch("tdx_stocks.daily.workflow._run_consensus", return_value={"rows": []}) as run_consensus_mock,
            patch("tdx_stocks.daily.workflow.build_portfolio", return_value=fake_portfolio) as build_portfolio_mock,
            patch("tdx_stocks.daily.workflow.save_portfolio_report", return_value={"payload_json": "/tmp/portfolio.json"}),
            patch("tdx_stocks.daily.workflow.check_portfolio_risk", return_value=SimpleNamespace(passed=True, summary={})),
            patch("tdx_stocks.daily.workflow.save_daily_report", return_value={"payload_json": "/tmp/daily.json", "report_markdown": "/tmp/daily.md", "manifest": "/tmp/manifest.json"}),
            patch("tdx_stocks.daily.workflow.write_daily_json_file", side_effect=[Path("/tmp/compare.json"), Path("/tmp/consensus.json")]),
        ):
            result = run_daily_workflow(
                config,
                as_of=date(2024, 1, 31),
                strategy_limit=0,
                min_hit=0,
                portfolio_top=0,
                portfolio_weighting="",
                portfolio_max_weight=0.0,
                skip_report=True,
            )

        self.assertEqual(run_strategies_mock.call_args.kwargs["strategy_limit"], 0)
        self.assertEqual(run_consensus_mock.call_args.kwargs["min_hit"], 0)
        self.assertEqual(build_portfolio_mock.call_args.kwargs["top"], 0)
        self.assertEqual(build_portfolio_mock.call_args.kwargs["max_weight"], 0.0)
        self.assertIn("portfolio:payload_json", result.outputs)
        self.assertEqual(result.outputs["portfolio:payload_json"], "/tmp/portfolio.json")
        self.assertEqual(result.report.steps[-1]["step_name"], "daily_report")

    def test_daily_workflow_writes_report_with_empty_strategy_outputs(self) -> None:
        fake_ctx = SimpleNamespace(con=object(), manifest={"run_id": "run-1"}, close=lambda: None)
        config = AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-daily-test"))
        strategy_step = SimpleNamespace(
            to_dict=lambda: {
                "step_name": "strategy:trend-strength",
                "status": "success",
                "message": "saved",
                "output_paths": [],
                "metrics": {"picked": 0},
                "duration_seconds": 0.0,
            }
        )
        fake_strategy_payload = {"steps": [strategy_step], "warnings": [], "errors": []}
        with (
            patch("tdx_stocks.daily.workflow.build_dataset", return_value={"run_id": "run-1"}),
            patch("tdx_stocks.daily.workflow.open_query_context", return_value=fake_ctx),
            patch("tdx_stocks.daily.workflow._load_latest_trade_date", return_value=date(2024, 1, 31)),
            patch("tdx_stocks.daily.workflow._run_strategies", return_value=(fake_strategy_payload, {})),
            patch("tdx_stocks.daily.workflow.compare_strategies", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})),
            patch("tdx_stocks.daily.workflow.build_consensus", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})),
            patch("tdx_stocks.daily.workflow.write_daily_json_file", side_effect=[Path("/tmp/compare.json"), Path("/tmp/consensus.json")]),
            patch(
                "tdx_stocks.daily.workflow.save_daily_report",
                return_value={
                    "payload_json": "/tmp/daily.json",
                    "report_markdown": "/tmp/daily.md",
                    "manifest": "/tmp/manifest.json",
                },
            ),
            patch("tdx_stocks.daily.workflow.build_portfolio", return_value=SimpleNamespace(to_dict=lambda: {"holdings": [], "risk_summary": {}}, holdings=[])),
            patch("tdx_stocks.daily.workflow.save_portfolio_report", return_value={"payload_json": "/tmp/portfolio.json"}),
            patch("tdx_stocks.daily.workflow.build_rebalance_plan") as mocked_rebalance,
            patch("tdx_stocks.daily.workflow.check_portfolio_risk", return_value=SimpleNamespace(passed=True, summary={})),
        ):
            mocked_rebalance.return_value = SimpleNamespace(to_dict=lambda: {"turnover": 0.0}, turnover=0.0)
            result = run_daily_workflow(
                config,
                as_of=date(2024, 1, 31),
                skip_portfolio=True,
                skip_report=False,
            )

        self.assertEqual(result.report.status, "success")
        self.assertEqual(result.outputs["compare_json"], "/tmp/compare.json")
        self.assertEqual(result.outputs["consensus_json"], "/tmp/consensus.json")
        self.assertEqual(result.outputs["payload_json"], "/tmp/daily.json")

    def test_daily_workflow_skips_portfolio_when_strategies_are_skipped(self) -> None:
        fake_ctx = SimpleNamespace(
            con=SimpleNamespace(execute=lambda *args, **kwargs: SimpleNamespace(fetchone=lambda: (date(2024, 1, 31),))),
            manifest={"run_id": "run-1", "summary": {"trade_date": "2024-01-31"}},
            close=lambda: None,
        )
        config = AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-daily-test"))
        with (
            patch("tdx_stocks.daily.workflow.open_query_context", return_value=fake_ctx),
            patch("tdx_stocks.daily.workflow.build_portfolio") as build_portfolio_mock,
            patch("tdx_stocks.daily.workflow.load_current_holdings_csv") as load_current_holdings_mock,
            patch("tdx_stocks.daily.workflow.build_rebalance_plan") as build_rebalance_plan_mock,
            patch("tdx_stocks.daily.workflow.save_rebalance_plan") as save_rebalance_plan_mock,
            patch("tdx_stocks.daily.workflow.compare_strategies", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})),
            patch("tdx_stocks.daily.workflow.build_consensus", return_value=SimpleNamespace(to_dict=lambda: {"rows": []})),
        ):
            result = run_daily_workflow(
                config,
                as_of=date(2024, 1, 31),
                skip_strategies=True,
                skip_portfolio=False,
                current_holdings="holdings.csv",
                skip_report=True,
            )
        self.assertFalse(build_portfolio_mock.called)
        self.assertFalse(load_current_holdings_mock.called)
        self.assertFalse(build_rebalance_plan_mock.called)
        self.assertFalse(save_rebalance_plan_mock.called)
        self.assertIn("portfolio skipped because strategies were skipped", result.report.warnings)

    def test_daily_workflow_skips_rebalance_plan_when_requested(self) -> None:
        fake_ctx = SimpleNamespace(
            con=SimpleNamespace(execute=lambda *args, **kwargs: SimpleNamespace(fetchone=lambda: (date(2024, 1, 31),))),
            manifest={"run_id": "run-1", "summary": {"trade_date": "2024-01-31"}},
            close=lambda: None,
        )
        fake_portfolio = SimpleNamespace(
            as_of="2024-01-31",
            holdings=[{"market": "sh", "symbol": "600000", "weight": 1.0}],
            to_dict=lambda: {"holdings": [{"market": "sh", "symbol": "600000", "weight": 1.0}]},
        )
        config = AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-daily-test"))
        with (
            patch("tdx_stocks.daily.workflow.open_query_context", return_value=fake_ctx),
            patch("tdx_stocks.daily.workflow._run_strategies", return_value=({"steps": [], "warnings": [], "errors": []}, {})),
            patch("tdx_stocks.daily.workflow._run_compare", return_value={"rows": []}),
            patch("tdx_stocks.daily.workflow._run_consensus", return_value={"rows": []}),
            patch("tdx_stocks.daily.workflow.build_portfolio", return_value=fake_portfolio),
            patch("tdx_stocks.daily.workflow.save_portfolio_report", return_value={"payload_json": "/tmp/portfolio.json"}),
            patch("tdx_stocks.daily.workflow.load_current_holdings_csv") as load_current_holdings_mock,
            patch("tdx_stocks.daily.workflow.build_rebalance_plan") as build_rebalance_plan_mock,
            patch("tdx_stocks.daily.workflow.save_rebalance_plan") as save_rebalance_plan_mock,
            patch("tdx_stocks.daily.workflow.check_portfolio_risk", return_value=SimpleNamespace(passed=True, summary={})),
        ):
            result = run_daily_workflow(
                config,
                as_of=date(2024, 1, 31),
                current_holdings="holdings.csv",
                skip_strategies=False,
                skip_portfolio=False,
                skip_rebalance=True,
                skip_report=True,
            )
        self.assertFalse(load_current_holdings_mock.called)
        self.assertFalse(build_rebalance_plan_mock.called)
        self.assertFalse(save_rebalance_plan_mock.called)
        self.assertIn("rebalance plan skipped by --skip-rebalance", result.report.warnings)

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
        self.assertIn("## 运行摘要", markdown)
        self.assertIn("## 数据质量", markdown)
        self.assertIn("## 策略摘要", markdown)
        self.assertIn("## 共振股票", markdown)
        self.assertIn("## 组合摘要", markdown)
        self.assertIn("## 调仓计划", markdown)
        self.assertIn("## 警告", markdown)
        self.assertIn("## 错误", markdown)

    def test_cli_main_rejects_output_conflict(self) -> None:
        buffer = StringIO()
        with redirect_stderr(buffer):
            code = cli_main(["query", "export", "factors", "--output", "a.csv", "--to", "b.csv"])
        self.assertEqual(code, 6)
        self.assertIn("use either --output or --to", buffer.getvalue())

    @pytest.mark.integration
    def test_ui_command_launches_packaged_streamlit_app(self) -> None:
        args = SimpleNamespace(config=Path("tdx_stocks.toml"), host="127.0.0.1", port=8501, no_browser=True)
        with patch("tdx_stocks.commands.ui.importlib.util.find_spec", return_value=object()), patch(
            "tdx_stocks.commands.ui.subprocess.call",
            return_value=0,
        ) as mocked_call:
            code = cmd_ui(args)

        self.assertEqual(code, 0)
        called_args, called_kwargs = mocked_call.call_args
        self.assertIn("streamlit", called_args[0])
        self.assertTrue(str(called_args[0][4]).endswith("src/tdx_stocks/web/app.py"))
        self.assertEqual(called_kwargs["env"]["TDX_STOCKS_CONFIG"], "tdx_stocks.toml")


if __name__ == "__main__":
    unittest.main()
