from __future__ import annotations

from tdx_stocks.risk.market_regime import evaluate_market_regime


def test_macro_filter_missing_required_indicator_pause_open() -> None:
    result = evaluate_market_regime(
        {
            "enabled": True,
            "required": ["market_breadth"],
            "indicators": {},
            "rules": {"bear_trade_allowed": False},
        }
    )
    assert result.status == "not_available"
    assert result.action == "pause_open"


def test_macro_filter_bear_and_not_allowed_pause_open() -> None:
    result = evaluate_market_regime(
        {
            "enabled": True,
            "indicators": {"market_breadth": "bear"},
            "rules": {"bear_trade_allowed": False},
            "impact": {"position_limit_bear": 0.4},
        }
    )
    assert result.status == "bear"
    assert result.action == "pause_open"
