from __future__ import annotations

from .models import PortfolioParams


def calc_target_shares(available_cash: float, price: float, params: PortfolioParams) -> int:
    """计算目标买入股数（等权模型）"""
    if available_cash <= 0 or price <= 0 or params.max_positions <= 0:
        return 0
    target_cash = params.initial_cash / params.max_positions
    investable_cash = min(target_cash, available_cash)
    return int(investable_cash / price // 100) * 100
