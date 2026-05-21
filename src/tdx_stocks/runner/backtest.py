from __future__ import annotations

from typing import Any

from ..backtest import BacktestParams, PortfolioParams, run_backtest
from ..pipeline import parse_iso_date
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress


DEFAULT_FEE_RATE = 0.0003
DEFAULT_SLIPPAGE = 0.0005


def run_backtest_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取回测任务配置")
    data = run_config.config
    strategy = data.get("strategy") or {}
    backtest = data.get("backtest") or {}

    def _pick(value, fallback):
        return fallback if value is None else value

    portfolio_params = build_backtest_portfolio_params(data, fallback_hold_days=int(_pick(backtest.get("hold_days"), 5)))
    params = BacktestParams(
        from_date=parse_iso_date(backtest.get("from_date")),
        to_date=parse_iso_date(backtest.get("to_date")),
        top=int(_pick(backtest.get("top"), _pick(strategy.get("limit"), 20))),
        hold_days=int(_pick(backtest.get("hold_days"), portfolio_params.max_hold_days or 5)),
        fee_rate=float(_pick(backtest.get("fee_rate"), (backtest.get("fee_bps") / 10_000 if backtest.get("fee_bps") is not None else DEFAULT_FEE_RATE))),
        slippage=float(_pick(backtest.get("slippage"), (backtest.get("slippage_bps") / 10_000 if backtest.get("slippage_bps") is not None else DEFAULT_SLIPPAGE))),
        market=backtest.get("market"),
        candidate_type=backtest.get("candidate_type"),
        min_score=_pick(backtest.get("min_score"), strategy.get("min_score")),
        min_amount_ma20=_pick(backtest.get("min_amount_ma20"), strategy.get("min_amount_ma20")),
        portfolio=portfolio_params,
        rolling=bool(backtest.get("rolling", False)),
    )
    emit_progress(progress, "执行策略回测")
    strategy_name = str(strategy.get("name") or data.get("strategy_name") or "trend-strength")
    report = run_backtest(run_config.app_config, strategy_name, params, progress=progress)
    emit_progress(progress, "准备回测报告输出")
    return RunResult(
        task_type="backtest",
        name=run_config.task_name,
        status="success",
        summary=report.to_dict(),
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "backtest", as_of=backtest.get("to_date"), strategy=strategy_name),
    )


def build_backtest_portfolio_params(data: dict[str, Any], *, fallback_hold_days: int) -> PortfolioParams:
    exit_rules = data.get("exit_rules") if isinstance(data.get("exit_rules"), dict) else {}
    technical = exit_rules.get("technical") if isinstance(exit_rules.get("technical"), dict) else {}
    max_hold = exit_rules.get("max_hold") if isinstance(exit_rules.get("max_hold"), dict) else {}
    signal_exit = exit_rules.get("signal_exit") if isinstance(exit_rules.get("signal_exit"), dict) else {}
    stop_loss = data.get("stop_loss") if isinstance(data.get("stop_loss"), dict) else {}
    stop_loss_method = str(stop_loss.get("method") or "").lower()
    adaptive = stop_loss.get("volatility_adaptive") if isinstance(stop_loss.get("volatility_adaptive"), dict) else {}
    chandelier = stop_loss.get("chandelier") if isinstance(stop_loss.get("chandelier"), dict) else {}
    trailing = stop_loss.get("trailing") if isinstance(stop_loss.get("trailing"), dict) else {}
    stop_loss_atr = _optional_float(technical.get("stop_loss_atr"))
    take_profit_atr = _optional_float(technical.get("take_profit_atr"))
    if stop_loss_atr is None and stop_loss_method in {"fixed_atr", "volatility_adaptive"}:
        stop_loss_atr = _optional_float(adaptive.get("base_multiplier"))
    if stop_loss_atr is None and stop_loss_method == "chandelier":
        stop_loss_atr = _optional_float(chandelier.get("multiplier"))
    enabled = bool(exit_rules.get("enabled", bool(exit_rules)))
    unsupported = ["parabolic_sar"] if stop_loss_method == "parabolic_sar" else []
    return PortfolioParams(
        max_positions=int((data.get("backtest") or {}).get("top") or 5),
        stop_loss_pct=None if enabled else 0.08,
        hard_stop_loss_pct=0.12,
        take_profit_pct=None,
        atr_proxy_pct=0.02,
        stop_loss_atr=stop_loss_atr,
        take_profit_atr=take_profit_atr,
        stop_loss_ma20=bool(technical.get("stop_loss_ma20", False)),
        momentum_turn_negative=bool(technical.get("momentum_turn_negative", False)),
        min_hold_days=int(max_hold.get("min_days") or 1),
        exit_when_score_below=_optional_float(signal_exit.get("exit_when_score_below")),
        max_hold_days=int(max_hold.get("max_days") or fallback_hold_days),
        trailing_pullback_pct=_optional_float(trailing.get("pullback_pct")) if bool(trailing.get("enabled", False)) else None,
        chandelier_period=int(chandelier.get("period")) if chandelier.get("period") is not None else None,
        chandelier_multiplier=_optional_float(chandelier.get("multiplier")),
        volatility_high_threshold=_optional_float(adaptive.get("high_volatility_threshold")),
        volatility_low_threshold=_optional_float(adaptive.get("low_volatility_threshold")),
        volatility_high_multiplier=_optional_float(adaptive.get("high_volatility_multiplier")),
        volatility_low_multiplier=_optional_float(adaptive.get("low_volatility_multiplier")),
        stop_loss_method=stop_loss_method or None,
        unsupported_features=unsupported,
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
