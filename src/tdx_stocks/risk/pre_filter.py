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
    cfg = _normalize_config(config or {})
    reasons: list[str] = []
    details: list[dict[str, Any]] = []

    def _hit(rule: str, actual: Any, threshold: Any, reason: str) -> None:
        reasons.append(reason)
        details.append({"rule": rule, "actual": actual, "threshold": threshold, "result": "filtered_out"})

    tags = {str(x) for x in (candidate.get("tags") or [])} | {str(x) for x in (candidate.get("risk_flags") or [])}

    if bool(cfg.get("exclude_st", True)) and ("st" in tags or bool(candidate.get("is_st"))):
        _hit("exclude_st", candidate.get("is_st"), False, "ST 股票")

    delist = candidate.get("delisting_risk", candidate.get("delist_risk"))
    if bool(cfg.get("exclude_delisting_risk", True)) and bool(delist):
        _hit("exclude_delisting_risk", delist, False, "退市风险")

    listed_days = _f(candidate.get("listing_days", candidate.get("listed_days")))
    min_listing_days = _f(cfg.get("min_listing_days"))
    if listed_days is not None and min_listing_days is not None and listed_days < min_listing_days:
        _hit("min_listing_days", listed_days, min_listing_days, "上市天数不足")

    price = _f(candidate.get("close", candidate.get("price")))
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

    turnover_ma20 = _f(candidate.get("turnover_ma20", candidate.get("turnover")))
    min_turnover = _f(cfg.get("min_turnover"))
    if turnover_ma20 is not None and min_turnover is not None and turnover_ma20 < min_turnover:
        _hit("min_turnover", turnover_ma20, min_turnover, "20 日均换手率不足")

    vol = _f(candidate.get("annual_volatility", candidate.get("annualized_volatility")))
    max_vol = _f(cfg.get("max_volatility"))
    if vol is not None and max_vol is not None and vol > max_vol:
        _hit("max_volatility", vol, max_vol, "年化波动率过高")

    mdd = _f(candidate.get("max_drawdown_1y", candidate.get("max_drawdown")))
    max_mdd = _f(cfg.get("max_drawdown"))
    if mdd is not None and max_mdd is not None and abs(mdd) > max_mdd:
        _hit("max_drawdown", mdd, max_mdd, "一年最大回撤过高")

    trading_days = _f(candidate.get("trading_days"))
    min_trading_days = _f(cfg.get("min_trading_days"))
    if trading_days is not None and min_trading_days is not None and trading_days < min_trading_days:
        _hit("min_trading_days", trading_days, min_trading_days, "交易数据不足")

    fin_age = _f(candidate.get("financial_data_age_months"))
    max_fin_age = _f(cfg.get("max_financial_data_age_months"))
    if fin_age is not None and max_fin_age is not None and fin_age > max_fin_age:
        _hit("max_financial_data_age_months", fin_age, max_fin_age, "财务数据过旧")

    if bool(candidate.get("data_quality_insufficient")):
        _hit("data_quality", candidate.get("data_quality_insufficient"), False, "数据质量不足")

    required_fields = cfg.get("required_fields")
    if isinstance(required_fields, (list, tuple, set)):
        missing = [str(name) for name in required_fields if candidate.get(str(name)) in (None, "")]
        if missing:
            _hit("required_fields", ",".join(missing), "non-empty", "数据质量不足")

    return PreFilterResult(passed=not reasons, reasons=reasons, details=details)


def _normalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Accept both flat legacy config and the layered screening_pre_filter.toml shape."""
    cfg = dict(config or {})
    basic = cfg.get("basic") if isinstance(cfg.get("basic"), dict) else {}
    liquidity = cfg.get("liquidity") if isinstance(cfg.get("liquidity"), dict) else {}
    risk = cfg.get("risk") if isinstance(cfg.get("risk"), dict) else {}
    quality = cfg.get("data_quality") if isinstance(cfg.get("data_quality"), dict) else {}
    normalized: dict[str, Any] = {}
    normalized.update({
        "exclude_st": basic.get("exclude_st", cfg.get("exclude_st", True)),
        "exclude_delisting_risk": basic.get("exclude_delisting_risk", cfg.get("exclude_delisting_risk", True)),
        "min_listing_days": basic.get("min_listing_days", cfg.get("min_listing_days", cfg.get("min_listed_days"))),
        "min_price": basic.get("min_price", cfg.get("min_price")),
        "max_price": basic.get("max_price", cfg.get("max_price")),
        "min_amount_ma20": liquidity.get("min_amount_ma20", cfg.get("min_amount_ma20")),
        "min_turnover": liquidity.get("min_turnover", cfg.get("min_turnover", cfg.get("min_turnover_ma20"))),
        "max_volatility": risk.get("max_volatility", cfg.get("max_volatility", cfg.get("max_annualized_volatility"))),
        "max_drawdown": risk.get("max_drawdown", cfg.get("max_drawdown", cfg.get("max_drawdown_1y"))),
        "min_trading_days": quality.get("min_trading_days", cfg.get("min_trading_days")),
        "max_financial_data_age_months": quality.get("max_financial_data_age_months", cfg.get("max_financial_data_age_months")),
        "required_fields": quality.get("required_fields", cfg.get("required_fields")),
    })
    return normalized


def _f(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
