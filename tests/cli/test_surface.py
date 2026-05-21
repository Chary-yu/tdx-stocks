from __future__ import annotations

import argparse
import unittest

from tdx_stocks.cli import build_parser, main as cli_main
from tdx_stocks.exit_codes import UsageError


class CliSurfaceTest(unittest.TestCase):
    def test_top_level_surface_is_locked(self) -> None:
        parser = build_parser()
        subparsers_action = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        visible = [choice.dest for choice in subparsers_action._choices_actions if choice.help != argparse.SUPPRESS]
        self.assertEqual(visible, ["init", "doctor", "config", "sync", "run", "report", "query", "status", "ui", "help"])

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
                with self.assertRaises(UsageError):
                    build_parser().parse_args(argv)

    def test_old_factor_syntax_is_still_parsed_but_routed_to_legacy_handler(self) -> None:
        args = build_parser().parse_args(["query", "factor", "list"])
        self.assertEqual(args.command, "query")
        self.assertEqual(args.query_command, "factor")
        self.assertEqual(args.factor, "list")
        self.assertEqual(args.legacy_args, [])

    def test_new_query_commands_are_registered(self) -> None:
        expected = {
            ("query", "factors"): "factors",
            ("query", "factor", "pct_rank_ret_20"): "factor",
            ("query", "rank", "pct_rank_ret_20"): "rank",
            ("query", "strategies"): "strategies",
            ("query", "strategy", "trend-strength"): "strategy",
        }
        for argv, command in expected.items():
            with self.subTest(argv=argv):
                args = build_parser().parse_args(argv)
                self.assertEqual(args.command, "query")
                self.assertEqual(args.query_command, command)
