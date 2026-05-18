from __future__ import annotations

import json
from typing import Any

from .models import DailyRunReport


def render_daily_json(report: DailyRunReport) -> dict[str, Any]:
    return report.to_dict()


def render_daily_markdown(report: DailyRunReport) -> str:
    payload = report.to_dict()
    lines: list[str] = []
    lines.append("# TDX Stocks Daily Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- As of: {payload.get('as_of')}")
    lines.append(f"- Status: {payload.get('status')}")
    lines.append(f"- Data run id: {payload.get('data_run_id')}")
    lines.append("")
    lines.append("## Data Quality")
    lines.append("")
    lines.append(json.dumps(payload.get("data_quality"), ensure_ascii=False, indent=2, default=str))
    lines.append("")
    lines.append("## Strategy Summary")
    lines.append("")
    lines.append(json.dumps(payload.get("strategy_summary"), ensure_ascii=False, indent=2, default=str))
    lines.append("")
    lines.append("## Consensus")
    lines.append("")
    lines.append(json.dumps(payload.get("consensus_summary"), ensure_ascii=False, indent=2, default=str))
    lines.append("")
    lines.append("## Portfolio")
    lines.append("")
    lines.append(json.dumps(payload.get("portfolio_summary"), ensure_ascii=False, indent=2, default=str))
    lines.append("")
    lines.append("## Rebalance Plan")
    lines.append("")
    lines.append(json.dumps(payload.get("rebalance_summary"), ensure_ascii=False, indent=2, default=str))
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    lines.extend(f"- {item}" for item in payload.get("warnings") or ["None"])
    lines.append("")
    lines.append("## Errors")
    lines.append("")
    lines.extend(f"- {item}" for item in payload.get("errors") or ["None"])
    lines.append("")
    lines.append("## Output Files")
    lines.append("")
    lines.append(json.dumps(payload.get("outputs"), ensure_ascii=False, indent=2, default=str))
    return "\n".join(lines).rstrip() + "\n"
