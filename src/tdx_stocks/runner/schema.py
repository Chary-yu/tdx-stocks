from __future__ import annotations

from collections.abc import Mapping

from .errors import InvalidRunConfigError

SUPPORTED_TASK_TYPES = {"daily", "signal", "backtest", "grid_search", "portfolio", "rebalance"}

_TOP_LEVEL_ALLOWED = {
    "task",
    "paths",
    "build",
    "factors",
    "daily",
    "strategies",
    "consensus",
    "portfolio",
    "rebalance",
    "strategy",
    "backtest",
    "grid",
    "output",
    "data",
}

_SECTION_ALLOWED = {
    "task": {"type", "name"},
    "data": {"as_of"},
    "strategies": {"enabled", "limit", "min_score", "candidate_type", "market"},
    "consensus": {"enabled", "min_hit", "limit"},
    "portfolio": {"enabled", "source", "top", "weighting", "max_weight", "min_weight", "max_risk_score", "exclude_risk_tags", "market"},
    "rebalance": {"enabled", "current_holdings", "min_trade_weight", "max_turnover"},
    "strategy": {"name", "limit", "min_score", "min_amount_ma20", "market", "candidate_type"},
    "backtest": {"from_date", "to_date", "top", "hold_days", "fee_rate", "slippage", "fee_bps", "slippage_bps", "market", "candidate_type", "min_score", "min_amount_ma20"},
    "grid": None,
    "output": {"save", "dir", "formats"},
    "daily": {"enabled_strategies", "strategy_limit", "strategy_min_score", "consensus_min_hit", "consensus_limit", "portfolio_top", "portfolio_weighting", "portfolio_max_weight", "exclude_risk_tags"},
}

_REQUIRED_BY_TYPE = {
    "daily": set(),
    "signal": set(),
    "backtest": {"backtest", "strategy"},
    "grid_search": {"backtest", "grid", "strategy"},
    "portfolio": {"portfolio"},
    "rebalance": {"portfolio", "rebalance"},
}

_ALLOWED_SECTIONS_BY_TYPE = {
    "daily": {"task", "data", "strategies", "consensus", "portfolio", "rebalance", "output", "paths", "build", "factors", "daily"},
    "signal": {"task", "data", "strategies", "consensus", "output", "paths", "build", "factors", "daily"},
    "backtest": {"task", "strategy", "backtest", "output", "paths", "build", "factors", "daily"},
    "grid_search": {"task", "strategy", "backtest", "grid", "output", "paths", "build", "factors", "daily"},
    "portfolio": {"task", "portfolio", "output", "paths", "build", "factors", "daily"},
    "rebalance": {"task", "portfolio", "rebalance", "output", "paths", "build", "factors", "daily"},
}


def validate_run_config(data: Mapping[str, object]) -> tuple[str, str, list[str]]:
    unknown_top = sorted(key for key in data.keys() if key not in _TOP_LEVEL_ALLOWED)
    if unknown_top:
        raise InvalidRunConfigError(
            f"Invalid config: unknown top-level section(s): {', '.join(unknown_top)}.\n"
            f"Use only: {', '.join(sorted(_TOP_LEVEL_ALLOWED))}"
        )
    task = data.get("task")
    if not isinstance(task, Mapping):
        raise InvalidRunConfigError("Invalid config: [task].type is required.\nUse:\n  [task]\n  type = \"daily\"")
    task_type = str(task.get("type") or "").strip()
    if not task_type:
        raise InvalidRunConfigError("Invalid config: [task].type is required.\nUse:\n  type = \"daily\"")
    if task_type not in SUPPORTED_TASK_TYPES:
        raise InvalidRunConfigError(
            f"Invalid config: unsupported task.type={task_type!r}.\n"
            f"Supported values: {', '.join(sorted(SUPPORTED_TASK_TYPES))}"
        )
    task_name = str(task.get("name") or task_type)
    for section in _REQUIRED_BY_TYPE[task_type]:
        if section not in data:
            raise InvalidRunConfigError(
                f"Invalid config: [{section}] is required for task.type={task_type!r}."
            )
    allowed_sections = _ALLOWED_SECTIONS_BY_TYPE[task_type]
    unknown_type_sections = sorted(key for key in data.keys() if key not in allowed_sections and key not in _TOP_LEVEL_ALLOWED)
    if unknown_type_sections:
        raise InvalidRunConfigError(
            f"Invalid config: unsupported section(s) for task.type={task_type!r}: {', '.join(unknown_type_sections)}."
        )
    for section, allowed_keys in _SECTION_ALLOWED.items():
        value = data.get(section)
        if not isinstance(value, Mapping):
            continue
        if allowed_keys is None:
            continue
        unknown = sorted(key for key in value.keys() if key not in allowed_keys)
        if unknown:
            bad = unknown[0]
            replacement = "from_date" if section == "backtest" and bad == "from" else None
            if replacement:
                raise InvalidRunConfigError(
                    f"Invalid config: [{section}].{bad} is not supported.\n\nUse:\n  {replacement} = \"2022-01-01\""
                )
            raise InvalidRunConfigError(
                f"Invalid config: [{section}].{', '.join(unknown)} is not supported."
            )
    if task_type == "rebalance":
        rebalance = data.get("rebalance")
        if isinstance(rebalance, Mapping) and not rebalance.get("current_holdings"):
            raise InvalidRunConfigError(
                "Invalid config: [rebalance].current_holdings is required.\n"
                "Use:\n  current_holdings = \"holdings.csv\""
            )
    if task_type in {"backtest", "grid_search"}:
        backtest = data.get("backtest")
        if isinstance(backtest, Mapping) and "from" in backtest and "from_date" not in backtest:
            raise InvalidRunConfigError(
                "Invalid config: [backtest].from is not supported.\n\nUse:\n  from_date = \"2022-01-01\""
            )
    return task_type, task_name, []
