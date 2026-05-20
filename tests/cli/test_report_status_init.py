from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main


class ReportStatusInitTest(unittest.TestCase):
    def test_report_formats_and_output_path(self) -> None:
        doc = {"schema_version": "daily-report-v1", "summary": {}, "steps": []}
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "report.json"
            with patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path(tmp)))), patch(
                "tdx_stocks.commands.report.load_daily_report",
                return_value=doc,
            ), patch("tdx_stocks.commands.report.render_daily_json", return_value={"ok": True}), patch(
                "tdx_stocks.commands.report.render_daily_markdown",
                return_value="# report\n",
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--format", "json", "--output", output_path.as_posix()])
                self.assertEqual(code, 0)
                self.assertTrue(output_path.exists())
                code = cli_main(["report", "--format", "markdown"])
                self.assertEqual(code, 0)

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

    def test_status_and_init_succeed_with_mocks(self) -> None:
        with patch("tdx_stocks.commands.status._load_optional_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=Path("/tmp")))), patch(
            "tdx_stocks.commands.status._build_status_payload",
            return_value={"config_file": "x", "config_exists": True, "data_root": "x", "data_root_exists": True, "latest_data_version": None, "latest_trade_date": None, "latest_run_status": None, "latest_daily_report": None, "latest_portfolio_report": None, "warnings": 0, "errors": 0},
        ):
            code = cli_main(["status"])
        self.assertEqual(code, 0)

        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                with patch("tdx_stocks.commands.init.Path.cwd", return_value=Path(tmp)):
                    code = cli_main(["init", "--force", "--data-root", "Database"])
            finally:
                pass
        self.assertEqual(code, 0)
