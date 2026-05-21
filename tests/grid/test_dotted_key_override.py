from __future__ import annotations

from tdx_stocks.config.override import set_by_dotted_key


def test_set_by_dotted_key() -> None:
    config: dict[str, object] = {}
    set_by_dotted_key(config, "strategy.min_score", 70)
    set_by_dotted_key(config, "exit_rules.technical.stop_loss_atr", 2.0)
    assert config["strategy"]["min_score"] == 70
    assert config["exit_rules"]["technical"]["stop_loss_atr"] == 2.0
