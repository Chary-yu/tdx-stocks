from __future__ import annotations

import contextlib
import io
import unittest

from tdx_stocks.cli import main as cli_main


class HelpCommandTest(unittest.TestCase):
    def test_workflow_help_is_available(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["help", "workflow"])
        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("Recommended workspace workflow", text)
        self.assertIn("tdx-stocks run daily --explain", text)
