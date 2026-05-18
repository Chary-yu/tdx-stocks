from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

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
) -> RebalancePlan:
    current_map = {(holding.market, holding.symbol): holding for holding in current_holdings}
    target_map = {(holding.market, holding.symbol): holding for holding in target_holdings}
    keys = sorted(set(current_map) | set(target_map))

    actions: list[RebalanceAction] = []
    for market, symbol in keys:
        current = current_map.get((market, symbol))
        target = target_map.get((market, symbol))
        current_weight = current.weight if current else 0.0
        target_weight = target.weight if target else 0.0
        delta = round(target_weight - current_weight, 6)
        action, reason = _classify_action(current_weight, target_weight, min_trade_weight)
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
        diagnostics={"turnover_check": reason},
    )


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
