from __future__ import annotations

from itertools import product

from ..backtest import BacktestParams, PortfolioParams, run_backtest
from ..config.override import set_by_dotted_key
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
    report = _run_generic_grid(run_config, strategy_name, params, grid, progress=progress)
    emit_progress(progress, "准备参数搜索报告输出")
    return RunResult(
        task_type="grid_search",
        name=run_config.task_name,
        status="success",
        summary=report,
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "grid_search", as_of=backtest.get("to_date"), strategy=strategy_name),
    )


def _run_generic_grid(
    run_config: LoadedRunConfig,
    strategy_name: str,
    base_params: BacktestParams,
    grid: dict[str, object],
    *,
    progress: ProgressCallback | None,
) -> dict[str, object]:
    keys = [str(key) for key, value in grid.items() if isinstance(value, list)]
    values = [list(grid[key]) for key in keys]
    combinations = list(product(*values)) if keys else [()]
    rows: list[dict[str, object]] = []
    for idx, combo in enumerate(combinations, start=1):
        combo_map = {k: v for k, v in zip(keys, combo, strict=True)}
        emit_progress(progress, f"参数搜索进度：第 {idx} / {len(combinations)} 组，当前参数：" + ", ".join(f"{k}={v}" for k, v in combo_map.items()))
        report = run_backtest(
            run_config.app_config,
            strategy_name,
            _params_from_combo(base_params, combo_map),
            progress=progress,
            progress_prefix=f"参数组 {idx}/{len(combinations)} 回测进度",
        )
        row = {
            **combo_map,
            "min_score": combo_map.get("strategy.min_score", base_params.min_score),
            "min_amount_ma20": combo_map.get("strategy.min_amount_ma20", base_params.min_amount_ma20),
            "top": combo_map.get("backtest.top", base_params.top),
            "hold_days": combo_map.get("backtest.hold_days", base_params.hold_days),
            "total_return": report.total_return,
            "annual_return": report.annual_return,
            "max_drawdown": report.max_drawdown,
            "win_rate": report.win_rate,
            "turnover": report.turnover,
            "period_count": report.period_count,
            "empty_period_count": report.empty_period_count,
            "research_score": round(report.annual_return - abs(report.max_drawdown) + report.win_rate * 0.1, 6),
        }
        rows.append(row)
    rows.sort(key=lambda item: float(item.get("research_score") or 0.0), reverse=True)
    return {
        "schema_version": "parameter-scan-v2",
        "strategy_name": strategy_name,
        "params": base_params.to_dict(),
        "rows": rows,
    }


def _params_from_combo(base: BacktestParams, combo: dict[str, object]) -> BacktestParams:
    model = {
        "strategy": {
            "min_score": base.min_score,
            "min_amount_ma20": base.min_amount_ma20,
        },
        "backtest": {
            "top": base.top,
            "hold_days": base.hold_days,
        },
        "exit_rules": {"technical": {}},
    }
    for key, value in combo.items():
        set_by_dotted_key(model, key, value)
    strategy = model.get("strategy", {})
    bt = model.get("backtest", {})
    tech = (model.get("exit_rules") or {}).get("technical") if isinstance(model.get("exit_rules"), dict) else {}
    portfolio = base.portfolio or PortfolioParams()
    if isinstance(tech, dict):
        portfolio = PortfolioParams(
            initial_cash=portfolio.initial_cash,
            max_positions=portfolio.max_positions,
            stop_loss_pct=portfolio.stop_loss_pct,
            take_profit_pct=portfolio.take_profit_pct,
            atr_proxy_pct=portfolio.atr_proxy_pct,
            stop_loss_atr=float(tech.get("stop_loss_atr")) if tech.get("stop_loss_atr") is not None else portfolio.stop_loss_atr,
            take_profit_atr=float(tech.get("take_profit_atr")) if tech.get("take_profit_atr") is not None else portfolio.take_profit_atr,
            stop_loss_ma20=bool(tech.get("stop_loss_ma20", portfolio.stop_loss_ma20)),
            momentum_turn_negative=bool(tech.get("momentum_turn_negative", portfolio.momentum_turn_negative)),
            max_hold_days=portfolio.max_hold_days,
            margin_rate=portfolio.margin_rate,
        )
    return BacktestParams(
        from_date=base.from_date,
        to_date=base.to_date,
        top=int(bt.get("top", base.top)),
        hold_days=int(bt.get("hold_days", base.hold_days)),
        fee_rate=base.fee_rate,
        slippage=base.slippage,
        market=base.market,
        candidate_type=base.candidate_type,
        min_score=float(strategy.get("min_score")) if strategy.get("min_score") is not None else base.min_score,
        min_amount_ma20=float(strategy.get("min_amount_ma20")) if strategy.get("min_amount_ma20") is not None else base.min_amount_ma20,
        portfolio=portfolio,
        rolling=base.rolling,
    )
