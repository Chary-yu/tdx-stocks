from __future__ import annotations

from collections.abc import Mapping
from typing import Any

AUX_CONFIG_ALIASES: dict[str, list[str]] = {
    "pre_filter": ["pre_filter.toml", "screening_pre_filter.toml"],
    "stop_loss": ["stop_loss.toml", "stop_loss_dynamic.toml"],
    "macro_filter": ["macro_filter.toml"],
    "event_calendar": ["event_calendar.toml"],
    "risk_management": ["risk_management.toml"],
    "order_execution": ["order_execution.toml"],
    "alerts": ["alerts.toml"],
    "logging": ["logging.toml"],
    "risk_scenario": ["risk_scenario.toml"],
}

SECTION_EXTRACTORS: dict[str, str] = {
    "macro_filter": "macro_filter",
    "event_calendar": "event_calendar",
    "risk_management": "risk",
    "pre_filter": "pre_filter",
    "stop_loss": "stop_loss",
    "order_execution": "execution",
    "alerts": "alerts",
    "logging": "logging",
    "risk_scenario": "risk_scenario",
}


def extract_aux_section_payload(section: str, data: Mapping[str, Any], *, extractor_key: str) -> dict[str, Any]:
    root = dict(data)
    node = root.get(extractor_key)
    if isinstance(node, Mapping):
        return dict(node)
    # fallback: keep root when extractor key is absent to avoid data loss
    # and to keep backward compatibility for flat auxiliary files.
    return root
