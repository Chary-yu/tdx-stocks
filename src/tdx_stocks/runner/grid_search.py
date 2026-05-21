from __future__ import annotations

from ..backtest import BacktestParams, tune_strategy_parameters
from .backtest import DEFAULT_FEE_RATE, DEFAULT_SLIPPAGE
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress


def run_grid_search_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取参数搜索任务配置")
    data = run_config.config
    strategy = data.get("strategy") or {}
    backtest = data.get("backtest") or {}
    grid = data.get("grid") or {}
    params = BacktestParams(
        from_date=parse_iso_date(backtest.get("from_date")),
        to_date=parse_iso_date(backtest.get("to_date")),
        top=int(backtest.get("top") or 10),
        hold_days=int(backtest.get("hold_days") or 5),
        fee_rate=float(backtest.get("fee_rate") if backtest.get("fee_rate") is not None else (backtest.get("fee_bps") / 10_000 if backtest.get("fee_bps") is not None else DEFAULT_FEE_RATE)),
        slippage=float(backtest.get("slippage") if backtest.get("slippage") is not None else (backtest.get("slippage_bps") / 10_000 if backtest.get("slippage_bps") is not None else DEFAULT_SLIPPAGE)),
        market=backtest.get("market"),
        candidate_type=backtest.get("candidate_type"),
        min_score=backtest.get("min_score") or strategy.get("min_score"),
        min_amount_ma20=backtest.get("min_amount_ma20") or strategy.get("min_amount_ma20"),
        rolling=bool(backtest.get("rolling", False)),
    )
    emit_progress(progress, "执行参数网格搜索")
    strategy_name = str(strategy.get("name") or data.get("strategy_name") or "trend-strength")
    report = tune_strategy_parameters(
        run_config.app_config,
        strategy_name,
        params,
        min_scores=list(grid.get("strategy.min_score") or [60, 65]),
        tops=list(grid.get("backtest.top") or [10]),
        hold_days=list(grid.get("backtest.hold_days") or [5, 10]),
        min_amount_ma20_values=list(grid.get("strategy.min_amount_ma20") or [params.min_amount_ma20]),
        progress=progress,
    )
    emit_progress(progress, "准备参数搜索报告输出")
    return RunResult(
        task_type="grid_search",
        name=run_config.task_name,
        status="success",
        summary=report,
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "grid_search", as_of=backtest.get("to_date"), strategy=strategy_name),
    )
