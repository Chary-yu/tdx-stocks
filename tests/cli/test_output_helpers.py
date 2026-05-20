from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.commands.output import emit_report_table, write_rows


class OutputHelpersTest(unittest.TestCase):
    def test_write_rows_supports_terminal_json_csv_and_files(self) -> None:
        rows = [{"symbol": "600519", "score": 88.5}]
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "nested" / "rows.csv"
            json_path = Path(tmp) / "nested" / "rows.json"
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                write_rows(rows, columns=["symbol", "score"], format_name="table", to=None)
            self.assertIn("symbol", stdout.getvalue())
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                write_rows(rows, columns=["symbol", "score"], format_name="json", to=None)
            self.assertIn("\"symbol\"", stdout.getvalue())
            write_rows(rows, columns=["symbol", "score"], format_name="csv", to=csv_path)
            write_rows(rows, columns=["symbol", "score"], format_name="json", to=json_path)
            self.assertTrue(csv_path.exists())
            self.assertTrue(json_path.exists())

    def test_emit_report_table_supports_json_periods_and_dir_creation(self) -> None:
        report = {
            "rows": [{"symbol": "600519", "score": 88.5}],
            "schema_version": "backtest-report-v1",
        }
        periods_report = {
            "schema_version": "backtest-report-v1",
            "strategy_name": "trend-strength",
            "strategy_names": ["trend-strength"],
            "periods": [{"trade_date": "2024-01-01", "return": 0.1}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "reports" / "report.txt"
            emit_report_table(report, format_name="json", to=output_path)
            self.assertTrue(output_path.exists())
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                emit_report_table(report, format_name="table", to=None)
            self.assertIn("symbol", stdout.getvalue())
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                emit_report_table(periods_report, format_name="table", to=None)
            self.assertIn("backtest report", stdout.getvalue())

    def test_unsupported_format_raises_value_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported output format"):
            write_rows([{"x": 1}], columns=["x"], format_name="xml", to=None)
        with self.assertRaisesRegex(ValueError, "unsupported output format"):
            emit_report_table({"rows": []}, format_name="xml", to=None)
