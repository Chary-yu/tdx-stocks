from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from itertools import combinations
from statistics import mean
from typing import Any

from ..config import AppConfig
from .registry import get_strategy
from .storage import load_saved_report


@dataclass(frozen=True)
class StrategyCompareRow:
    strategy_name: str
    candidate_count: int
    avg_score: float | None
    max_score: float | None
    high_score_count: int
    risk_flag_count: int
    stocks: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_name": self.strategy_name,
            "candidate_count": self.candidate_count,
            "avg_score": self.avg_score,
            "max_score": self.max_score,
            "high_score_count": self.high_score_count,
            "risk_flag_count": self.risk_flag_count,
            "stocks": self.stocks,
        }


@dataclass(frozen=True)
class StrategyCompareResult:
    as_of: str
    strategies: list[StrategyCompareRow]
    overlaps: list[dict[str, object]]
    unique_stocks: dict[str, list[str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "strategies": [row.to_dict() for row in self.strategies],
            "overlaps": self.overlaps,
            "unique_stocks": self.unique_stocks,
        }


def compare_strategies(
    config: AppConfig,
    strategy_names: list[str],
    *,
    as_of: date | None = None,
    use_saved_reports: bool = True,
) -> StrategyCompareResult:
    docs = {
        strategy_name: _resolve_report_doc(
            config,
            strategy_name,
            as_of=as_of,
            use_saved_reports=use_saved_reports,
        )
        for strategy_name in strategy_names
    }
    strategy_rows: list[StrategyCompareRow] = []
    strategy_sets: dict[str, set[tuple[str, str]]] = {}
    for strategy_name, doc in docs.items():
        candidates = list(doc.get("candidates") or [])
        stocks = sorted(
            {
                (str(candidate.get("market") or "").lower(), str(candidate.get("symbol") or ""))
                for candidate in candidates
                if candidate.get("market") and candidate.get("symbol")
            }
        )
        strategy_sets[strategy_name] = set(stocks)
        scores = [float(candidate["score"]) for candidate in candidates if candidate.get("score") is not None]
        risk_flags = {
            str(flag)
            for candidate in candidates
            for flag in (candidate.get("risk_flags") or [])
        }
        strategy_rows.append(
            StrategyCompareRow(
                strategy_name=strategy_name,
                candidate_count=int(doc.get("candidate_count") or len(candidates)),
                avg_score=round(mean(scores), 2) if scores else None,
                max_score=round(max(scores), 2) if scores else None,
                high_score_count=sum(1 for score in scores if score >= 80.0),
                risk_flag_count=len(risk_flags),
                stocks=[f"{symbol}.{market.upper()}" for market, symbol in stocks],
            )
        )

    overlaps: list[dict[str, object]] = []
    for left_name, right_name in combinations(strategy_names, 2):
        left = strategy_sets.get(left_name, set())
        right = strategy_sets.get(right_name, set())
        shared = sorted(left & right)
        overlaps.append(
            {
                "left_strategy": left_name,
                "right_strategy": right_name,
                "overlap_count": len(shared),
                "stocks": [f"{symbol}.{market.upper()}" for market, symbol in shared],
            }
        )

    unique_stocks = {}
    for strategy_name, stock_set in strategy_sets.items():
        other_symbols = set().union(*(symbols for name, symbols in strategy_sets.items() if name != strategy_name))
        unique = sorted(stock_set - other_symbols)
        unique_stocks[strategy_name] = [f"{symbol}.{market.upper()}" for market, symbol in unique]

    return StrategyCompareResult(
        as_of=(as_of.isoformat() if as_of else "latest"),
        strategies=sorted(strategy_rows, key=lambda item: item.strategy_name),
        overlaps=overlaps,
        unique_stocks=unique_stocks,
    )


def _resolve_report_doc(
    config: AppConfig,
    strategy_name: str,
    *,
    as_of: date | None,
    use_saved_reports: bool,
) -> dict[str, Any]:
    if use_saved_reports:
        saved = load_saved_report(
            config.paths.data_root,
            strategy_name,
            as_of=as_of.isoformat() if as_of else "latest",
        )
        if saved is not None:
            return saved
    definition = get_strategy(strategy_name)
    params = replace(definition.default_params, as_of=as_of)
    report = definition.runner(config, params)
    return {
        "candidate_count": report.summary.get("eligible"),
        "excluded_count": report.summary.get("excluded"),
        "candidates": report.picks,
        "excluded_summary": {},
        "risk_summary": report.summary.get("risk_flag_counts", {}),
        "diagnostics": {"summary": report.summary, "explain": report.explain},
    }
