from __future__ import annotations

from .models import PortfolioParams, Position


def check_exit_signal(pos: Position, current_price: float, params: PortfolioParams) -> str | None:
    """返回离场原因标识，不离场返回 None"""
    if params.stop_loss_pct:
        if current_price <= pos.buy_price * (1 - params.stop_loss_pct):
            return "stop_loss"
    return None
