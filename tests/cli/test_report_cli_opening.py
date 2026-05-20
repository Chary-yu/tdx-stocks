from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main


class ReportOpeningCliTest(unittest.TestCase):
    def test_report_default_no_open_and_json_contract(self) -> None:
        doc = {"schema_version": "daily-report-v1", "summary": {}, "steps": []}
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            with (
                patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=data_root))),
                patch("tdx_stocks.commands.report.load_daily_report", return_value=doc),
                patch("tdx_stocks.commands.report.render_daily_markdown", return_value="# daily\n"),
                patch("tdx_stocks.reports.opening.open_file") as mocked_open,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report"])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_called_once()

                mocked_open.reset_mock()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--no-open"])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "--format", "json"])
                self.assertEqual(code, 0)
                self.assertNotIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()

    def test_report_strategy_prints_path_and_skips_json_open(self) -> None:
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
            data_root = Path(tmp)
            with (
                patch("tdx_stocks.commands.report.load_config", return_value=SimpleNamespace(paths=SimpleNamespace(data_root=data_root))),
                patch("tdx_stocks.commands.report.load_saved_report", return_value=report),
                patch("tdx_stocks.commands.report.render_strategy_markdown", return_value="# strategy\n"),
                patch("tdx_stocks.reports.opening.open_file") as mocked_open,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "strategy", "trend-strength"])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_open.assert_called_once()

                mocked_open.reset_mock()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["report", "strategy", "trend-strength", "--format", "json"])
                self.assertEqual(code, 0)
                self.assertNotIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()
