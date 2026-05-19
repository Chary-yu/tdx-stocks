from __future__ import annotations

from pathlib import Path

from ..portfolio import build_portfolio, build_rebalance_plan, load_current_holdings_csv
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult


def run_rebalance_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    portfolio = data.get("portfolio") or {}
    rebalance = data.get("rebalance") or {}
    task_data = data.get("data") or {}
    as_of_value = task_data.get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else parse_iso_date(as_of_value)
    target = build_portfolio(
        run_config.app_config,
        source=str(portfolio.get("source") or "consensus"),
        top=int(portfolio.get("top") or 20),
        weighting=str(portfolio.get("weighting") or "equal"),
        max_weight=float(portfolio.get("max_weight") or 0.10),
        min_weight=float(portfolio.get("min_weight") or 0.0),
        max_risk_score=portfolio.get("max_risk_score"),
        exclude_risk_tags=tuple(portfolio.get("exclude_risk_tags") or ()),
        market=portfolio.get("market"),
        as_of=as_of,
    )
    holdings_path = rebalance.get("current_holdings")
    current = load_current_holdings_csv(Path(holdings_path)) if holdings_path else []
    plan = build_rebalance_plan(
        current,
        target.holdings,
        as_of=target.as_of,
        min_trade_weight=float(rebalance.get("min_trade_weight") or 0.0),
        max_turnover=rebalance.get("max_turnover"),
    )
    return RunResult(
        task_type="rebalance",
        name=str((data.get("task") or {}).get("name") or "rebalance"),
        status="success",
        summary=plan.to_dict(),
    )
