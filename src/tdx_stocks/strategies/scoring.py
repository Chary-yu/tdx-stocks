from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import ScoreWeights


def calculate_multi_factor_score(
    row: dict[str, Any],
    weights: ScoreWeights,
) -> dict[str, float]:
    rs_score = _float_or_none(row.get("rs_score"))
    vol_20_pct_rank = _float_or_none(row.get("vol_20_pct_rank"))
    amount_ma20_pct_rank = _float_or_none(row.get("amount_ma20_pct_rank"))
    atr_pct_14_pct_rank = _float_or_none(row.get("atr_pct_14_pct_rank"))
    pct_rank_ret_20 = _float_or_none(row.get("pct_rank_ret_20"))
    pct_rank_ret_60 = _float_or_none(row.get("pct_rank_ret_60"))
    ma_cross_20_60 = _float_or_none(row.get("ma_cross_20_60"))

    momentum = round((rs_score or 0.0) * weights.momentum, 6)
    volatility = round((1.0 - (vol_20_pct_rank or 0.0)) * weights.volatility, 6)
    liquidity = round((amount_ma20_pct_rank or 0.0) * weights.liquidity, 6)
    relative_strength = round(
        (((pct_rank_ret_20 or rs_score or 0.0) + (pct_rank_ret_60 or rs_score or 0.0)) / 2.0)
        * weights.relative_strength,
        6,
    )
    trend = round((((ma_cross_20_60 or 0.0) + (atr_pct_14_pct_rank or 0.0)) / 2.0) * weights.trend, 6)
    total = round(momentum + volatility + liquidity + relative_strength + trend, 6)
    return {
        "momentum": momentum,
        "volatility": volatility,
        "liquidity": liquidity,
        "relative_strength": relative_strength,
        "trend": trend,
        "total": total,
    }


def build_trend_score_breakdown(
    row: dict[str, Any],
    min_amount_ma20: float,
    risk_flags: list[str],
    strategy_name: str = "trend-strength",
) -> dict[str, float]:
    dispatcher: dict[str, Callable[[dict[str, Any], float, list[str]], dict[str, float]]] = {
        "low-vol-breakout": _score_low_vol_breakout,
        "ma-pullback": _score_ma_pullback,
        "relative-strength": _score_relative_strength,
        "volume-breakout": _score_volume_breakout,
        "mean-reversion": _score_mean_reversion,
        "smart-money": _score_smart_money,
        "trend-strength": _score_trend_strength,
    }
    scorer = dispatcher.get(strategy_name, _score_trend_strength)
    return scorer(row, min_amount_ma20, risk_flags)


def _score_trend_strength(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="trend-strength")
    return _select_score_components(components, ("trend", "liquidity", "position", "short_strength", "risk_penalty"))


def _score_low_vol_breakout(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="low-vol-breakout")
    return _select_score_components(components, ("trend", "breakout", "low_volatility", "liquidity", "risk_penalty"))


def _score_ma_pullback(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="ma-pullback")
    return _select_score_components(components, ("trend", "pullback", "liquidity", "risk_penalty"))


def _score_relative_strength(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="relative-strength")
    return _select_score_components(components, ("trend", "momentum", "position", "liquidity", "risk_penalty"))


def _score_volume_breakout(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="volume-breakout")
    return _select_score_components(components, ("trend", "breakout", "volume", "liquidity", "risk_penalty"))


def _score_mean_reversion(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="mean-reversion")
    return _select_score_components(components, ("trend", "oversold", "band_reclaim", "liquidity", "risk_penalty"))


def _score_smart_money(row: dict[str, Any], min_amount_ma20: float, risk_flags: list[str]) -> dict[str, float]:
    components = _build_trend_score_components(row, min_amount_ma20, risk_flags, strategy_name="smart-money")
    return _select_score_components(components, ("trend", "smart_volume", "stability", "liquidity", "risk_penalty"))


def _build_trend_score_components(
    row: dict[str, Any],
    min_amount_ma20: float,
    risk_flags: list[str],
    *,
    strategy_name: str,
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
    vol_ratio_5_60 = _float_or_none(row.get("vol_ratio_5_60"))
    price_vol_corr_20 = _float_or_none(row.get("price_vol_corr_20"))
    std_pctchg_20 = _float_or_none(row.get("std_pctchg_20"))
    bb_lower_20 = _float_or_none(row.get("bb_lower_20"))

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
    oversold = round(
        25.0 * _clamp((30.0 - (rsi_14 or 30.0)) / 10.0, 0.0, 1.0)
        + 15.0 * _clamp(max(0.0, -(ret_20 or 0.0) - 0.15) / 0.15, 0.0, 1.0),
        2,
    )
    low_volatility_bonus = round(10.0 * _clamp(1.0 - (std_pctchg_20 or 0.0) / 0.05, 0.0, 1.0), 2)
    band_reclaim = round(
        20.0 * _clamp(max(0.0, (bb_lower_20 or 0.0) - adj_close) / max(abs(bb_lower_20 or adj_close or 1.0), 1.0), 0.0, 1.0)
        + low_volatility_bonus,
        2,
    )
    smart_volume = round(
        20.0 * _clamp((vol_ratio_5_60 or 0.0) / 2.5, 0.0, 1.0)
        + 10.0 * _clamp((price_vol_corr_20 or 0.0) / 0.6, 0.0, 1.0),
        2,
    )
    stability = round(15.0 * _clamp((atr_pct_14 or 0.0) / 0.05, 0.0, 1.0), 2)

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
    if strategy_name == "low-vol-breakout" and (
        (atr_pct_14 is not None and atr_pct_14 >= 0.04) or (vol_20 is not None and vol_20 >= 0.035)
    ):
        risk_penalty -= 6.0
    if strategy_name == "ma-pullback" and dd_20 is not None and dd_20 < -0.12:
        risk_penalty -= 6.0
    if strategy_name == "relative-strength" and (ret_60 < 0.10 or ret_5 >= 0.10):
        risk_penalty -= 4.0
    if strategy_name == "volume-breakout" and (vol_ratio_20 is not None and vol_ratio_20 < 0.25):
        risk_penalty -= 6.0
    if strategy_name == "mean-reversion" and (rsi_14 is not None and rsi_14 < 30):
        risk_penalty += 2.0
    if strategy_name == "smart-money" and (price_vol_corr_20 is not None and price_vol_corr_20 > 0.6):
        risk_penalty += 2.0
    risk_penalty = round(max(-30.0, risk_penalty), 2)

    return {
        "trend": trend,
        "liquidity": liquidity,
        "position": position,
        "short_strength": short_strength,
        "breakout": breakout,
        "low_volatility": low_volatility,
        "pullback": pullback,
        "momentum": momentum,
        "volume": volume,
        "oversold": oversold,
        "band_reclaim": band_reclaim,
        "smart_volume": smart_volume,
        "stability": stability,
        "risk_penalty": risk_penalty,
    }


def _select_score_components(components: dict[str, float], names: tuple[str, ...]) -> dict[str, float]:
    return {name: components[name] for name in names}


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
