from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.reports.opening import open_report_if_needed, print_report_path, should_open_report


class ReportOpeningTest(unittest.TestCase):
    def test_should_open_report_respects_json_and_no_open_flags(self) -> None:
        args = SimpleNamespace(no_open=False)
        self.assertTrue(should_open_report(args, json_mode=False))
        self.assertFalse(should_open_report(args, json_mode=True))
        self.assertFalse(should_open_report(SimpleNamespace(no_open=True), json_mode=False))

    def test_print_and_open_are_separated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                print_report_path(path, json_mode=False)
            self.assertIn("Report:", stdout.getvalue())

            with patch("tdx_stocks.reports.opening.open_file") as mocked_open:
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    open_report_if_needed(SimpleNamespace(no_open=False), path, json_mode=False)
                self.assertEqual(stdout.getvalue(), "")
                mocked_open.assert_called_once_with(path)

            with patch("tdx_stocks.reports.opening.open_file") as mocked_open:
                open_report_if_needed(SimpleNamespace(no_open=True), path, json_mode=False)
                mocked_open.assert_not_called()
