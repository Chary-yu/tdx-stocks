from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreFilterResult:
    passed: bool
    reasons: list[str]
    details: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "reasons": list(self.reasons), "details": list(self.details)}


def apply_pre_filter(candidate: dict[str, Any], config: dict[str, Any] | None = None) -> PreFilterResult:
    cfg = config or {}
    reasons: list[str] = []
    details: list[dict[str, Any]] = []
    def _hit(rule: str, actual: Any, threshold: Any, reason: str) -> None:
        reasons.append(reason)
        details.append({"rule": rule, "actual": actual, "threshold": threshold, "result": "filtered_out"})
    tags = {str(x) for x in (candidate.get("tags") or [])} | {str(x) for x in (candidate.get("risk_flags") or [])}
    if "st" in tags or bool(candidate.get("is_st")):
        _hit("is_st", candidate.get("is_st"), True, "ST 股票")
    if bool(candidate.get("delist_risk")):
        _hit("delisting_risk", candidate.get("delist_risk"), False, "退市风险")
    listed_days = _f(candidate.get("listed_days"))
    min_listed_days = _f(cfg.get("min_listed_days"))
    if listed_days is not None and min_listed_days is not None and listed_days < min_listed_days:
        _hit("listing_days", listed_days, min_listed_days, "上市天数不足")
    price = _f(candidate.get("close"))
    min_price = _f(cfg.get("min_price"))
    max_price = _f(cfg.get("max_price"))
    if price is not None and min_price is not None and price < min_price:
        _hit("min_price", price, min_price, "股价低于下限")
    if price is not None and max_price is not None and price > max_price:
        _hit("max_price", price, max_price, "股价高于上限")
    amount_ma20 = _f(candidate.get("amount_ma20"))
    min_amount_ma20 = _f(cfg.get("min_amount_ma20"))
    if amount_ma20 is not None and min_amount_ma20 is not None and amount_ma20 < min_amount_ma20:
        _hit("min_amount_ma20", amount_ma20, min_amount_ma20, "20 日均成交额不足")
    turnover_ma20 = _f(candidate.get("turnover_ma20"))
    min_turnover_ma20 = _f(cfg.get("min_turnover_ma20"))
    if turnover_ma20 is not None and min_turnover_ma20 is not None and turnover_ma20 < min_turnover_ma20:
        _hit("min_turnover_ma20", turnover_ma20, min_turnover_ma20, "20 日均换手率不足")
    vol = _f(candidate.get("annualized_volatility"))
    max_vol = _f(cfg.get("max_annualized_volatility"))
    if vol is not None and max_vol is not None and vol > max_vol:
        _hit("max_annualized_volatility", vol, max_vol, "年化波动率过高")
    mdd = _f(candidate.get("max_drawdown_1y"))
    max_mdd = _f(cfg.get("max_drawdown_1y"))
    if mdd is not None and max_mdd is not None and mdd > max_mdd:
        _hit("max_drawdown_1y", mdd, max_mdd, "一年最大回撤过高")
    if bool(candidate.get("data_quality_insufficient")):
        _hit("data_quality", candidate.get("data_quality_insufficient"), False, "数据质量不足")
    required_fields = cfg.get("required_fields")
    if isinstance(required_fields, (list, tuple, set)):
        missing = [str(name) for name in required_fields if candidate.get(str(name)) in (None, "")]
        if missing:
            _hit("required_fields", ",".join(missing), "non-empty", "数据质量不足")
    return PreFilterResult(passed=not reasons, reasons=reasons, details=details)


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
