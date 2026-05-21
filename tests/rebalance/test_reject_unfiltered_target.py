from __future__ import annotations

from tdx_stocks.portfolio.models import Holding
from tdx_stocks.portfolio.rebalance import build_rebalance_plan


def test_critical_reject_trade() -> None:
    current = [Holding(market="sh", symbol="600000", weight=0.0)]
    target = [Holding(market="sh", symbol="600000", weight=0.5)]
    plan = build_rebalance_plan(
        current,
        target,
        as_of="2024-12-31",
        cost_model={"piecewise": {"critical": {"reject": True, "delta_threshold": 0.2}}},
        target_risk_filter={"risk_filter_applied": True, "market_regime": {"status": "bull", "action": "allow_open"}},
    )
    assert any(row["action"] == "REJECT_TRADE" for row in plan.weight_changes)
