from __future__ import annotations

from typing import Any

from .base import GLOBAL_REQUIRED_FIELDS, StrategyParams


def hard_exclusion_reason(row: dict[str, Any], params: StrategyParams) -> str | None:
    if missing_any(row, GLOBAL_REQUIRED_FIELDS):
        return "missing_required_factor"
    amount_ma20 = float_or_none(row.get("amount_ma20"))
    if amount_ma20 is None or amount_ma20 < params.min_amount_ma20:
        return "insufficient_liquidity"
    ret_5 = float_or_none(row.get("ret_5"))
    if ret_5 is not None and ret_5 >= 0.15:
        return "overheated_ret_5"
    rsi_14 = float_or_none(row.get("rsi_14"))
    if rsi_14 is not None and rsi_14 >= 85:
        return "extreme_rsi"
    atr_pct_14 = float_or_none(row.get("atr_pct_14"))
    vol_20 = float_or_none(row.get("vol_20"))
    if (atr_pct_14 is not None and atr_pct_14 >= 0.10) or (vol_20 is not None and vol_20 >= 0.08):
        return "excessive_volatility"
    return None


def display_symbol(market: str, symbol: str) -> str:
    return f"{symbol}.{market.upper()}"


def float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def missing_any(row: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(row.get(field) is None for field in fields)
