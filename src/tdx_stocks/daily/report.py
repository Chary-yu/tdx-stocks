from __future__ import annotations

from typing import Any

from .models import DailyRunReport
from ..reports.renderers import render_daily_markdown as _render_daily_markdown


def render_daily_json(report: DailyRunReport) -> dict[str, Any]:
    return report.to_dict()


def render_daily_markdown(report: DailyRunReport) -> str:
    return _render_daily_markdown(report)
