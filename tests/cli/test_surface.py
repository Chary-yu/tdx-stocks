from __future__ import annotations

import argparse
import contextlib
import io
import unittest

from tdx_stocks.cli import build_parser, main as cli_main


class CliSurfaceTest(unittest.TestCase):
    def test_top_level_surface_is_locked(self) -> None:
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        visible = [choice.dest for choice in subparsers_action._choices_actions if choice.help != argparse.SUPPRESS]
        self.assertEqual(visible, ["init", "doctor", "sync", "run", "report", "query", "status", "ui", "help"])

    def test_old_top_level_commands_fail(self) -> None:
        for argv in (
            ["data", "sync"],
            ["strategy", "list"],
            ["portfolio", "build"],
            ["daily", "run"],
            ["help-summary"],
            ["init-config"],
        ):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                self.assertNotEqual(code, 0)
                self.assertIn("invalid choice", stderr.getvalue())

    def test_old_factor_syntax_is_rejected_with_clear_guidance(self) -> None:
        for argv in (
            ["query", "factor", "list"],
            ["query", "factor", "describe", "rsi_14"],
            ["query", "factor", "rank", "rsi_14"],
            ["query", "factor", "schema"],
        ):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                self.assertEqual(code, 6)
                self.assertIn("legacy query factor subcommands are no longer supported", stderr.getvalue())

    def test_new_query_commands_work(self) -> None:
        for argv in (
            ["query", "factors"],
            ["query", "factor", "pct_rank_ret_20"],
            ["query", "rank", "pct_rank_ret_20"],
            ["query", "strategies"],
            ["query", "strategy", "trend-strength"],
        ):
            with self.subTest(argv=argv):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    code = cli_main(argv)
                self.assertEqual(code, 0, stderr.getvalue())
