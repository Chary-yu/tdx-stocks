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
    """返回离场原因标识，不离场返回 None。"""
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

    atr = max(float(pos.buy_price) * max(params.atr_proxy_pct, 0.001), 0.01)
    stop_mult = _adaptive_stop_multiplier(params)
    if params.chandelier_multiplier:
        chandelier_stop = highest_price - params.chandelier_multiplier * atr
        if current_price <= chandelier_stop:
            return "chandelier_stop"
    if stop_mult:
        if current_price <= highest_price - stop_mult * atr:
            return "atr_stop_loss"
    if params.trailing_pullback_pct:
        trailing_stop = highest_price * (1.0 - params.trailing_pullback_pct)
        if current_price <= trailing_stop:
            return "trailing_take_profit"
    if params.take_profit_atr:
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


def _adaptive_stop_multiplier(params: PortfolioParams) -> float | None:
    base = params.stop_loss_atr
    if base is None:
        return None
    vol = params.atr_proxy_pct * (252 ** 0.5)
    if params.volatility_high_threshold is not None and params.volatility_high_multiplier is not None:
        if vol >= params.volatility_high_threshold:
            return params.volatility_high_multiplier
    if params.volatility_low_threshold is not None and params.volatility_low_multiplier is not None:
        if vol <= params.volatility_low_threshold:
            return params.volatility_low_multiplier
    return base
