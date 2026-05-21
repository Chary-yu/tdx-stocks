from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tdx_stocks.config.loader import load_config_bundle


class ConfigBundleLoaderTest(unittest.TestCase):
    def test_aux_alias_and_section_extraction_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            exp = root / "experiments"
            exp.mkdir(parents=True, exist_ok=True)
            (exp / "daily.toml").write_text(
                """
[task]
type = "daily"
name = "daily"
""".strip(),
                encoding="utf-8",
            )
            (exp / "macro_filter.toml").write_text(
                """
[macro_filter]
enabled = true
[macro_filter.rules]
bull_trade_required = true
[macro_filter.impact]
position_limit_bear = 0.4
""".strip(),
                encoding="utf-8",
            )
            (exp / "screening_pre_filter.toml").write_text(
                """
[pre_filter]
[pre_filter.basic]
min_amount_ma20 = 100000000
""".strip(),
                encoding="utf-8",
            )
            (exp / "stop_loss_dynamic.toml").write_text(
                """
[stop_loss]
[stop_loss.volatility_adaptive]
enabled = true
""".strip(),
                encoding="utf-8",
            )
            bundle = load_config_bundle(exp / "daily.toml")

        self.assertTrue(bundle.merged_config["macro_filter"]["enabled"])
        self.assertIn("rules", bundle.merged_config["macro_filter"])
        self.assertIn("impact", bundle.merged_config["macro_filter"])
        self.assertIn("basic", bundle.merged_config["pre_filter"])
        self.assertIn("volatility_adaptive", bundle.merged_config["stop_loss"])
        self.assertNotIn("macro_filter", bundle.merged_config["macro_filter"])

