from __future__ import annotations

from collections import Counter
from typing import Any

DEFAULT_EXCLUDE_RISK_TAGS = ("high_volatility", "low_liquidity")
DEFAULT_INSTITUTIONAL_MIN_AMOUNT_MA20 = 150_000_000.0
DEFAULT_MAX_ADV_PARTICIPATION = 0.10
DEFAULT_MAX_LIQUIDATION_DAYS = 0.5
DEFAULT_CAPITAL = 10_000_000.0
DEFAULT_MAX_SECTOR_WEIGHT = 0.25

RISK_TAG_LABELS = {
    "high_volatility": "高波动",
    "low_liquidity": "低流动性",
    "near_20d_high": "接近20日高点",
    "ret_5_strong": "近5日涨幅较强",
    "rsi_high": "RSI偏高",
    "mild_volatility": "波动偏高",
}


def normalize_exclude_risk_tags(values: object) -> tuple[str, ...]:
    if values in (None, ""):
        return DEFAULT_EXCLUDE_RISK_TAGS
    if isinstance(values, str):
        return tuple(item.strip() for item in values.split(",") if item.strip()) or DEFAULT_EXCLUDE_RISK_TAGS
    if isinstance(values, (list, tuple, set)):
        normalized = tuple(str(item).strip() for item in values if str(item).strip())
        return normalized or DEFAULT_EXCLUDE_RISK_TAGS
    return DEFAULT_EXCLUDE_RISK_TAGS


def candidate_tags(candidate: dict[str, Any]) -> set[str]:
    values: set[str] = set()
    for key in ("risk_flags", "tags"):
        raw = candidate.get(key)
        if isinstance(raw, (list, tuple, set)):
            values.update(str(item) for item in raw if item not in (None, ""))
        elif raw not in (None, ""):
            values.add(str(raw))
    return values


def risk_interception(candidate: dict[str, Any], *, reason: str, trigger_tags: list[str] | None = None) -> dict[str, Any]:
    return {
        "market": str(candidate.get("market") or "").lower(),
        "symbol": str(candidate.get("symbol") or candidate.get("code") or ""),
        "display_symbol": candidate.get("display_symbol"),
        "score": candidate.get("score"),
        "source_strategy": candidate.get("source_strategy"),
        "source_strategies": candidate.get("source_strategies") or [],
        "candidate_type": candidate.get("candidate_type"),
        "risk_flags": list(candidate.get("risk_flags") or []),
        "tags": list(candidate.get("tags") or []),
        "trigger_tags": trigger_tags or [],
        "reason": reason,
        "action": "rejected",
    }


def amount_ma20(candidate: dict[str, Any]) -> float | None:
    for key in ("amount_ma20", "adv", "avg_daily_amount", "turnover_amount_ma20"):
        value = candidate.get(key)
        if value is None:
            factors = candidate.get("factor_values") if isinstance(candidate.get("factor_values"), dict) else {}
            value = factors.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def liquidity_metrics(
    candidate: dict[str, Any],
    *,
    weight: float,
    capital: float | None,
    max_adv_participation: float,
    max_liquidation_days: float,
) -> dict[str, Any]:
    adv = amount_ma20(candidate)
    if adv is None or adv <= 0 or not capital or capital <= 0:
        return {
            "amount_ma20": adv,
            "target_amount": None,
            "target_amount_to_adv": None,
            "expected_liquidation_days": None,
            "liquidity_weight_cap": None,
            "liquidity_constraint": "no_adv_data",
        }
    target_amount = capital * weight
    per_day_capacity = max(adv * max_adv_participation, 1.0)
    expected_days = target_amount / per_day_capacity
    cap = (adv * max_adv_participation * max_liquidation_days) / capital
    return {
        "amount_ma20": round(adv, 2),
        "target_amount": round(target_amount, 2),
        "target_amount_to_adv": round(target_amount / adv, 6),
        "expected_liquidation_days": round(expected_days, 4),
        "liquidity_weight_cap": round(cap, 6),
        "liquidity_constraint": "pass" if expected_days <= max_liquidation_days else "exceeds_liquidation_days",
    }


def sector_exposure(holdings: list[dict[str, Any]], *, max_sector_weight: float = DEFAULT_MAX_SECTOR_WEIGHT) -> dict[str, Any]:
    weights: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    missing = 0
    for holding in holdings:
        factors = holding.get("factor_values") if isinstance(holding.get("factor_values"), dict) else {}
        sector = holding.get("sector") or holding.get("industry") or factors.get("sector") or factors.get("industry") or factors.get("申万行业")
        if not sector:
            missing += 1
            continue
        text = str(sector)
        counts[text] += 1
        try:
            weights[text] += float(holding.get("weight") or 0.0)
        except (TypeError, ValueError):
            pass
    rows = []
    for sector, weight in weights.most_common():
        rows.append({
            "sector": sector,
            "count": counts[sector],
            "weight": round(weight, 6),
            "warning": weight > max_sector_weight,
        })
    return {
        "available": bool(rows),
        "rows": rows,
        "missing_count": missing,
        "max_sector_weight": max_sector_weight,
        "warnings": [f"行业集中度过高：{row['sector']}" for row in rows if row.get("warning")],
    }



def technical_concentration(holdings: list[dict[str, Any]], *, max_near_high_weight: float = 0.40) -> dict[str, Any]:
    total = 0.0
    count = 0
    for holding in holdings:
        flags = set(str(item) for item in holding.get("risk_flags") or []) | set(str(item) for item in holding.get("tags") or [])
        if "near_20d_high" in flags:
            count += 1
            try:
                total += float(holding.get("weight") or 0.0)
            except (TypeError, ValueError):
                pass
    return {
        "near_20d_high_count": count,
        "near_20d_high_weight": round(total, 6),
        "max_near_20d_high_weight": max_near_high_weight,
        "warning": total > max_near_high_weight,
        "message": "接近20日高点权重超过上限" if total > max_near_high_weight else "正常",
    }


def market_regime_placeholder(*, enabled: bool = False, index: str = "国证A指", ma_window: int = 20, bear_action: str = "pause_open") -> dict[str, Any]:
    return {
        "enabled": bool(enabled),
        "index": index,
        "ma_window": ma_window,
        "status": "not_available" if enabled else "disabled",
        "action": "仅记录，不自动减仓" if not enabled else bear_action,
        "message": "未接入指数均线数据，暂无法自动判断市场多空状态" if enabled else "市场环境滤网未启用",
    }


def technical_exit_policy(max_holding_days: object = None) -> dict[str, Any]:
    return {
        "mode": "technical_with_max_holding_days",
        "max_holding_days": max_holding_days,
        "rules": [
            "ATR吊灯止损：后续接入 ATR 后动态计算",
            "移动均线破位：后续接入 MA 死叉/跌破均线后触发",
            "前低破位：后续接入形态低点后触发",
        ],
        "note": "当前补丁先将固定 hold_days 降级为最大持有天数语义，完整逐笔动态退出仍需在回测引擎中继续实现。",
    }
