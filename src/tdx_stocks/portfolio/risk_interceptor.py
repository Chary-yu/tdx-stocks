from __future__ import annotations

from typing import Any

from ..risk.event_calendar import apply_event_calendar


def apply_risk_interceptors(
    candidates: list[dict[str, Any]],
    *,
    exclude_risk_tags: tuple[str, ...],
    event_calendar_cfg: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    filtered: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    exclude = set(exclude_risk_tags)
    for item in candidates:
        tags = {str(x) for x in (item.get("tags") or [])} | {str(x) for x in (item.get("risk_flags") or [])}
        if exclude & tags:
            logs.append(
                {
                    "symbol": item.get("symbol"),
                    "market": item.get("market"),
                    "action": "reject",
                    "reason": "命中 exclude_risk_tags",
                    "tags": sorted(exclude & tags),
                }
            )
            continue
        event = apply_event_calendar(item, event_calendar_cfg)
        if event.action == "reject":
            logs.append({"symbol": item.get("symbol"), "market": item.get("market"), **event.to_dict()})
            continue
        filtered.append(item)
    return filtered, logs
