from __future__ import annotations

from .models import Holding, PortfolioBacktestReport, PortfolioReport, RebalancePlan


def report_to_dict(report: PortfolioReport) -> dict[str, object]:
    return report.to_dict()


def backtest_to_dict(report: PortfolioBacktestReport) -> dict[str, object]:
    return report.to_dict()


def rebalance_to_dict(plan: RebalancePlan) -> dict[str, object]:
    return plan.to_dict()
