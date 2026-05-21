from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreFilterResult:
    passed: bool
    reasons: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": list(self.reasons)}


def apply_pre_filter(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> PreFilterResult:
    cfg = config or {}
    reasons: list[str] = []
    tags = {str(x) for x in (candidate.get("tags") or [])} | {str(x) for x in (candidate.get("risk_flags") or [])}
    if "st" in tags or bool(candidate.get("is_st")):
        reasons.append("ST 股票")
    if bool(candidate.get("delist_risk")):
        reasons.append("退市风险")
    price = _f(candidate.get("close"))
    min_price = _f(cfg.get("min_price"))
    max_price = _f(cfg.get("max_price"))
    if price is not None and min_price is not None and price < min_price:
        reasons.append("股价低于下限")
    if price is not None and max_price is not None and price > max_price:
        reasons.append("股价高于上限")
    amount_ma20 = _f(candidate.get("amount_ma20"))
    min_amount_ma20 = _f(cfg.get("min_amount_ma20"))
    if amount_ma20 is not None and min_amount_ma20 is not None and amount_ma20 < min_amount_ma20:
        reasons.append("20 日均成交额不足")
    turnover_ma20 = _f(candidate.get("turnover_ma20"))
    min_turnover_ma20 = _f(cfg.get("min_turnover_ma20"))
    if turnover_ma20 is not None and min_turnover_ma20 is not None and turnover_ma20 < min_turnover_ma20:
        reasons.append("20 日均换手率不足")
    vol = _f(candidate.get("annualized_volatility"))
    max_vol = _f(cfg.get("max_annualized_volatility"))
    if vol is not None and max_vol is not None and vol > max_vol:
        reasons.append("年化波动率过高")
    mdd = _f(candidate.get("max_drawdown_1y"))
    max_mdd = _f(cfg.get("max_drawdown_1y"))
    if mdd is not None and max_mdd is not None and mdd > max_mdd:
        reasons.append("一年最大回撤过高")
    if bool(candidate.get("data_quality_insufficient")):
        reasons.append("数据质量不足")
    return PreFilterResult(passed=not reasons, reasons=reasons)


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
