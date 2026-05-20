from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main
from tdx_stocks.daily.store import latest_daily_md_path


class ReportStatusInitTest(unittest.TestCase):
    def test_report_formats_and_opening_contract(self) -> None:
        doc = {"schema_version": "daily-report-v1", "summary": {}, "steps": []}
        with tempfile.TemporaryDirectory() as tmp:
            markdown_path = latest_daily_md_path(Path(tmp))
            json_path = Path(tmp) / "report.json"
            with (
                patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path(tmp)))),
                patch("tdx_stocks.commands.report.load_daily_report", return_value=doc),
                patch("tdx_stocks.commands.report.render_daily_json", return_value={"ok": True}),
                patch("tdx_stocks.commands.report.render_daily_markdown", return_value="# report\n"),
                patch("tdx_stocks.reports.opening.open_file") as mocked_open,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--format", "markdown"])
                self.assertEqual(code, 0)
                self.assertTrue(markdown_path.exists())
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_called_once()

                mocked_open.reset_mock()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--format", "markdown", "--no-open", "--output", markdown_path.as_posix()])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--format", "json", "--output", json_path.as_posix()])
                self.assertEqual(code, 0)
                self.assertTrue(json_path.exists())
                self.assertNotIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

    def test_report_strategy_opening_contract(self) -> None:
        report = {
            "strategy_name": "trend-strength",
            "as_of": "latest",
            "generated_at": "now",
            "data_run_id": "run-1",
            "candidate_count": 1,
            "excluded_count": 0,
            "candidates": [{"market": "sh", "symbol": "600519"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            md_path = Path(tmp) / "reports" / "strategies" / "latest" / "trend-strength.md"
            with (
                patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path(tmp)))),
                patch("tdx_stocks.commands.report.load_saved_report", return_value=report),
                patch("tdx_stocks.commands.report.render_strategy_markdown", return_value="# strategy\n"),
                patch("tdx_stocks.reports.opening.open_file") as mocked_open,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "strategy", "trend-strength"])
                self.assertEqual(code, 0)
                self.assertTrue(md_path.exists())
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_called_once()

                mocked_open.reset_mock()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "strategy", "trend-strength", "--no-open"])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "strategy", "trend-strength", "--format", "json"])
                self.assertEqual(code, 0)
                self.assertNotIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

    def test_report_strategy_list_and_missing_report(self) -> None:
        rows = [{"strategy_name": "trend-strength", "as_of": "latest", "generated_at": "now", "path": "/tmp/x"}]
        with patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path("/tmp")))), patch(
            "tdx_stocks.commands.report.list_saved_reports",
            return_value=rows,
        ), patch("tdx_stocks.commands.report.load_saved_report", return_value=None):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli_main(["report", "strategy", "--list"])
            self.assertEqual(code, 0)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                code = cli_main(["report", "strategy", "trend-strength"])
            self.assertEqual(code, 2)

    def test_status_missing_manifest_is_handled(self) -> None:
        with patch("tdx_stocks.commands.status._load_optional_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path("/tmp")))), patch(
            "tdx_stocks.commands.status.load_latest_manifest",
            side_effect=FileNotFoundError("missing"),
        ), patch("tdx_stocks.commands.status.load_latest_daily_report", return_value=None), patch(
            "tdx_stocks.commands.status.load_latest_portfolio_report",
            return_value=None,
        ), patch("tdx_stocks.commands.status.load_latest_run_report", return_value=None):
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli_main(["status"])
        self.assertEqual(code, 0)
        self.assertIn("latest_data_version", stdout.getvalue())

    def test_status_and_init_succeed_with_mocks(self) -> None:
        with patch("tdx_stocks.commands.status._load_optional_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path("/tmp")))), patch(
            "tdx_stocks.commands.status._build_status_payload",
            return_value={"config_file": "x", "config_exists": True, "data_root": "x", "data_root_exists": True, "latest_data_version": None, "latest_trade_date": None, "latest_run_status": None, "latest_daily_report": None, "latest_portfolio_report": None, "warnings": 0, "errors": 0},
        ):
            code = cli_main(["status"])
        self.assertEqual(code, 0)

        with tempfile.TemporaryDirectory() as tmp:
            with patch("tdx_stocks.commands.init.Path.cwd", return_value=Path(tmp)):
                code = cli_main(["init", "--force", "--data-root", "Database"])
        self.assertEqual(code, 0)
