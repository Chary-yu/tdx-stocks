from __future__ import annotations

from collections.abc import Mapping

from ..config.schema import CORE_EXECUTION_SECTIONS, UNSUPPORTED_FEATURE_RULES
from .errors import InvalidRunConfigError

SUPPORTED_TASK_TYPES = {"daily", "signal", "backtest", "grid_search", "portfolio", "rebalance"}
AUXILIARY_SECTIONS = {
    "macro_filter",
    "event_calendar",
    "risk_management",
    "stop_loss",
    "order_execution",
    "pre_filter",
    "alerts",
    "logging",
    "risk_scenario",
}

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
    "exit_rules",
    "signal",
    "diversity_check",
    *AUXILIARY_SECTIONS,
}

_SECTION_ALLOWED = {
    "task": {"type", "name"},
    "data": {"as_of"},
    "strategies": {"enabled", "limit", "min_score", "candidate_type", "market"},
    "consensus": {"enabled", "min_hit", "limit", "advanced"},
    "signal": {"decay"},
    "diversity_check": {"enabled", "max_correlation_before_warning"},
    "portfolio": {"enabled", "source", "top", "weighting", "max_weight", "min_weight", "max_risk_score", "exclude_risk_tags", "market", "capital", "max_adv_participation", "max_liquidation_days", "market_regime_enabled", "max_sector_weight", "weighting_hybrid", "regime", "attribution", "override"},
    "rebalance": {"enabled", "current_holdings", "min_trade_weight", "max_turnover", "require_risk_filtered_target", "reject_unfiltered_target", "target_source", "cost_model"},
    "exit_rules": {"enabled", "technical", "max_hold", "signal_exit"},
    "strategy": {"name", "limit", "min_score", "min_amount_ma20", "market", "candidate_type"},
    "backtest": {"from_date", "to_date", "top", "hold_days", "rolling", "fee_rate", "slippage", "fee_bps", "slippage_bps", "market", "candidate_type", "min_score", "min_amount_ma20"},
    "grid": None,
    "output": {"save", "dir", "formats"},
    "daily": {"enabled_strategies", "strategy_limit", "strategy_min_score", "consensus_min_hit", "consensus_limit", "portfolio_top", "portfolio_weighting", "portfolio_max_weight", "exclude_risk_tags"},
    "macro_filter": None,
    "event_calendar": None,
    "risk_management": None,
    "stop_loss": None,
    "order_execution": None,
    "pre_filter": None,
    "alerts": None,
    "logging": None,
    "risk_scenario": None,
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
    "daily": {"task", "data", "strategies", "consensus", "signal", "diversity_check", "portfolio", "rebalance", "output", "paths", "build", "factors", "daily", "exit_rules", *AUXILIARY_SECTIONS},
    "signal": {"task", "data", "strategies", "consensus", "signal", "diversity_check", "output", "paths", "build", "factors", "daily", *AUXILIARY_SECTIONS},
    "backtest": {"task", "strategy", "backtest", "exit_rules", "output", "paths", "build", "factors", "daily", *AUXILIARY_SECTIONS},
    "grid_search": {"task", "strategy", "backtest", "grid", "exit_rules", "output", "paths", "build", "factors", "daily", *AUXILIARY_SECTIONS},
    "portfolio": {"task", "portfolio", "output", "paths", "build", "factors", "daily", *AUXILIARY_SECTIONS},
    "rebalance": {"task", "portfolio", "rebalance", "output", "paths", "build", "factors", "daily", *AUXILIARY_SECTIONS},
}


def validate_run_config(data: Mapping[str, object]) -> tuple[str, str, list[str]]:
    warnings: list[str] = []
    unknown_top = sorted(key for key in data.keys() if key not in _TOP_LEVEL_ALLOWED)
    if unknown_top:
        warnings.append(f"ignored unknown top-level section(s): {', '.join(unknown_top)}")
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
        warnings.append(f"ignored unsupported section(s) for task.type={task_type!r}: {', '.join(unknown_type_sections)}")
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
            if section in CORE_EXECUTION_SECTIONS:
                raise InvalidRunConfigError(
                    f"Invalid config: unsupported core key(s) in [{section}]: {', '.join(unknown)}"
                )
            warnings.append(f"ignored unsupported key(s) in [{section}]: {', '.join(unknown)}")
    for (section, key), values in UNSUPPORTED_FEATURE_RULES.items():
        node = data.get(section)
        if isinstance(node, Mapping):
            value = str(node.get(key) or "")
            if value in values:
                warnings.append(f"unsupported_feature: [{section}].{key}={value}")
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
    return task_type, task_name, warnings
