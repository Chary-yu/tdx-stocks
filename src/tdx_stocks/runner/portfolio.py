from __future__ import annotations

from ..portfolio import build_portfolio
from ..portfolio.risk_controls import DEFAULT_EXCLUDE_RISK_TAGS, normalize_exclude_risk_tags
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress
from .dates import resolve_report_as_of


def run_portfolio_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取组合任务配置")
    data = run_config.config
    portfolio = data.get("portfolio") or {}
    macro_filter = data.get("macro_filter") if isinstance(data.get("macro_filter"), dict) else {}
    event_calendar = data.get("event_calendar") if isinstance(data.get("event_calendar"), dict) else {}
    task_data = data.get("data") or {}
    as_of_value = task_data.get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else parse_iso_date(as_of_value)
    emit_progress(progress, "构建目标组合")
    report = build_portfolio(
        run_config.app_config,
        source=str(portfolio.get("source") or "consensus"),
        top=int(portfolio.get("top") or 20),
        weighting=str(portfolio.get("weighting") or "liquidity-risk"),
        max_weight=float(portfolio.get("max_weight") or 0.10),
        min_weight=float(portfolio.get("min_weight") or 0.0),
        max_risk_score=portfolio.get("max_risk_score"),
        exclude_risk_tags=normalize_exclude_risk_tags(portfolio.get("exclude_risk_tags") or DEFAULT_EXCLUDE_RISK_TAGS),
        market=portfolio.get("market"),
        capital=float(portfolio.get("capital") or 10_000_000),
        max_adv_participation=float(portfolio.get("max_adv_participation") or 0.10),
        max_liquidation_days=float(portfolio.get("max_liquidation_days") or 3.0),
        market_regime_enabled=bool(portfolio.get("market_regime_enabled") or False),
        sector_max_weight=float(portfolio.get("max_sector_weight") or 0.25),
        market_regime_config=macro_filter,
        event_calendar_config=event_calendar,
        weighting_hybrid_config=portfolio.get("weighting_hybrid") if isinstance(portfolio.get("weighting_hybrid"), dict) else None,
        as_of=as_of,
    )
    emit_progress(progress, "准备组合报告输出")
    return RunResult(
        task_type="portfolio",
        name=run_config.task_name,
        status="success",
        summary=report.to_dict(),
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "portfolio", as_of=resolve_report_as_of(run_config.app_config, report.to_dict().get("as_of") or as_of_value)),
    )
