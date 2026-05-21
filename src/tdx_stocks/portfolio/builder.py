from __future__ import annotations

from dataclasses import replace
from datetime import datetime, date
from typing import Any

from ..config import AppConfig
from ..config_validators import optional_str
from ..pipeline import parse_iso_date
from ..strategies.consensus import build_consensus
from ..strategies.registry import get_strategy, list_strategies
from ..strategies.storage import load_saved_report
from .models import Holding, PortfolioReport
from .risk import check_portfolio_risk
from .risk_controls import (
    DEFAULT_CAPITAL,
    DEFAULT_EXCLUDE_RISK_TAGS,
    DEFAULT_MAX_ADV_PARTICIPATION,
    DEFAULT_MAX_LIQUIDATION_DAYS,
    candidate_tags,
    liquidity_metrics,
    market_regime_placeholder,
    normalize_exclude_risk_tags,
    risk_interception,
    sector_exposure,
    technical_concentration,
    technical_exit_policy,
)
from .optimizer import optimize_weights
from .risk_interceptor import apply_risk_interceptors
from ..risk.market_regime import evaluate_market_regime


def build_portfolio(
    config: AppConfig,
    *,
    source: str = "consensus",
    strategy: str | None = None,
    top: int = 20,
    weighting: str = "equal",
    max_weight: float = 0.10,
    min_weight: float = 0.0,
    max_risk_score: float | None = None,
    exclude_risk_tags: tuple[str, ...] = (),
    market: str | None = None,
    as_of: date | None = None,
    capital: float | None = None,
    max_adv_participation: float = DEFAULT_MAX_ADV_PARTICIPATION,
    max_liquidation_days: float = DEFAULT_MAX_LIQUIDATION_DAYS,
    market_regime_enabled: bool = False,
    sector_max_weight: float = 0.25,
) -> PortfolioReport:
    candidates, data_run_id, resolved_as_of = _load_candidates(config, source, strategy, as_of)
    normalized_exclude_tags = normalize_exclude_risk_tags(exclude_risk_tags or DEFAULT_EXCLUDE_RISK_TAGS)
    risk_interceptions: list[dict[str, Any]] = []
    base_filtered: list[dict[str, Any]] = []
    excluded_count = 0
    for candidate in candidates:
        if market and str(candidate.get("market") or "").lower() != market.lower():
            excluded_count += 1
            risk_interceptions.append(risk_interception(candidate, reason=f"市场不匹配：{market}", trigger_tags=[]))
            continue
        risk_flags = [str(flag) for flag in candidate.get("risk_flags") or []]
        tags = [str(tag) for tag in candidate.get("tags") or []]
        matched_tags = sorted(set(normalized_exclude_tags) & candidate_tags(candidate))
        if matched_tags:
            excluded_count += 1
            risk_interceptions.append(risk_interception(candidate, reason="命中组合风控剔除标签", trigger_tags=matched_tags))
            continue
        risk_score = _float_or_none(candidate.get("risk_score"))
        if max_risk_score is not None and risk_score is not None and risk_score > max_risk_score:
            excluded_count += 1
            risk_interceptions.append(risk_interception(candidate, reason=f"风险分 {risk_score:.2f} 高于上限 {max_risk_score}", trigger_tags=[]))
            continue
        base_filtered.append(candidate)

    filtered_candidates, extra_logs = apply_risk_interceptors(
        base_filtered,
        exclude_risk_tags=normalized_exclude_tags,
        event_calendar_cfg=getattr(config, "event_calendar", None) if hasattr(config, "event_calendar") else None,
    )
    risk_interceptions.extend(extra_logs)

    filtered_candidates = sorted(
        filtered_candidates,
        key=lambda item: (
            -_float_or_zero(item.get("score")),
            len(item.get("risk_flags") or []),
            str(item.get("market") or ""),
            str(item.get("symbol") or ""),
        ),
    )[:top]

    if market_regime_enabled:
        regime = evaluate_market_regime({"status": "not_available", "missing_action": "pause_open"}).to_dict()
    else:
        regime = market_regime_placeholder(enabled=False)
    hard_intercepted = market_regime_enabled and (regime.get("action") == "pause_open" or regime.get("status") in {"not_available", "bear"})
    if hard_intercepted:
        filtered_candidates = []
        risk_interceptions.extend(risk_interception(candidate, reason="市场环境滤网触发行情熔断，暂停开仓", trigger_tags=["market_regime_block"]) for candidate in candidates[:50])

    filtered_candidates = _apply_near_high_cap(filtered_candidates, max_near_high_weight=0.40)

    if not filtered_candidates:
        holdings: list[Holding] = []
    else:
        weights = optimize_weights(
            filtered_candidates,
            mode=weighting,
            max_weight=max_weight,
            min_weight=min_weight,
            capital=capital,
            max_adv_participation=max_adv_participation,
            max_liquidation_days=max_liquidation_days,
        )
        holdings = [
            _candidate_to_holding(candidate, weight, source, strategy, capital=capital, max_adv_participation=max_adv_participation, max_liquidation_days=max_liquidation_days)
            for candidate, weight in zip(filtered_candidates, weights, strict=True)
        ]

    risk = check_portfolio_risk(holdings, max_weight=max_weight)
    summary = {
        "source": source,
        "strategy": strategy,
        "candidate_count": len(candidates),
        "selected_count": len(holdings),
        "excluded_count": excluded_count,
        "weighting": weighting,
        "max_weight": max_weight,
        "min_weight": min_weight,
        "max_risk_score": max_risk_score,
        "market": market,
        "risk_filter_applied": True,
        "exclude_risk_tags": list(normalized_exclude_tags),
        "risk_interception_count": len(risk_interceptions),
    }
    holding_dicts = [holding.to_dict() for holding in holdings]
    sector = sector_exposure(holding_dicts, max_sector_weight=sector_max_weight)
    diagnostics = {
        "source_candidate_count": len(candidates),
        "filtered_candidate_count": len(filtered_candidates),
        "risk_check": risk.to_dict(),
        "risk_filter_applied": True,
        "exclude_risk_tags": list(normalized_exclude_tags),
        "risk_interceptions": risk_interceptions,
        "market_regime": regime,
        "hard_interception": hard_intercepted,
        "hard_interception_reason": "行情熔断：市场环境数据缺失或要求暂停开仓" if hard_intercepted else None,
        "sector_exposure": sector,
        "technical_concentration": technical_concentration(holding_dicts),
        "technical_exit_policy": technical_exit_policy(),
    }
    return PortfolioReport.build(
        generated_at=datetime.now(),
        as_of=resolved_as_of or "latest",
        data_run_id=data_run_id,
        source=source,
        params={
            "source": source,
            "strategy": strategy,
            "top": top,
            "weighting": weighting,
            "max_weight": max_weight,
            "min_weight": min_weight,
            "max_risk_score": max_risk_score,
            "exclude_risk_tags": list(normalized_exclude_tags),
            "market": market,
            "capital": capital,
            "max_adv_participation": max_adv_participation,
            "max_liquidation_days": max_liquidation_days,
            "as_of": as_of.isoformat() if as_of else None,
        },
        holdings=holdings,
        summary=summary,
        risk_summary=risk.to_dict(),
        diagnostics=diagnostics,
    )


def _load_candidates(
    config: AppConfig,
    source: str,
    strategy: str | None,
    as_of: date | str | None,
) -> tuple[list[dict[str, Any]], str | None, str | date]:
    if source == "consensus":
        strategy_names = [definition.name for definition in list_strategies() if definition.group != "pair"]
        result = build_consensus(config, strategy_names, as_of=as_of, min_hit=2)
        rows = []
        for row in result.rows:
            rows.append(
                {
                    "market": row.market,
                    "symbol": row.symbol,
                    "score": row.avg_score,
                    "candidate_type": row.candidate_types[0] if row.candidate_types else None,
                    "source_strategy": "consensus",
                    "source_strategies": row.strategies,
                    "risk_flags": row.risk_flags,
                    "tags": row.tags,
                    "reason": ", ".join(row.reasons) or "consensus",
                    "risk_score": row.risk_score,
                }
            )
        return rows, None, result.as_of

    if not strategy:
        raise ValueError("strategy is required when source is not consensus")
    if source == "strategy":
        definition = get_strategy(strategy)
        report = definition.runner(config, definition.default_params if as_of is None else replace(definition.default_params, as_of=as_of))
        candidates = list(report.picks)
        return candidates, optional_str(report.summary.get("dataset_run_id")), as_of or "latest"

    if source == "report":
        if strategy is None:
            raise ValueError("strategy is required when source=report")
        report_as_of = "latest" if as_of is None else (as_of.isoformat() if isinstance(as_of, date) else as_of)
        doc = load_saved_report(
            config.paths.data_root,
            strategy,
            as_of=report_as_of,
        )
        if doc is None:
            raise FileNotFoundError(f"saved strategy report not found for {strategy!r}")
        return list(doc.get("candidates") or []), optional_str(doc.get("data_run_id")), str(doc.get("as_of") or "latest")
    raise ValueError(f"unknown portfolio source: {source}")



def _apply_near_high_cap(candidates: list[dict[str, Any]], *, max_near_high_weight: float) -> list[dict[str, Any]]:
    if not candidates:
        return []
    kept = list(candidates)
    def is_near(item: dict[str, Any]) -> bool:
        return "near_20d_high" in set(str(x) for x in (item.get("risk_flags") or [])) | set(str(x) for x in (item.get("tags") or []))
    while kept:
        near = [item for item in kept if is_near(item)]
        if not near or len(near) / len(kept) <= max_near_high_weight:
            break
        # Drop the weakest near-high candidate first to control同向技术风险集中度.
        weakest = sorted(near, key=lambda item: _float_or_zero(item.get("score")))[0]
        kept.remove(weakest)
    return kept


def _candidate_to_holding(
    candidate: dict[str, Any],
    weight: float,
    source: str,
    strategy: str | None,
    *,
    capital: float | None = None,
    max_adv_participation: float = DEFAULT_MAX_ADV_PARTICIPATION,
    max_liquidation_days: float = DEFAULT_MAX_LIQUIDATION_DAYS,
) -> Holding:
    factor_values = dict(candidate.get("factor_values") or {})
    factor_values.update(liquidity_metrics(candidate, weight=weight, capital=capital or DEFAULT_CAPITAL, max_adv_participation=max_adv_participation, max_liquidation_days=max_liquidation_days))
    for key in ("sector", "industry", "amount_ma20", "adv"):
        if key in candidate and key not in factor_values:
            factor_values[key] = candidate.get(key)
    source_strategies = candidate.get("source_strategies")
    if not isinstance(source_strategies, list):
        source_strategies = []
    return Holding(
        market=str(candidate.get("market") or "").lower(),
        symbol=str(candidate.get("symbol") or ""),
        weight=round(weight, 6),
        score=_float_or_none(candidate.get("score")),
        source_strategy=str(candidate.get("source_strategy") or strategy or source),
        source_strategies=[str(item) for item in source_strategies],
        candidate_type=str(candidate.get("candidate_type")) if candidate.get("candidate_type") else None,
        risk_flags=[str(item) for item in candidate.get("risk_flags") or []],
        tags=[str(item) for item in candidate.get("tags") or []],
        reason=str(candidate.get("reason") or candidate.get("reasons") or ""),
        risk_score=_float_or_none(candidate.get("risk_score")),
        factor_values=factor_values,
    )


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_or_zero(value: Any) -> float:
    result = _float_or_none(value)
    return result if result is not None else 0.0
