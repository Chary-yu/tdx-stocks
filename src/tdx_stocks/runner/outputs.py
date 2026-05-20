from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..io_utils import write_json_atomic, write_text_atomic
from ..reports.rendering import save_run_result_markdown
from .config import LoadedRunConfig
from .models import RunResult


def build_run_plan(run_config: LoadedRunConfig) -> dict[str, Any]:
    data = run_config.config
    task = data.get("task") or {}
    task_type = run_config.task_type
    inputs: dict[str, Any] = {}
    outputs: dict[str, Any] = {}
    steps: list[str] = []

    if task_type == "daily":
        daily = data.get("daily") or {}
        strategies = data.get("strategies") or {}
        consensus = data.get("consensus") or {}
        portfolio = data.get("portfolio") or {}
        rebalance = data.get("rebalance") or {}
        inputs = {
            "as_of": (data.get("data") or {}).get("as_of", "latest"),
            "strategies": list(strategies.get("enabled") or daily.get("enabled_strategies") or []),
            "strategy_limit": strategies.get("limit") or daily.get("strategy_limit"),
            "min_score": strategies.get("min_score") or daily.get("strategy_min_score"),
            "min_hit": consensus.get("min_hit") or daily.get("consensus_min_hit"),
            "portfolio_top": portfolio.get("top") or daily.get("portfolio_top"),
            "portfolio_weighting": portfolio.get("weighting") or daily.get("portfolio_weighting"),
            "current_holdings": rebalance.get("current_holdings"),
        }
        outputs = {
            "reports": [
                "reports/daily/latest.json",
                "reports/daily/latest.md",
                "reports/daily/by_date/<as_of>/daily_report.json",
                "reports/daily/by_date/<as_of>/daily_report.md",
                "reports/latest.json",
            ],
        }
        steps = [
            "load latest dataset",
            "run selected strategies",
            "build consensus and portfolio",
            "optionally build rebalance plan",
            "save daily report",
        ]
    elif task_type == "signal":
        strategies = data.get("strategies") or {}
        consensus = data.get("consensus") or {}
        inputs = {
            "as_of": (data.get("data") or {}).get("as_of", "latest"),
            "strategies": list(strategies.get("enabled") or []),
            "min_hit": consensus.get("min_hit") or 2,
        }
        outputs = {"reports": ["reports/latest.json"]}
        steps = ["load latest dataset", "compare strategies", "build consensus"]
    elif task_type == "backtest":
        strategy = data.get("strategy") or {}
        backtest = data.get("backtest") or {}
        inputs = {
            "strategy": strategy.get("name") or data.get("strategy_name") or "trend-strength",
            "from_date": backtest.get("from_date"),
            "to_date": backtest.get("to_date"),
            "top": backtest.get("top") or strategy.get("limit"),
            "hold_days": backtest.get("hold_days"),
        }
        outputs = {"reports": ["reports/latest.json"]}
        steps = ["validate task", "run backtest", "save report"]
    elif task_type == "grid_search":
        strategy = data.get("strategy") or {}
        backtest = data.get("backtest") or {}
        grid = data.get("grid") or {}
        inputs = {
            "strategy": strategy.get("name") or data.get("strategy_name") or "trend-strength",
            "from_date": backtest.get("from_date"),
            "to_date": backtest.get("to_date"),
            "grid_keys": sorted(grid.keys()),
        }
        outputs = {"reports": ["reports/latest.json"]}
        steps = ["validate task", "expand grid", "run backtests", "save report"]
    elif task_type == "portfolio":
        portfolio = data.get("portfolio") or {}
        inputs = {
            "source": portfolio.get("source") or "consensus",
            "top": portfolio.get("top") or 20,
            "weighting": portfolio.get("weighting") or "equal",
            "as_of": (data.get("data") or {}).get("as_of", "latest"),
        }
        outputs = {"reports": ["reports/latest.json"]}
        steps = ["load target source", "build portfolio", "save report"]
    elif task_type == "rebalance":
        portfolio = data.get("portfolio") or {}
        rebalance = data.get("rebalance") or {}
        inputs = {
            "source": portfolio.get("source") or "consensus",
            "current_holdings": rebalance.get("current_holdings"),
            "min_trade_weight": rebalance.get("min_trade_weight"),
            "max_turnover": rebalance.get("max_turnover"),
        }
        outputs = {"reports": ["reports/latest.json"]}
        steps = ["load target portfolio", "load holdings", "build rebalance plan", "save report"]

    return {
        "task": {
            "type": task_type,
            "name": str(task.get("name") or run_config.task_name or task_type),
        },
        "config": run_config.path.as_posix(),
        "base_dir": run_config.base_dir.as_posix(),
        "inputs": inputs,
        "outputs": outputs,
        "steps": steps,
    }


def build_latest_run_report(run_config: LoadedRunConfig, result: RunResult, *, dry_run: bool = False) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    return {
        "last_run": run_config.path.as_posix(),
        "status": result.status,
        "task_type": result.task_type,
        "task_name": result.name,
        "report": result.to_dict(),
        "outputs": result.outputs,
        "warnings": list(result.warnings),
        "errors": list(result.errors),
        "generated_at": now,
        "dry_run": dry_run,
    }


def save_latest_run_report(data_root: Path, document: dict[str, Any]) -> Path:
    report_path = data_root / "reports" / "latest.json"
    write_json_atomic(report_path, document)
    return report_path


def main_report_path(outputs: dict[str, str]) -> Path | None:
    for value in outputs.values():
        if value.endswith(".md"):
            return Path(value)
    for value in outputs.values():
        if value.endswith(".json"):
            return Path(value)
    return None


def load_latest_run_report(data_root: Path) -> dict[str, Any] | None:
    path = data_root / "reports" / "latest.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def render_run_plan(plan: dict[str, Any]) -> str:
    lines = [
        f"Task: {plan['task']['type']}",
        f"Name: {plan['task']['name']}",
        f"Config: {plan['config']}",
        "",
        "Inputs:",
    ]
    for key, value in plan["inputs"].items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("Steps:")
    for step in plan["steps"]:
        lines.append(f"  - {step}")
    lines.append("")
    lines.append("Outputs:")
    for key, value in plan["outputs"].items():
        lines.append(f"  {key}: {', '.join(value) if isinstance(value, list) else value}")
    return "\n".join(lines)


def render_run_result(result: RunResult) -> str:
    return f"{result.task_type}: {result.status}"


def save_run_output(path: Path, result: RunResult, *, json_mode: bool = False) -> None:
    if json_mode:
        write_json_atomic(path, result.to_dict())
        return
    write_text_atomic(path, render_run_result(result) + "\n")


def ensure_run_report_markdown(path: Path, result: RunResult) -> Path:
    return save_run_result_markdown(path, result)
