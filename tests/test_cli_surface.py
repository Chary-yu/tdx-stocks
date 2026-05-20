from __future__ import annotations

import argparse
import contextlib
import io
import unittest

from tdx_stocks.cli import build_parser, main as cli_main


class CliSurfaceTest(unittest.TestCase):
    def test_root_commands_are_locked_to_new_surface(self) -> None:
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if action.__class__.__name__ == "_SubParsersAction")
        visible = [choice.dest for choice in subparsers_action._choices_actions if choice.help != argparse.SUPPRESS]
        self.assertEqual(visible, ["init", "doctor", "sync", "run", "report", "query", "status", "ui", "help"])
        self.assertNotIn("strategy", visible)
        self.assertNotIn("portfolio", visible)

    def test_old_top_level_commands_fail(self) -> None:
        for argv in (
            ["stock", "600519.SH"],
            ["data", "sync"],
            ["factors", "list"],
            ["strategy", "list"],
            ["portfolio", "build"],
            ["daily", "run"],
            ["audit", "verify-adjustment"],
            ["query", "price", "600519.SH"],
            ["query", "status"],
            ["examples"],
            ["help-summary"],
            ["init-config"],
        ):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                self.assertNotEqual(code, 0)
                self.assertIn("invalid choice", stderr.getvalue())

    def test_new_flat_query_commands_work(self) -> None:
        for argv in (
            ["query", "factors"],
            ["query", "factor", "pct_rank_ret_20"],
            ["query", "strategies"],
            ["query", "strategy", "trend-strength"],
        ):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                self.assertEqual(code, 0, stderr.getvalue())

    def test_help_topics_are_static(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli_main(["help", "run"])
        self.assertEqual(code, 0)
        text = stdout.getvalue()
        self.assertIn("Built-in presets", text)
        self.assertIn("daily, signal, portfolio, rebalance, backtest, grid", text)
        self.assertIn("tdx-stocks run daily --explain", text)


if __name__ == "__main__":
    unittest.main()
