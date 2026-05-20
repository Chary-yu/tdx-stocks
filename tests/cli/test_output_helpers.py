from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.commands.output import emit_report_table, write_rows


class OutputHelpersTest(unittest.TestCase):
    def test_write_rows_supports_terminal_and_file_targets(self) -> None:
        rows = [{"symbol": "600519", "score": 88.5}]
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "nested" / "rows.csv"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                write_rows(rows, columns=["symbol", "score"], format_name="csv", to=None)
            self.assertIn("symbol", stdout.getvalue())
            write_rows(rows, columns=["symbol", "score"], format_name="json", to=output_path)
            self.assertTrue(output_path.exists())

    def test_emit_report_table_supports_json_and_dir_creation(self) -> None:
        report = {"rows": [{"symbol": "600519", "score": 88.5}]}
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "reports" / "report.txt"
            emit_report_table(report, format_name="json", to=output_path)
            self.assertTrue(output_path.exists())

    def test_unsupported_format_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported output format"):
            write_rows([{"x": 1}], columns=["x"], format_name="xml", to=None)
        with self.assertRaisesRegex(ValueError, "unsupported output format"):
            emit_report_table({"rows": []}, format_name="xml", to=None)
