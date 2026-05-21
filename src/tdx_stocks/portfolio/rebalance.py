from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import Holding, RebalanceAction, RebalancePlan
from .risk import check_portfolio_risk


def load_current_holdings_csv(path: Path) -> list[Holding]:
    rows: list[Holding] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                Holding(
                    market=str(row.get("market") or "").lower(),
                    symbol=str(row.get("symbol") or ""),
                    weight=float(row.get("weight") or 0.0),
                )
            )
    return rows


def build_rebalance_plan(
    current_holdings: list[Holding],
    target_holdings: list[Holding],
    *,
    as_of: str,
    min_trade_weight: float = 0.0,
    max_turnover: float | None = None,
    target_risk_filter: dict[str, Any] | None = None,
) -> RebalancePlan:
    current_map = {(holding.market, holding.symbol): holding for holding in current_holdings}
    target_map = {(holding.market, holding.symbol): holding for holding in target_holdings}
    keys = sorted(set(current_map) | set(target_map))

    diagnostics_filter = target_risk_filter or {}
    market_regime = diagnostics_filter.get("market_regime") if isinstance(diagnostics_filter.get("market_regime"), dict) else {}
    pause_open = market_regime.get("action") == "pause_open" or market_regime.get("status") in {"not_available", "bear"}
    actions: list[RebalanceAction] = []
    for market, symbol in keys:
        current = current_map.get((market, symbol))
        target = target_map.get((market, symbol))
        current_weight = current.weight if current else 0.0
        target_weight = target.weight if target else 0.0
        delta = round(target_weight - current_weight, 6)
        action, reason = _classify_action(current_weight, target_weight, min_trade_weight)
        if pause_open and action in {"BUY", "INCREASE"}:
            action = "HOLD_CASH"
            reason = "大盘风控要求暂停开仓，拒绝买入并保持现金"
            delta = 0.0
            target_weight = current_weight
        actions.append(
            RebalanceAction(
                market=market,
                symbol=symbol,
                current_weight=round(current_weight, 6),
                target_weight=round(target_weight, 6),
                delta_weight=delta,
                action=action,
                reason=reason,
            )
        )

    turnover = round(sum(abs(action.delta_weight) for action in actions) / 2.0, 6)
    if max_turnover is not None and turnover > max_turnover:
        reason = f"turnover {turnover} exceeds max_turnover {max_turnover}"
    else:
        reason = "ok"
    risk_summary = check_portfolio_risk(target_holdings).to_dict()
    target_risk_filter = diagnostics_filter

    estimated_impact_bps = _estimated_impact_bps(actions, target_holdings)
    execution_mode = "分批执行" if estimated_impact_bps is not None and estimated_impact_bps > 50 else "正常执行"

    buckets = {
        "buy": [action.to_dict() for action in actions if action.action == "BUY"],
        "sell": [action.to_dict() for action in actions if action.action == "SELL"],
        "hold": [action.to_dict() for action in actions if action.action == "HOLD"],
        "increase": [action.to_dict() for action in actions if action.action == "INCREASE"],
        "reduce": [action.to_dict() for action in actions if action.action == "REDUCE"],
    }
    return RebalancePlan(
        schema_version="rebalance-plan-v1",
        as_of=as_of,
        current_holdings=[holding.to_dict() for holding in current_holdings],
        target_holdings=[holding.to_dict() for holding in target_holdings],
        buy=buckets["buy"],
        sell=buckets["sell"],
        hold=buckets["hold"],
        increase=buckets["increase"],
        reduce=buckets["reduce"],
        weight_changes=[action.to_dict() for action in actions],
        turnover=turnover,
        risk_summary=risk_summary,
        diagnostics={
            "turnover_check": reason,
            "target_risk_filter": target_risk_filter,
            "risk_filter_applied": bool(target_risk_filter.get("risk_filter_applied")),
            "exclude_risk_tags": target_risk_filter.get("exclude_risk_tags") or [],
            "risk_interceptions": target_risk_filter.get("risk_interceptions") or [],
            "market_regime": market_regime,
            "pre_trade_message": "大盘风控暂停开仓，BUY/INCREASE 已转为 HOLD_CASH" if pause_open else "前置风控通过",
            "estimated_impact_bps": estimated_impact_bps,
            "execution_mode": execution_mode,
        },
    )



def _estimated_impact_bps(actions: list[RebalanceAction], target_holdings: list[Holding]) -> float | None:
    # Lightweight deterministic estimate: base 5 bps per 10% turnover. Real broker/market-impact model can replace this later.
    turnover = sum(abs(action.delta_weight) for action in actions) / 2.0
    return round(turnover * 50.0, 4)


def _classify_action(current_weight: float, target_weight: float, min_trade_weight: float) -> tuple[str, str]:
    delta = target_weight - current_weight
    if current_weight <= 0 and target_weight > 0:
        return "BUY", "current position absent"
    if current_weight > 0 and target_weight <= 0:
        return "SELL", "target position absent"
    if abs(delta) < min_trade_weight:
        return "HOLD", "weight change below min_trade_weight"
    if delta > 0:
        return "INCREASE", "target weight above current"
    if delta < 0:
        return "REDUCE", "target weight below current"
    return "HOLD", "no change"
