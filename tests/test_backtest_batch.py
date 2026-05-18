from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.backtest.config_parser import expand_batch_configs, inject_nested_value, load_backtest_configs
from tdx_stocks.backtest.runner import run_single


class BacktestBatchConfigTest(unittest.TestCase):
    def test_inject_nested_value_creates_missing_levels(self) -> None:
        target: dict[str, object] = {}
        inject_nested_value(target, "strategy.factors.mom_20", 10)
        self.assertEqual(target, {"strategy": {"factors": {"mom_20": 10}}})

    def test_expand_batch_configs_builds_cartesian_product(self) -> None:
        config = {
            "engine": {
                "from_date": date(2024, 1, 1),
                "to_date": date(2024, 1, 5),
            },
            "batch_search": {
                "enabled": True,
                "engine.top": [10, 20],
                "strategy.factors.mom_20": [5, 10],
            },
        }

        expanded = expand_batch_configs(config, batch=True)

        self.assertEqual(len(expanded), 4)
        self.assertNotIn("batch_search", expanded[0])
        self.assertEqual(expanded[0]["engine"]["top"], 10)
        self.assertEqual(expanded[0]["strategy"]["factors"]["mom_20"], 5)
        self.assertEqual(expanded[-1]["engine"]["top"], 20)
        self.assertEqual(expanded[-1]["strategy"]["factors"]["mom_20"], 10)

    def test_load_backtest_configs_reads_toml_and_expands_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "backtest.toml"
            path.write_text(
                """
[engine]
from_date = 2024-01-01
to_date = 2024-01-05

[batch_search]
enabled = true
"engine.top" = [10, 20]
""".strip(),
                encoding="utf-8",
            )

            configs = load_backtest_configs(path, batch=True)

        self.assertEqual(len(configs), 2)
        self.assertEqual(configs[0]["engine"]["top"], 10)
        self.assertEqual(configs[1]["engine"]["top"], 20)

    def test_run_single_merges_strategy_overrides_into_backtest_params(self) -> None:
        config = {
            "paths": {
                "data_root": "/tmp/data-root",
            },
            "engine": {
                "from_date": date(2024, 1, 1),
                "to_date": date(2024, 1, 5),
                "top": 20,
                "hold_days": 5,
            },
            "strategy_name": "trend-strength",
            "strategy": {
                "limit": 10,
                "min_score": 70.0,
                "market": "sh",
            },
        }

        with patch("tdx_stocks.backtest.runner.run_backtest", return_value="sentinel") as mocked:
            result = run_single(config)

        self.assertEqual(result, "sentinel")
        args, kwargs = mocked.call_args
        self.assertEqual(args[1], "trend-strength")
        self.assertEqual(args[2].top, 10)
        self.assertEqual(args[2].min_score, 70.0)
        self.assertEqual(args[2].market, "sh")
        self.assertIn("strategy_runner_fn", kwargs)
        self.assertTrue(callable(kwargs["strategy_runner_fn"]))


if __name__ == "__main__":
    unittest.main()
