from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import build_parser
from tdx_stocks.commands.strategy import cmd_strategy_describe, cmd_strategy_explain, cmd_strategy_groups
from tdx_stocks.strategies.base import StrategyReport
from tdx_stocks.strategies.registry import list_strategies


class StrategyMetadataTest(unittest.TestCase):
    def test_builtin_strategies_expose_required_metadata(self) -> None:
        strategies = list_strategies()
        self.assertGreater(len(strategies), 0)
        for definition in strategies:
            self.assertTrue(definition.display_name is not None)
            self.assertTrue(definition.group)
            self.assertTrue(definition.style)
            self.assertTrue(definition.introduced_in)

    def test_groups_command_returns_group_payload(self) -> None:
        args = build_parser().parse_args(["strategy", "groups", "--json"])
        with patch("tdx_stocks.commands.strategy.print_json") as mocked_print_json:
            cmd_strategy_groups(args)
        payload = mocked_print_json.call_args.args[0]
        self.assertTrue(any(row["group"] == "trend" for row in payload))

    def test_describe_command_returns_strategy_schema(self) -> None:
        args = build_parser().parse_args(["strategy", "describe", "trend-strength", "--json"])
        with patch("tdx_stocks.commands.strategy.print_json") as mocked_print_json:
            cmd_strategy_describe(args)
        payload = mocked_print_json.call_args.args[0]
        self.assertEqual(payload["name"], "trend-strength")
        self.assertIn("group", payload)
        self.assertIn("candidate_types", payload)
        self.assertIn("supported_research_capabilities", payload)

    def test_explain_command_returns_selected_payload(self) -> None:
        args = build_parser().parse_args(["strategy", "explain", "trend-strength", "000001", "--json"])
        fake_report = StrategyReport(
            summary={"min_score": 60.0},
            picks=[],
            excluded=[],
            explain={
                "status": "picked",
                "message": "picked into the observation pool",
                "pick": {
                    "score": 88.5,
                    "score_breakdown": {"trend": 20.0},
                    "factor_values": {"ma20": 10.0, "ma60": 9.0},
                    "risk_flags": ["mild_volatility"],
                    "candidate_type": "strong_trend",
                    "tags": ["trend_strong"],
                    "watch_plan": "watch",
                },
            },
        )
        with patch("tdx_stocks.commands.strategy.load_config", return_value=SimpleNamespace()):
            with patch("tdx_stocks.commands.strategy.get_strategy") as mocked_get_strategy:
                mocked_get_strategy.return_value = SimpleNamespace(
                    runner=lambda config, params: fake_report,
                    params_builder=None,
                )
                with patch("tdx_stocks.commands.strategy.print_json") as mocked_print_json:
                    cmd_strategy_explain(args)
        payload = mocked_print_json.call_args.args[0]
        self.assertTrue(payload["selected"])
        self.assertEqual(payload["total_score"], 88.5)
        self.assertIn("rule_checks", payload)
        self.assertIn("key_factors", payload)


if __name__ == "__main__":
    unittest.main()
