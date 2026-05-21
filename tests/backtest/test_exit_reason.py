from __future__ import annotations

from datetime import date

from tdx_stocks.backtest.engine import _build_trade_from_match
from tdx_stocks.backtest.models import BacktestParams


def test_trade_contains_exit_reason_fields() -> None:
    params = BacktestParams(from_date=date(2024, 1, 1), to_date=date(2024, 1, 31), hold_days=5)
    signal = {
        "signal_date": date(2024, 1, 4),
        "market": "sh",
        "symbol": "600519",
        "display_symbol": "600519.SH",
        "score": 80.0,
        "candidate_type": "trend",
        "direction": "LONG",
    }
    match = {
        "buy_date": date(2024, 1, 5),
        "sell_date": date(2024, 1, 10),
        "buy_price": 10.0,
        "sell_price": 11.0,
        "exit_reason": "ma_breakdown",
    }
    trade, _ = _build_trade_from_match(signal, match, params)
    assert trade.exit_reason is not None
