from __future__ import annotations

from datetime import date

from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
from .config import LoadedRunConfig
from .models import RunResult


def run_signal_task(run_config: LoadedRunConfig, *, dry_run: bool = False) -> RunResult:
    data = run_config.config
    strategies = data.get("strategies") or {}
    consensus = data.get("consensus") or {}
    as_of_value = (data.get("data") or {}).get("as_of") or "latest"
    as_of = None if as_of_value == "latest" else date.fromisoformat(str(as_of_value))
    names = list(strategies.get("enabled") or [])
    compare = compare_strategies(run_config.app_config, names, as_of=as_of)
    consensus_report = build_consensus(run_config.app_config, names, as_of=as_of, min_hit=int(consensus.get("min_hit") or 2))
    return RunResult(
        task_type="signal",
        name=run_config.task_name,
        status="success",
        summary={
            "compare": compare.to_dict(),
            "consensus": consensus_report.to_dict(),
        },
    )
