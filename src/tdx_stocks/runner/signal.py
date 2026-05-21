from __future__ import annotations

from datetime import date

from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
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
    as_of_value = (data.get("data") or {}).get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else date.fromisoformat(str(as_of_value))
    names = list(strategies.get("enabled") or [])
    emit_progress(progress, "比较策略信号")
    compare = compare_strategies(run_config.app_config, names, as_of=as_of)
    emit_progress(progress, "生成共振股票")
    consensus_report = build_consensus(run_config.app_config, names, as_of=as_of, min_hit=int(consensus.get("min_hit") or 2))
    emit_progress(progress, "准备信号报告输出")
    return RunResult(
        task_type="signal",
        name=run_config.task_name,
        status="success",
        summary={
            "compare": compare.to_dict(),
            "consensus": consensus_report.to_dict(),
        },
        outputs=run_report_outputs(run_config.app_config.paths.data_root, "signal", as_of=resolve_report_as_of(run_config.app_config, as_of_value)),
    )
