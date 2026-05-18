from __future__ import annotations

from typing import Any


def build_trend_score_breakdown(
    row: dict[str, Any],
    min_amount_ma20: float,
    risk_flags: list[str],
) -> dict[str, float]:
    adj_close = _float_or_none(row.get("adj_close")) or 0.0
    ma20 = _float_or_none(row.get("ma20")) or 0.0
    ma60 = _float_or_none(row.get("ma60")) or 0.0
    ret_5 = _float_or_none(row.get("ret_5")) or 0.0
    ret_20 = _float_or_none(row.get("ret_20")) or 0.0
    amount_ma20 = _float_or_none(row.get("amount_ma20")) or 0.0
    pos_20 = _float_or_none(row.get("pos_20")) or 0.0
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    dd_20 = _float_or_none(row.get("dd_20"))

    trend = 0.0
    if adj_close > ma20:
        trend += 15.0
    if ma20 > ma60:
        trend += 10.0
    trend += 10.0 * _clamp(ret_20 / 0.20, 0.0, 1.0)
    trend = round(min(35.0, trend), 2)

    liquidity = round(20.0 * _clamp(amount_ma20 / max(min_amount_ma20 * 5.0, 1.0), 0.0, 1.0), 2)
    position = round(20.0 * _clamp(pos_20, 0.0, 1.0), 2)
    short_strength = round(15.0 * _clamp((ret_5 + 0.05) / 0.20, 0.0, 1.0), 2)

    risk_penalty = 0.0
    if "risk_factor_missing" in risk_flags:
        risk_penalty -= 1.0
    if ret_5 >= 0.08:
        risk_penalty -= 4.0
    if rsi_14 is not None and rsi_14 >= 75:
        risk_penalty -= 4.0
    if (atr_pct_14 is not None and atr_pct_14 >= 0.05) or (vol_20 is not None and vol_20 >= 0.04):
        risk_penalty -= 4.0
    if dd_20 is not None and dd_20 >= -0.03:
        risk_penalty -= 2.0
    risk_penalty = round(max(-30.0, risk_penalty), 2)

    return {
        "trend": trend,
        "liquidity": liquidity,
        "position": position,
        "short_strength": short_strength,
        "risk_penalty": risk_penalty,
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
