from __future__ import annotations

from ..backtest import BacktestParams, run_backtest
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress


def run_backtest_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取回测任务配置")
    data = run_config.config
    strategy = data.get("strategy") or {}
    backtest = data.get("backtest") or {}

    def _pick(value, fallback):
        return fallback if value is None else value

    params = BacktestParams(
        from_date=parse_iso_date(backtest.get("from_date")),
        to_date=parse_iso_date(backtest.get("to_date")),
        top=int(_pick(backtest.get("top"), _pick(strategy.get("limit"), 20))),
        hold_days=int(_pick(backtest.get("hold_days"), 5)),
        fee_rate=float(_pick(backtest.get("fee_rate"), (backtest.get("fee_bps") or 0.0) / 10_000)),
        slippage=float(_pick(backtest.get("slippage"), (backtest.get("slippage_bps") or 0.0) / 10_000)),
        market=backtest.get("market"),
        candidate_type=backtest.get("candidate_type"),
        min_score=_pick(backtest.get("min_score"), strategy.get("min_score")),
        min_amount_ma20=_pick(backtest.get("min_amount_ma20"), strategy.get("min_amount_ma20")),
    )
    emit_progress(progress, "执行策略回测")
    strategy_name = str(strategy.get("name") or data.get("strategy_name") or "trend-strength")
    report = run_backtest(run_config.app_config, strategy_name, params)
    emit_progress(progress, "准备回测报告输出")
    return RunResult(
        task_type="backtest",
        name=run_config.task_name,
        status="success",
        summary=report.to_dict(),
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "backtest", as_of=backtest.get("to_date"), strategy=strategy_name),
    )
