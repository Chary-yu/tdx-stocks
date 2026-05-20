from __future__ import annotations

import argparse
import unittest

from tdx_stocks.cli import build_parser
from tdx_stocks.exit_codes import UsageError


class ReleaseCliContractTest(unittest.TestCase):
    def test_new_surface_includes_report_opening_flags(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["report", "--no-open"])
        self.assertEqual(args.command, "report")
        self.assertTrue(args.no_open)

        args = parser.parse_args(["report", "strategy", "trend-strength", "--no-open"])
        self.assertEqual(args.command, "report")
        self.assertEqual(args.report_command, "strategy")
        self.assertTrue(args.no_open)

        args = parser.parse_args(["run", "daily", "--no-open"])
        self.assertEqual(args.command, "run")
        self.assertTrue(args.no_open)

    def test_old_top_level_commands_are_rejected(self) -> None:
        parser = build_parser()
        for argv in (["portfolio", "build"], ["strategy", "list"], ["factors", "list"], ["daily", "run"]):
            with self.subTest(argv=argv):
                with self.assertRaises(UsageError):
                    parser.parse_args(argv)
