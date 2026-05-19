from __future__ import annotations

from ..portfolio import build_portfolio
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult


def run_portfolio_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    portfolio = data.get("portfolio") or {}
    task_data = data.get("data") or {}
    as_of_value = task_data.get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else parse_iso_date(as_of_value)
    report = build_portfolio(
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
    return RunResult(
        task_type="portfolio",
        name=str((data.get("task") or {}).get("name") or "portfolio"),
        status="success",
        summary=report.to_dict(),
    )
