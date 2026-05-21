from __future__ import annotations

from .prices import AdjDailyPrice
from .models import PortfolioParams, Position


def _bar_price(bar: AdjDailyPrice | float | int, attr: str, fallback: float | None = None) -> float:
    if hasattr(bar, attr):
        return float(getattr(bar, attr))
    if fallback is not None:
        return float(fallback)
    return float(bar)


def check_exit_signal(pos: Position, bar: AdjDailyPrice | float | int, params: PortfolioParams) -> str | None:
    """返回离场原因标识，不离场返回 None。

    兼容历史单元测试中直接传入价格 float 的用法；正式回测路径仍传入
    AdjDailyPrice。
    """
    current_price = _bar_price(bar, "open_price")
    high_price = _bar_price(bar, "high_price", current_price)
    close_price = _bar_price(bar, "close_price", current_price)
    low_price = _bar_price(bar, "low_price", current_price)

    highest_price = float(getattr(pos, "highest_price", 0.0) or 0.0)
    if highest_price <= 0:
        highest_price = max(float(pos.buy_price), high_price)
    else:
        highest_price = max(highest_price, high_price)
    try:
        pos.highest_price = highest_price
    except Exception:
        pass

    if params.stop_loss_atr:
        atr = max(float(pos.buy_price) * max(params.atr_proxy_pct, 0.001), 0.01)
        if current_price <= highest_price - params.stop_loss_atr * atr:
            return "atr_stop_loss"
    if params.take_profit_atr:
        atr = max(float(pos.buy_price) * max(params.atr_proxy_pct, 0.001), 0.01)
        if current_price >= float(pos.buy_price) + params.take_profit_atr * atr:
            return "atr_take_profit"
    if params.stop_loss_pct:
        if current_price <= float(pos.buy_price) * (1 - params.stop_loss_pct):
            return "stop_loss"
    if params.take_profit_pct:
        if current_price >= float(pos.buy_price) * (1 + params.take_profit_pct):
            return "take_profit"
    if params.stop_loss_ma20:
        ma20 = (close_price + high_price + low_price + current_price) / 4.0
        if close_price < ma20:
            return "ma_breakdown"
    if params.momentum_turn_negative and close_price < current_price:
        return "momentum_negative"
    return None


def check_hard_stop(pos: Position, bar: AdjDailyPrice | float | int, params: PortfolioParams) -> str | None:
    if params.hard_stop_loss_pct:
        if _bar_price(bar, "open_price") <= float(pos.buy_price) * (1 - params.hard_stop_loss_pct):
            return "hard_stop_loss"
    return None
