from __future__ import annotations

from datetime import date

from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
from ..risk.pre_filter import apply_pre_filter
from ..events.bus import publish
from ..events.types import Event
from .config import LoadedRunConfig
from .models import RunResult
from ..reports.paths import run_report_outputs
from ..progress import ProgressCallback, emit_progress
from .dates import resolve_report_as_of


def run_signal_task(run_config: LoadedRunConfig, *, dry_run: bool = False, progress: ProgressCallback | None = None) -> RunResult:
    emit_progress(progress, "读取信号任务配置")
    data = run_config.config
    strategies = data.get("strategies") or {}
    consensus = data.get("consensus") or {}
    consensus_advanced = consensus.get("advanced") if isinstance(consensus.get("advanced"), dict) else {}
    pre_filter_cfg = data.get("pre_filter") if isinstance(data.get("pre_filter"), dict) else {}
    as_of_value = (data.get("data") or {}).get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else date.fromisoformat(str(as_of_value))
    names = list(strategies.get("enabled") or [])
    emit_progress(progress, "比较策略信号")
    compare = compare_strategies(run_config.app_config, names, as_of=as_of)
    emit_progress(progress, "生成共振股票")
    min_hit = int(consensus_advanced.get("min_hit") or consensus.get("min_hit") or 2)
    method = str(consensus_advanced.get("method") or "simple_majority")
    require_different_types = bool(consensus_advanced.get("require_different_types", False))
    decay_cfg = data.get("signal", {}).get("decay") if isinstance(data.get("signal"), dict) else {}
    if not isinstance(decay_cfg, dict):
        decay_cfg = {}
    consensus_report = build_consensus(
        run_config.app_config,
        names,
        as_of=as_of,
        min_hit=min_hit,
        method=method,
        require_different_types=require_different_types,
        decay_enabled=bool(decay_cfg.get("enabled", False)),
        decay_half_life_days=float(decay_cfg.get("half_life_days") or 5.0),
        decay_min_weight=float(decay_cfg.get("min_weight") or 0.10),
    )
    pre_filter_logs: list[dict[str, object]] = []
    filtered_rows = []
    for row in consensus_report.rows:
        row_dict = row.to_dict()
        merged = {
            "market": row_dict.get("market"),
            "symbol": row_dict.get("symbol"),
            "risk_flags": row_dict.get("risk_flags"),
            "tags": row_dict.get("tags"),
            "score": row_dict.get("avg_score"),
        }
        result = apply_pre_filter(merged, pre_filter_cfg)
        if result.passed:
            risk_flags = set(str(v) for v in (row_dict.get("risk_flags") or []))
            if risk_flags & {"near_20d_high", "rsi_high", "ret_5_strong", "high_volatility", "mild_volatility"}:
                publish(Event.create("SIGNAL_DOWNGRADED_TO_WATCHLIST", {"market": row_dict.get("market"), "symbol": row_dict.get("symbol"), "risk_flags": sorted(risk_flags)}))
            filtered_rows.append(row)
        else:
            pre_filter_logs.append({"market": row.market, "symbol": row.symbol, "reasons": result.reasons, "action": "filtered_out"})
    consensus_dict = consensus_report.to_dict()
    consensus_dict["rows"] = [row.to_dict() for row in filtered_rows]
    consensus_dict["pre_filter_log"] = pre_filter_logs
    consensus_dict["method"] = method
    consensus_dict["require_different_types"] = require_different_types
    emit_progress(progress, "准备信号报告输出")
    return RunResult(
        task_type="signal",
        name=run_config.task_name,
        status="success",
        summary={
            "compare": compare.to_dict(),
            "consensus": consensus_dict,
        },
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "signal", as_of=resolve_report_as_of(run_config.app_config, as_of_value)),
    )
