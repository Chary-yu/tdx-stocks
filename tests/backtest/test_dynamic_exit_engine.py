from __future__ import annotations

from datetime import date

from tdx_stocks.backtest.exits import ExitEngine
from tdx_stocks.backtest.models import PortfolioParams, Position
from tdx_stocks.backtest.prices import AdjDailyPrice


def test_exit_engine_respects_min_days_except_hard_stop() -> None:
    pos = Position(symbol="600000", shares=100, buy_price=10.0, buy_date=date(2024, 1, 1), highest_price=10.0)
    params = PortfolioParams(min_hold_days=3, hard_stop_loss_pct=0.10, stop_loss_pct=0.05)
    bar = AdjDailyPrice(open_price=8.8, close_price=8.8, high_price=9.0, low_price=8.7)
    reason, trigger = ExitEngine.check(pos, bar, params, hold_days=1)
    assert reason == "hard_stop_loss"
    assert trigger == "hard_stop"


def test_exit_engine_technical_after_min_days() -> None:
    pos = Position(symbol="600000", shares=100, buy_price=10.0, buy_date=date(2024, 1, 1), highest_price=10.5)
    params = PortfolioParams(min_hold_days=2, stop_loss_atr=2.0, atr_proxy_pct=0.02)
    bar = AdjDailyPrice(open_price=9.9, close_price=9.9, high_price=10.0, low_price=9.8)
    reason, trigger = ExitEngine.check(pos, bar, params, hold_days=2)
    assert reason in {"atr_stop_loss", None}
    if reason is not None:
        assert trigger == "technical"

