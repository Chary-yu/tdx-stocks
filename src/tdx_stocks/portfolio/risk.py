from __future__ import annotations

from collections import Counter
from typing import Any

from .models import Holding, RiskCheckResult


def check_portfolio_risk(
    holdings: list[Holding],
    *,
    max_weight: float = 0.10,
    min_holdings: int = 1,
    max_high_risk_tags: int = 0,
    max_avg_risk_score: float = 0.7,
    max_market_exposure: float = 0.75,
) -> RiskCheckResult:
    weights = [holding.weight for holding in holdings]
    market_exposure: dict[str, float] = {}
    for holding in holdings:
        market_exposure[holding.market] = market_exposure.get(holding.market, 0.0) + holding.weight

    risk_tag_counts = Counter(tag for holding in holdings for tag in holding.risk_flags)
    risk_scores = [holding.risk_score for holding in holdings if holding.risk_score is not None]
    avg_risk_score = round(sum(risk_scores) / len(risk_scores), 6) if risk_scores else None
    low_liquidity_count = sum(
        1
        for holding in holdings
        if _is_low_liquidity(holding)
    )
    missing_required_fields = sum(1 for holding in holdings if not holding.market or not holding.symbol)

    violations: list[str] = []
    warnings: list[str] = []
    if len(holdings) < min_holdings:
        violations.append("持仓数量不足")
    if any(weight > max_weight + 1e-12 for weight in weights):
        violations.append("单票权重超限")
    if sum(weights) and abs(sum(weights) - 1.0) > 0.02:
        warnings.append("权重合计异常")
    if any(exposure > max_market_exposure for exposure in market_exposure.values()):
        warnings.append("市场暴露过高")
    if sum(risk_tag_counts.values()) > max_high_risk_tags and max_high_risk_tags >= 0:
        warnings.append("高风险标签过多")
    if avg_risk_score is not None and avg_risk_score > max_avg_risk_score:
        warnings.append("平均 risk_score 偏高")
    if low_liquidity_count:
        warnings.append("低流动性股票存在")
    if missing_required_fields:
        violations.append("缺失关键字段")

    passed = not violations
    return RiskCheckResult(
        passed=passed,
        violations=violations,
        warnings=warnings,
        summary={
            "holding_count": len(holdings),
            "max_single_weight": round(max(weights), 6) if weights else 0.0,
            "market_exposure": {market: round(weight, 6) for market, weight in market_exposure.items()},
            "risk_tag_distribution": dict(risk_tag_counts),
            "avg_risk_score": avg_risk_score,
            "high_risk_stock_count": sum(1 for holding in holdings if _is_high_risk(holding)),
            "low_liquidity_stock_count": low_liquidity_count,
            "weight_sum": round(sum(weights), 6),
        },
    )


def _is_high_risk(holding: Holding) -> bool:
    if holding.risk_score is not None and holding.risk_score >= 0.7:
        return True
    return any(flag in {"risk_factor_missing", "mild_volatility"} for flag in holding.risk_flags)


def _is_low_liquidity(holding: Holding) -> bool:
    amount_ma20 = holding.factor_values.get("amount_ma20")
    if amount_ma20 is None:
        return "risk_factor_missing" in holding.risk_flags
    try:
        return float(amount_ma20) < 50_000_000.0
    except (TypeError, ValueError):
        return True
