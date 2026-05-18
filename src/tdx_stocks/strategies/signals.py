from __future__ import annotations

from typing import Any

from .base import StrategyParams


def classify_trend_candidate(
    row: dict[str, Any],
    params: StrategyParams,
    strategy_name: str = "trend-strength",
) -> tuple[str | None, list[str], list[str]]:
    if strategy_name == "low-vol-breakout":
        return _classify_low_vol_breakout(row, params)
    if strategy_name == "ma-pullback":
        return _classify_ma_pullback(row, params)
    if strategy_name == "relative-strength":
        return _classify_relative_strength(row, params)
    if strategy_name == "volume-breakout":
        return _classify_volume_breakout(row, params)
    return _classify_trend_strength(row, params)


def _classify_trend_strength(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    ret_5 = _float_or_none(row.get("ret_5"))
    ret_20 = _float_or_none(row.get("ret_20"))
    pos_20 = _float_or_none(row.get("pos_20"))
    dd_20 = _float_or_none(row.get("dd_20"))
    vol_ratio_20 = _float_or_none(row.get("vol_ratio_20"))

    strong_trend = (
        adj_close is not None
        and ma20 is not None
        and ma60 is not None
        and ret_20 is not None
        and adj_close > ma20
        and ma20 > ma60
        and ret_20 > 0
    )
    breakout_watch = (
        ret_20 is not None
        and pos_20 is not None
        and dd_20 is not None
        and vol_ratio_20 is not None
        and ret_20 > 0
        and pos_20 >= 0.85
        and dd_20 >= -0.03
        and vol_ratio_20 > 0
    )
    pullback_watch = (
        ma20 is not None
        and ma60 is not None
        and adj_close is not None
        and ret_5 is not None
        and ret_20 is not None
        and dd_20 is not None
        and ma20 > ma60
        and adj_close >= ma20
        and ret_5 <= 0
        and ret_20 > 0
        and dd_20 >= -0.12
    )

    if breakout_watch:
        candidate_type = "breakout_watch"
    elif strong_trend:
        candidate_type = "strong_trend"
    elif pullback_watch:
        candidate_type = "pullback_watch"

    if candidate_type == "breakout_watch":
        tags.extend(["breakout_watch", "trend_strong", "near_20d_high"])
        reasons.extend(["接近20日高点", "量能放大", "趋势延续"])
    elif candidate_type == "strong_trend":
        tags.extend(["trend_strong", "ma_bullish"])
        reasons.extend(["均线多头", "趋势向上", "成交额活跃"])
    elif candidate_type == "pullback_watch":
        tags.extend(["pullback_watch", "ma_bullish"])
        reasons.extend(["中期趋势向上", "短线回踩", "等待企稳"])

    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20 * 2:
        tags.append("active_amount")
    if vol_ratio_20 is not None and vol_ratio_20 > 0.1:
        tags.append("volume_expansion")

    return candidate_type, _dedupe_preserve_order(tags), reasons


def _classify_low_vol_breakout(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    pos_20 = _float_or_none(row.get("pos_20"))
    pos_60 = _float_or_none(row.get("pos_60"))
    dd_20 = _float_or_none(row.get("dd_20"))
    vol_ratio_20 = _float_or_none(row.get("vol_ratio_20"))
    vol_20 = _float_or_none(row.get("vol_20"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    ret_5 = _float_or_none(row.get("ret_5"))
    ret_20 = _float_or_none(row.get("ret_20"))
    rsi_14 = _float_or_none(row.get("rsi_14"))

    low_vol_breakout = (
        adj_close is not None
        and ma20 is not None
        and ma60 is not None
        and pos_20 is not None
        and dd_20 is not None
        and vol_ratio_20 is not None
        and vol_20 is not None
        and atr_pct_14 is not None
        and ret_20 is not None
        and adj_close > ma20
        and ma20 > ma60
        and pos_20 >= 0.85
        and (pos_60 is None or pos_60 >= 0.70)
        and dd_20 >= -0.03
        and vol_ratio_20 >= 0.12
        and vol_20 <= 0.045
        and atr_pct_14 <= 0.05
        and ret_20 > 0
        and (ret_5 is None or ret_5 <= 0.08)
        and (rsi_14 is None or rsi_14 < 78)
    )
    if low_vol_breakout:
        candidate_type = "breakout_watch"
        tags.extend(["breakout_watch", "low_volatility", "trend_strong", "near_20d_high"])
        reasons.extend(["低波收敛", "接近突破位", "趋势未破坏"])
    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20 * 2:
        tags.append("active_amount")
    if vol_ratio_20 is not None and vol_ratio_20 >= 0.20:
        tags.append("volume_expansion")
    return candidate_type, _dedupe_preserve_order(tags), reasons


def _classify_ma_pullback(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    ret_5 = _float_or_none(row.get("ret_5"))
    ret_20 = _float_or_none(row.get("ret_20"))
    dd_20 = _float_or_none(row.get("dd_20"))
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))

    pullback_watch = (
        adj_close is not None
        and ma20 is not None
        and ma60 is not None
        and ret_20 is not None
        and dd_20 is not None
        and adj_close >= ma20 * 0.97
        and adj_close <= ma20 * 1.03
        and ma20 > ma60
        and ret_20 > 0.03
        and (ret_5 is None or ret_5 <= 0.03)
        and dd_20 >= -0.10
        and (rsi_14 is None or rsi_14 < 72)
        and (atr_pct_14 is None or atr_pct_14 <= 0.06)
    )
    if pullback_watch:
        candidate_type = "pullback_watch"
        tags.extend(["pullback_watch", "ma_bullish", "trend_strong"])
        reasons.extend(["回踩均线", "中期趋势向上", "等待企稳"])
    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20 * 2:
        tags.append("active_amount")
    return candidate_type, _dedupe_preserve_order(tags), reasons


def _classify_relative_strength(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    ret_20 = _float_or_none(row.get("ret_20"))
    ret_60 = _float_or_none(row.get("ret_60"))
    pos_20 = _float_or_none(row.get("pos_20"))
    ret_5 = _float_or_none(row.get("ret_5"))

    strong_trend = (
        adj_close is not None
        and ma20 is not None
        and ma60 is not None
        and ret_20 is not None
        and ret_60 is not None
        and adj_close > ma20
        and ma20 > ma60
        and ret_20 >= 0.08
        and ret_60 >= 0.10
        and (pos_20 is None or pos_20 >= 0.65)
        and (ret_5 is None or ret_5 <= 0.10)
    )
    if strong_trend:
        candidate_type = "strong_trend"
        tags.extend(["trend_strong", "ma_bullish", "relative_strength"])
        reasons.extend(["20日动量强", "60日趋势不弱", "均线结构健康"])
    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20 * 1.5:
        tags.append("active_amount")
    return candidate_type, _dedupe_preserve_order(tags), reasons


def _classify_volume_breakout(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    pos_20 = _float_or_none(row.get("pos_20"))
    dd_20 = _float_or_none(row.get("dd_20"))
    vol_ratio_20 = _float_or_none(row.get("vol_ratio_20"))
    ret_5 = _float_or_none(row.get("ret_5"))
    rsi_14 = _float_or_none(row.get("rsi_14"))
    vol_20 = _float_or_none(row.get("vol_20"))

    volume_breakout = (
        adj_close is not None
        and ma20 is not None
        and pos_20 is not None
        and dd_20 is not None
        and vol_ratio_20 is not None
        and adj_close > ma20
        and pos_20 >= 0.85
        and dd_20 >= -0.03
        and vol_ratio_20 >= 0.25
        and (ret_5 is None or ret_5 > 0)
        and (rsi_14 is None or rsi_14 < 80)
        and (vol_20 is None or vol_20 <= 0.06)
    )
    if volume_breakout:
        candidate_type = "breakout_watch"
        tags.extend(["breakout_watch", "volume_breakout", "volume_expansion", "trend_strong", "near_20d_high"])
        reasons.extend(["放量突破", "接近20日高点", "量价配合"])
    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20:
        tags.append("active_amount")
    return candidate_type, _dedupe_preserve_order(tags), reasons


def build_trend_risk_flags(row: dict[str, Any], strategy_name: str = "trend-strength") -> list[str]:
    flags: list[str] = []
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    ret_5 = _float_or_none(row.get("ret_5"))
    dd_20 = _float_or_none(row.get("dd_20"))

    if rsi_14 is None or atr_pct_14 is None or vol_20 is None:
        flags.append("risk_factor_missing")
    if ret_5 is not None and ret_5 >= 0.08:
        flags.append("ret_5_strong")
    if rsi_14 is not None and rsi_14 >= 75:
        flags.append("rsi_high")
    if (atr_pct_14 is not None and atr_pct_14 >= 0.05) or (vol_20 is not None and vol_20 >= 0.04):
        flags.append("mild_volatility")
    if strategy_name == "low-vol-breakout" and (
        (atr_pct_14 is not None and atr_pct_14 >= 0.04) or (vol_20 is not None and vol_20 >= 0.035)
    ):
        flags.append("high_volatility")
    if strategy_name == "volume-breakout" and _float_or_none(row.get("vol_ratio_20")) is not None:
        if _float_or_none(row.get("vol_ratio_20")) >= 0.75 and ret_5 is not None and ret_5 <= 0:
            flags.append("volume_climax")
    if dd_20 is not None and dd_20 >= -0.03:
        flags.append("near_20d_high")
    return _dedupe_preserve_order(flags)


def build_trend_watch_plan(candidate_type: str | None, risk_flags: list[str], strategy_name: str = "trend-strength") -> str:
    if strategy_name == "low-vol-breakout":
        plan = "低波收敛后确认放量突破再观察，回到突破位下方则放弃"
    elif strategy_name == "ma-pullback":
        plan = "回踩 ma20 企稳再观察，跌破 ma60 则放弃"
    elif strategy_name == "relative-strength":
        plan = "相对强势优先看趋势延续，跌破 ma20 或动量走弱则放弃"
    elif strategy_name == "volume-breakout":
        plan = "放量突破后观察次日能否站稳，回落到前高下方不追"
    elif candidate_type == "breakout_watch":
        plan = "放量突破前高才确认，尾盘回落不追"
    elif candidate_type == "strong_trend":
        plan = "高开过多不追，回踩不破 ma5 或 ma20 再观察"
    elif candidate_type == "pullback_watch":
        plan = "回踩 ma20 企稳再观察，跌破支撑则放弃"
    else:
        plan = "不满足当前策略候选类型，暂不进入观察池"
    if "ret_5_strong" in risk_flags:
        plan += "；短线已有加速，避免追高"
    if "rsi_high" in risk_flags:
        plan += "；RSI 偏高，注意回撤"
    return plan


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
