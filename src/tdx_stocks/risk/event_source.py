
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Any

from ..config import AppConfig


def load_event_calendar_rows(config: AppConfig, *, path: Path | None = None) -> list[dict[str, Any]]:
    data_root = config.paths.data_root
    candidates = [path] if path else [data_root / "events" / "calendar.csv", data_root / "event_calendar.csv"]
    for candidate in candidates:
        if candidate and candidate.exists():
            with candidate.open("r", encoding="utf-8-sig", newline="") as handle:
                return [dict(row) for row in csv.DictReader(handle)]
    return []


def attach_events(candidates: list[dict[str, Any]], events: list[dict[str, Any]], *, as_of: date | str | None = None) -> list[dict[str, Any]]:
    if not events:
        return list(candidates)
    index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in events:
        key = (str(row.get("market") or "").lower(), str(row.get("symbol") or row.get("code") or ""))
        if key[1]:
            index.setdefault(key, []).append(row)
    out: list[dict[str, Any]] = []
    for item in candidates:
        key = (str(item.get("market") or "").lower(), str(item.get("symbol") or item.get("code") or ""))
        matches = index.get(key) or []
        if not matches:
            out.append(item)
            continue
        row = _nearest_event(matches, as_of)
        merged = dict(item)
        merged.setdefault("event_type", row.get("event_type") or row.get("type"))
        merged.setdefault("event_date", row.get("event_date") or row.get("date"))
        merged.setdefault("event_description", row.get("description"))
        if as_of is not None:
            merged.setdefault("as_of", str(as_of)[:10])
        out.append(merged)
    return out


def _nearest_event(rows: list[dict[str, Any]], as_of: date | str | None) -> dict[str, Any]:
    if as_of in (None, ""):
        return rows[0]
    try:
        ref = date.fromisoformat(str(as_of)[:10])
    except ValueError:
        return rows[0]
    def distance(row: dict[str, Any]) -> int:
        raw = row.get("event_date") or row.get("date")
        try:
            return abs((date.fromisoformat(str(raw)[:10]) - ref).days)
        except Exception:
            return 10_000
    return sorted(rows, key=distance)[0]
