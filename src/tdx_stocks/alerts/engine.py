
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..events.types import Event


@dataclass(frozen=True)
class AlertDecision:
    event_type: str
    triggered: bool
    channel: str
    reason: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "triggered": self.triggered,
            "channel": self.channel,
            "reason": self.reason,
            "payload": dict(self.payload),
        }


def evaluate_alerts(events: list[Event], cfg: dict[str, Any] | None = None) -> list[AlertDecision]:
    config = cfg or {}
    alerts = config.get("alerts") if isinstance(config.get("alerts"), dict) else config
    if alerts and not bool(alerts.get("enabled", True)):
        return []
    channels = alerts.get("channels") if isinstance(alerts.get("channels"), list) else ["console"]
    conditions = alerts.get("conditions") if isinstance(alerts.get("conditions"), dict) else {}
    decisions: list[AlertDecision] = []
    for event in events:
        triggered, reason = _event_matches(event, conditions)
        for channel in channels:
            decisions.append(AlertDecision(event.event_type, triggered, str(channel), reason, event.payload))
    return decisions


def emit_console_alerts(decisions: list[AlertDecision]) -> None:
    for item in decisions:
        if item.triggered and item.channel == "console":
            print(f"[ALERT] {item.event_type}: {item.reason} {item.payload}")


def validate_alert_config(cfg: dict[str, Any] | None = None) -> list[str]:
    alerts = cfg or {}
    warnings: list[str] = []
    channels = alerts.get("channels") if isinstance(alerts.get("channels"), list) else []
    email = alerts.get("email") if isinstance(alerts.get("email"), dict) else {}
    if "email" in channels:
        for key in ("smtp_host", "smtp_port", "from_addr", "to_addrs"):
            if email.get(key) in (None, "", []):
                warnings.append(f"alerts.email.{key} missing while email channel is enabled")
    return warnings


def _event_matches(event: Event, conditions: dict[str, Any]) -> tuple[bool, str]:
    et = event.event_type
    payload = event.payload or {}
    if et in {"DATA_QUALITY_ERROR", "MACRO_PAUSE_OPEN", "REBALANCE_BUY_BLOCKED", "RISK_INTERCEPTED"}:
        return True, "核心风控事件触发"
    if et == "STOP_LOSS_TRIGGERED":
        return bool(conditions.get("stop_loss_triggered", True)), "止损事件触发"
    if et == "TURNOVER_EXCEEDED":
        threshold = _float(conditions.get("turnover_threshold"), 0.50)
        value = _float(payload.get("turnover") or payload.get("value"), 0.0)
        return value >= threshold, f"换手率 {value:.2%} {'超过' if value >= threshold else '未超过'} 阈值 {threshold:.2%}"
    if et == "SCORE_CHANGED":
        threshold = _float(conditions.get("score_change_threshold"), 30.0)
        value = abs(_float(payload.get("score_delta"), 0.0))
        return value >= threshold, f"评分变化 {value:.2f} {'超过' if value >= threshold else '未超过'} 阈值 {threshold:.2f}"
    if et == "MAJOR_EVENT_OCCURRED":
        return bool(conditions.get("major_event_occurred", True)), "重大事件触发"
    return False, "事件未匹配告警条件"


def _float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
