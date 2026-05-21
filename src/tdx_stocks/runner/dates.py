from __future__ import annotations

from datetime import date
from typing import Any

from ..config import AppConfig
from ..query import open_query_context


def resolve_report_as_of(config: AppConfig, value: Any = None) -> Any:
    """Resolve ``latest`` to the latest factor trade date for report filenames."""
    if value not in (None, "", "latest"):
        return value
    try:
        ctx = open_query_context(config)
        try:
            row = ctx.con.execute("SELECT max(trade_date) FROM factors").fetchone()
            if row and row[0] is not None:
                resolved = row[0]
                return resolved.isoformat() if isinstance(resolved, date) else resolved
        finally:
            ctx.close()
    except Exception:
        return value
    return value
