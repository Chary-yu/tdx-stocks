from __future__ import annotations

import unittest

from tdx_stocks.runner.schema import validate_run_config


class RunSchemaCoreFieldsTest(unittest.TestCase):
    def test_core_sections_are_recognized_without_ignored_warnings(self) -> None:
        config = {
            "task": {"type": "backtest", "name": "bt"},
            "strategy": {"name": "trend-strength"},
            "backtest": {"from_date": "2024-01-01", "to_date": "2024-12-31"},
            "exit_rules": {
                "enabled": True,
                "technical": {"stop_loss_atr": 2.0},
                "max_hold": {"max_days": 20},
                "signal_exit": {"exit_when_score_below": 40},
            },
            "consensus": {"advanced": {"method": "weighted_by_performance"}},
            "signal": {"decay": {"enabled": True}},
            "diversity_check": {"enabled": True},
            "portfolio": {"weighting_hybrid": {"signal": 0.5, "liquidity": 0.5}},
            "rebalance": {"cost_model": {"piecewise": {"low": {"impact_bps": 2}}}},
        }
        _, _, warnings = validate_run_config(config)
        joined = "\n".join(warnings)
        self.assertNotIn("ignored unsupported section(s)", joined)
        self.assertNotIn("ignored unsupported key(s) in [exit_rules]", joined)
        self.assertNotIn("ignored unknown top-level section(s): signal", joined)

