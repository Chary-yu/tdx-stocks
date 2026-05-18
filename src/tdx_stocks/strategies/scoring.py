from __future__ import annotations

from typing import Any


def build_trend_score_breakdown(
    row: dict[str, Any],
    min_amount_ma20: float,
    risk_flags: list[str],
    strategy_name: str = "trend-strength",
) -> dict[str, float]:
    adj_close = _float_or_none(row.get("adj_close")) or 0.0
    ma20 = _float_or_none(row.get("ma20")) or 0.0
    ma60 = _float_or_none(row.get("ma60")) or 0.0
    ret_60 = _float_or_none(row.get("ret_60")) or 0.0
    ret_5 = _float_or_none(row.get("ret_5")) or 0.0
    ret_20 = _float_or_none(row.get("ret_20")) or 0.0
    amount_ma20 = _float_or_none(row.get("amount_ma20")) or 0.0
    pos_20 = _float_or_none(row.get("pos_20")) or 0.0
    pos_60 = _float_or_none(row.get("pos_60")) or 0.0
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    dd_20 = _float_or_none(row.get("dd_20"))
    vol_ratio_20 = _float_or_none(row.get("vol_ratio_20"))

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
    breakout = round(
        20.0 * _clamp((pos_20 + pos_60) / 1.8, 0.0, 1.0)
        + 10.0 * _clamp((vol_ratio_20 or 0.0) / 0.5, 0.0, 1.0),
        2,
    )
    low_volatility = round(
        20.0 * _clamp(1.0 - max(vol_20 or 0.0, atr_pct_14 or 0.0) / 0.08, 0.0, 1.0),
        2,
    )
    pullback = round(
        20.0
        * _clamp(1.0 - abs((adj_close / ma20) - 1.0) / 0.05 if ma20 else 0.0, 0.0, 1.0)
        + 10.0 * _clamp(max(0.0, -(dd_20 or 0.0)) / 0.08, 0.0, 1.0),
        2,
    )
    momentum = round(
        18.0 * _clamp(ret_20 / 0.18, 0.0, 1.0)
        + 12.0 * _clamp(ret_60 / 0.25, 0.0, 1.0)
        + 8.0 * _clamp(max(ret_5, 0.0) / 0.08, 0.0, 1.0),
        2,
    )
    volume = round(
        20.0 * _clamp((vol_ratio_20 or 0.0) / 0.5, 0.0, 1.0)
        + 10.0 * _clamp((amount_ma20 / max(min_amount_ma20, 1.0) - 1.0) / 2.0, 0.0, 1.0),
        2,
    )

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
    if strategy_name == "low-vol-breakout" and ((atr_pct_14 is not None and atr_pct_14 >= 0.04) or (vol_20 is not None and vol_20 >= 0.035)):
        risk_penalty -= 6.0
    if strategy_name == "ma-pullback" and (dd_20 is not None and dd_20 < -0.12):
        risk_penalty -= 6.0
    if strategy_name == "relative-strength" and (ret_60 < 0.10 or ret_5 >= 0.10):
        risk_penalty -= 4.0
    if strategy_name == "volume-breakout" and (vol_ratio_20 is not None and vol_ratio_20 < 0.25):
        risk_penalty -= 6.0
    risk_penalty = round(max(-30.0, risk_penalty), 2)

    if strategy_name == "low-vol-breakout":
        return {
            "trend": trend,
            "breakout": breakout,
            "low_volatility": low_volatility,
            "liquidity": liquidity,
            "risk_penalty": risk_penalty,
        }
    if strategy_name == "ma-pullback":
        return {
            "trend": trend,
            "pullback": pullback,
            "liquidity": liquidity,
            "risk_penalty": risk_penalty,
        }
    if strategy_name == "relative-strength":
        return {
            "trend": trend,
            "momentum": momentum,
            "position": position,
            "liquidity": liquidity,
            "risk_penalty": risk_penalty,
        }
    if strategy_name == "volume-breakout":
        return {
            "trend": trend,
            "breakout": breakout,
            "volume": volume,
            "liquidity": liquidity,
            "risk_penalty": risk_penalty,
        }
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
