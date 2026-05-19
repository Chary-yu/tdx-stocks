from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from tdx_stocks.cli import build_parser


class CliHelpSummaryTest(unittest.TestCase):
    def test_top_level_help_mentions_help_summary(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("tdx-stocks help-summary", help_text)
        self.assertIn("markdown CLI manual", help_text)

    def test_generate_cli_help_summary_contains_supported_commands(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        result = subprocess.run(
            [
                sys.executable,
                "tools/generate_cli_help_summary.py",
                "--output",
                "-",
            ],
            cwd=Path(__file__).resolve().parents[1],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout
        self.assertIn("tdx-stocks CLI 摘要", output)
        self.assertIn("Advanced commands", output)
        for command_name in (
            "init",
            "run",
            "ui",
            "examples",
            "doctor",
            "status",
            "report",
            "data",
            "audit",
            "query",
            "strategy",
            "portfolio",
            "daily",
            "sync",
            "init-config",
            "help-summary",
        ):
            self.assertIn(f"`{command_name}`", output)
        self.assertIn("兼容别名", output)


if __name__ == "__main__":
    unittest.main()
