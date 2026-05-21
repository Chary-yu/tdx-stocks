from __future__ import annotations

from .prices import AdjDailyPrice
from .models import PortfolioParams, Position


def check_exit_signal(pos: Position, bar: AdjDailyPrice, params: PortfolioParams) -> str | None:
    """返回离场原因标识，不离场返回 None"""
    current_price = float(bar.open_price)
    if pos.highest_price <= 0:
        pos.highest_price = max(pos.buy_price, float(bar.high_price))
    else:
        pos.highest_price = max(pos.highest_price, float(bar.high_price))

    if params.stop_loss_atr:
        atr = max(pos.buy_price * max(params.atr_proxy_pct, 0.001), 0.01)
        if current_price <= pos.highest_price - params.stop_loss_atr * atr:
            return "atr_stop_loss"
    if params.take_profit_atr:
        atr = max(pos.buy_price * max(params.atr_proxy_pct, 0.001), 0.01)
        if current_price >= pos.buy_price + params.take_profit_atr * atr:
            return "atr_take_profit"
    if params.stop_loss_pct:
        if current_price <= pos.buy_price * (1 - params.stop_loss_pct):
            return "stop_loss"
    if params.take_profit_pct:
        if current_price >= pos.buy_price * (1 + params.take_profit_pct):
            return "take_profit"
    if params.stop_loss_ma20:
        ma20 = (bar.close_price + bar.high_price + bar.low_price + bar.open_price) / 4.0
        if bar.close_price < ma20:
            return "ma_breakdown"
    if params.momentum_turn_negative and bar.close_price < bar.open_price:
        return "momentum_negative"
    return None
