from __future__ import annotations

from tdx_stocks.portfolio.models import Holding
from tdx_stocks.portfolio.rebalance import build_rebalance_plan


def test_pause_open_turns_buy_to_hold_cash() -> None:
    current = [Holding(market="sh", symbol="600000", weight=0.0)]
    target = [Holding(market="sh", symbol="600000", weight=0.2)]
    plan = build_rebalance_plan(
        current,
        target,
        as_of="2024-12-31",
        target_risk_filter={"risk_filter_applied": True, "market_regime": {"status": "bear", "action": "pause_open"}},
    )
    assert any(row["action"] == "HOLD_CASH" for row in plan.weight_changes)
