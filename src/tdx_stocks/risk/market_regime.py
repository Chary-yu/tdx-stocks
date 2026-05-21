from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketRegimeResult:
    status: str
    action: str
    reason: str
    required_missing: list[str]
    cash_floor: float | None = None
    position_limit: float | None = None
    sector_neutral_required: bool | None = None
    indicators: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "reason": self.reason,
            "required_missing": list(self.required_missing),
            "cash_floor": self.cash_floor,
            "position_limit": self.position_limit,
            "sector_neutral_required": self.sector_neutral_required,
            "indicators": dict(self.indicators or {}),
        }


def evaluate_market_regime(config: dict[str, Any] | None = None) -> MarketRegimeResult:
    cfg = config or {}
    enabled = bool(cfg.get("enabled", False))
    if not enabled:
        return MarketRegimeResult(status="neutral", action="allow_open", reason="macro_filter.disabled", required_missing=[], indicators={})

    indicator_modes = cfg.get("indicators") if isinstance(cfg.get("indicators"), dict) else {}
    rules = cfg.get("rules") if isinstance(cfg.get("rules"), dict) else {}
    impact = cfg.get("impact") if isinstance(cfg.get("impact"), dict) else {}
    values = _indicator_values(cfg)
    for name, mode in indicator_modes.items():
        text_mode = str(mode).lower()
        if text_mode not in {"required", "optional", "disabled"} and mode not in (None, ""):
            values[str(name)] = mode

    required = [name for name, mode in indicator_modes.items() if str(mode).lower() == "required"]
    required.extend(str(name) for name in (cfg.get("required") or []) if str(name) not in required)
    missing = [str(name) for name in required if values.get(str(name)) in (None, "")]
    if missing:
        fallback = str(cfg.get("missing_action") or "pause_open")
        return MarketRegimeResult(
            status="not_available",
            action=fallback,
            reason="required 指标缺失",
            required_missing=missing,
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
            indicators=values,
        )

    explicit_status = str(cfg.get("status") or values.get("status") or "").lower()
    if explicit_status in {"bull", "bear", "neutral", "not_available"}:
        status = explicit_status
    else:
        status = _infer_status(values, rules)

    if status == "not_available":
        return MarketRegimeResult(status="not_available", action="pause_open", reason="市场指标不可用", required_missing=missing, indicators=values)

    bear_trade_allowed = bool(rules.get("bear_trade_allowed", False))
    if status == "bear" and not bear_trade_allowed:
        return MarketRegimeResult(
            status="bear",
            action="pause_open",
            reason="熊市且不允许开仓",
            required_missing=[],
            position_limit=_float_or_none(impact.get("position_limit_bear")),
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
            indicators=values,
        )

    if status == "neutral":
        return MarketRegimeResult(
            status="neutral",
            action="reduce_position",
            reason="中性市场，降低仓位",
            required_missing=[],
            cash_floor=_float_or_none(rules.get("neutral_cash_floor")),
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
            indicators=values,
        )

    if status == "bear":
        return MarketRegimeResult(
            status="bear",
            action="reduce_position",
            reason="熊市允许交易但收缩风险",
            required_missing=[],
            position_limit=_float_or_none(impact.get("position_limit_bear")),
            sector_neutral_required=bool(impact.get("sector_neutral_required", False)),
            indicators=values,
        )

    return MarketRegimeResult(status="bull", action="allow_open", reason="牛市可开仓", required_missing=[], indicators=values)


def _indicator_values(cfg: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in ("values", "observed", "observed_indicators", "indicator_values"):
        node = cfg.get(key)
        if isinstance(node, dict):
            values.update(node)
    # Backward compatibility: allow actual values directly at top level.
    for key in ("market_breadth", "index_ma20", "index_ma60", "credit_cycle", "rate_trend", "status"):
        value = cfg.get(key)
        if value not in (None, ""):
            values[key] = value
    return values


def _infer_status(values: dict[str, Any], rules: dict[str, Any]) -> str:
    required_exprs = rules.get("bull_trade_required")
    if isinstance(required_exprs, str):
        required_exprs = [required_exprs]
    if isinstance(required_exprs, list) and required_exprs:
        results = [_eval_condition(str(expr), values) for expr in required_exprs]
        if all(result is True for result in results):
            return "bull"
        if any(result is None for result in results):
            return "not_available"
        return "bear"

    breadth = values.get("market_breadth")
    try:
        breadth_value = float(breadth)
        if breadth_value >= 0.6:
            return "bull"
        if breadth_value <= 0.4:
            return "bear"
        return "neutral"
    except (TypeError, ValueError):
        text = str(breadth or "").lower()
        if text in {"bull", "bear", "neutral"}:
            return text
    return "not_available"


_COND_RE = re.compile(r"^\s*([A-Za-z_][\w.]*)\s*(>=|<=|==|!=|>|<)\s*['\"]?([^'\"]+)['\"]?\s*$")
_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
    "!=": operator.ne,
}


def _eval_condition(expr: str, values: dict[str, Any]) -> bool | None:
    match = _COND_RE.match(expr)
    if not match:
        return None
    name, op, rhs_raw = match.groups()
    lhs = values.get(name)
    if lhs in (None, ""):
        return None
    op_fn = _OPS[op]
    try:
        return bool(op_fn(float(lhs), float(rhs_raw)))
    except (TypeError, ValueError):
        return bool(op_fn(str(lhs), str(rhs_raw)))


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
