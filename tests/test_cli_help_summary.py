from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class CliHelpSummaryTest(unittest.TestCase):
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
        for command_name in (
            "init-config",
            "doctor",
            "build",
            "rebuild",
            "status",
            "tables",
            "schema",
            "head",
            "stock",
            "sql",
            "export",
        ):
            self.assertIn(f"`{command_name}`", output)
        self.assertIn("build", output)
        self.assertIn("rebuild", output)
        self.assertIn("stock", output)


if __name__ == "__main__":
    unittest.main()
