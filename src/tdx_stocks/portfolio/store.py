from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ..io_utils import write_json_atomic, write_text_atomic
from .models import PortfolioBacktestReport, PortfolioReport, RebalancePlan


def portfolio_reports_root(data_root: Path) -> Path:
    return data_root / "report_payloads" / "portfolios"


def portfolio_backtests_root(data_root: Path) -> Path:
    return portfolio_reports_root(data_root) / "backtests"


def rebalance_root(data_root: Path) -> Path:
    return data_root / "report_payloads" / "rebalance"


def latest_portfolio_path(data_root: Path) -> Path:
    return portfolio_reports_root(data_root) / "latest.json"


def portfolio_by_date_path(data_root: Path, as_of: date) -> Path:
    return portfolio_reports_root(data_root) / "by_date" / as_of.isoformat() / "portfolio.json"


def portfolio_backtest_path(data_root: Path, as_of: date) -> Path:
    return portfolio_backtests_root(data_root) / as_of.isoformat() / "portfolio_backtest.json"


def rebalance_plan_json_path(data_root: Path, as_of: date) -> Path:
    return rebalance_root(data_root) / as_of.isoformat() / "rebalance_plan.json"


def rebalance_plan_csv_path(data_root: Path, as_of: date) -> Path:
    return rebalance_root(data_root) / as_of.isoformat() / "rebalance_plan.csv"


def save_portfolio_report(data_root: Path, report: PortfolioReport) -> Path:
    path = latest_portfolio_path(data_root)
    write_json_atomic(path, report.to_dict())
    try:
        as_of = date.fromisoformat(report.as_of)
    except ValueError:
        return path
    write_json_atomic(portfolio_by_date_path(data_root, as_of), report.to_dict())
    return path


def save_portfolio_backtest_report(data_root: Path, report: PortfolioBacktestReport) -> Path:
    path = portfolio_backtest_path(data_root, date.fromisoformat(report.as_of))
    write_json_atomic(path, report.to_dict())
    return path


def save_rebalance_plan(data_root: Path, plan: RebalancePlan) -> tuple[Path, Path]:
    as_of = date.fromisoformat(plan.as_of)
    json_path = rebalance_plan_json_path(data_root, as_of)
    csv_path = rebalance_plan_csv_path(data_root, as_of)
    write_json_atomic(json_path, plan.to_dict())
    write_text_atomic(csv_path, _build_csv_text(plan.weight_changes))
    return json_path, csv_path


def load_latest_portfolio_report(data_root: Path) -> dict[str, Any] | None:
    path = latest_portfolio_path(data_root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def load_portfolio_report(path: Path) -> dict[str, Any]:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def list_portfolio_reports(data_root: Path) -> list[dict[str, Any]]:
    root = portfolio_reports_root(data_root) / "by_date"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*.json")):
        try:
            doc = load_portfolio_report(path)
        except (OSError, json.JSONDecodeError):
            continue
        rows.append(
            {
                "as_of": doc.get("as_of"),
                "generated_at": doc.get("generated_at"),
                "source": doc.get("source"),
                "data_run_id": doc.get("data_run_id"),
                "holdings": len(doc.get("holdings") or []),
                "path": path.as_posix(),
            }
        )
    return sorted(rows, key=lambda row: str(row.get("as_of") or ""), reverse=True)

def _build_csv_text(rows: list[dict[str, Any]]) -> str:
    import csv
    from io import StringIO

    columns = ["market", "symbol", "current_weight", "target_weight", "delta_weight", "action", "reason"]
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns)
    writer.writeheader()
    for row in rows:
        writer.writerow({column: row.get(column) for column in columns})
    return buffer.getvalue()
