from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
import math
from statistics import mean
from typing import Any

from ..config import AppConfig
from .registry import get_strategy
from .storage import load_saved_report


@dataclass(frozen=True)
class ConsensusRow:
    market: str
    symbol: str
    hit_count: int
    strategies: list[str]
    avg_score: float
    max_score: float
    risk_score: float | None
    candidate_types: list[str]
    tags: list[str]
    risk_flags: list[str]
    reasons: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "market": self.market,
            "symbol": self.symbol,
            "hit_count": self.hit_count,
            "strategies": self.strategies,
            "avg_score": self.avg_score,
            "max_score": self.max_score,
            "risk_score": self.risk_score,
            "candidate_types": self.candidate_types,
            "tags": self.tags,
            "risk_flags": self.risk_flags,
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class ConsensusResult:
    as_of: str
    min_hit: int
    rows: list[ConsensusRow]

    def to_dict(self) -> dict[str, object]:
        return {
            "as_of": self.as_of,
            "min_hit": self.min_hit,
            "rows": [row.to_dict() for row in self.rows],
        }


def build_consensus(
    config: AppConfig,
    strategy_names: list[str],
    *,
    as_of: date | None = None,
    min_hit: int = 2,
    use_saved_reports: bool = True,
    method: str = "simple_majority",
    require_different_types: bool = False,
    strategy_weights: dict[str, float] | None = None,
    decay_enabled: bool = False,
    decay_half_life_days: float = 5.0,
    decay_min_weight: float = 0.10,
) -> ConsensusResult:
    docs = {
        strategy_name: _resolve_report_doc(
            config,
            strategy_name,
            as_of=as_of,
            use_saved_reports=use_saved_reports,
        )
        for strategy_name in strategy_names
    }
    strategy_weights = strategy_weights or {}
    bucket: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy_name, doc in docs.items():
        definition = get_strategy(strategy_name)
        type_tag = str(definition.strategy_type or definition.group or "other")
        perf_weight = float(strategy_weights.get(strategy_name) or 1.0)
        for candidate in doc.get("candidates") or []:
            market = str(candidate.get("market") or "").lower()
            symbol = str(candidate.get("symbol") or "")
            if not market or not symbol:
                continue
            key = (market, symbol)
            item = bucket.setdefault(
                key,
                {
                    "market": market,
                    "symbol": symbol,
                    "strategies": set(),
                    "strategy_types": set(),
                    "scores": [],
                    "weighted_scores": [],
                    "risk_scores": [],
                    "candidate_types": set(),
                    "tags": set(),
                    "risk_flags": set(),
                    "reasons": set(),
                },
            )
            item["strategies"].add(strategy_name)
            item["strategy_types"].add(type_tag)
            if candidate.get("score") is not None:
                score = float(candidate["score"])
                item["scores"].append(score)
                item["weighted_scores"].append(score * perf_weight)
            risk_score = candidate.get("risk_score")
            if risk_score is not None:
                item["risk_scores"].append(float(risk_score))
            if candidate.get("candidate_type"):
                item["candidate_types"].add(str(candidate["candidate_type"]))
            for field in ("tags", "risk_flags", "reasons"):
                for value in candidate.get(field) or []:
                    item[field].add(str(value))

    rows: list[ConsensusRow] = []
    for item in bucket.values():
        hit_count = len(item["strategies"])
        if hit_count < min_hit:
            continue
        if require_different_types and len(item["strategy_types"]) < min_hit:
            continue
        scores = item["scores"]
        if decay_enabled and scores:
            decay = max(decay_min_weight, 0.5 ** (1.0 / max(0.5, decay_half_life_days)))
            scores = [value * decay for value in scores]
        avg_score = round(mean(scores), 2) if scores else 0.0
        if method == "weighted_by_performance" and item["weighted_scores"]:
            weighted_base = item["weighted_scores"]
            avg_score = round(sum(weighted_base) / max(1, hit_count), 2)
        if method == "rank_sum":
            avg_score = round(avg_score + math.log(hit_count + 1.0) * 5.0, 2)
        rows.append(
            ConsensusRow(
                market=item["market"],
                symbol=item["symbol"],
                hit_count=hit_count,
                strategies=sorted(item["strategies"]),
                avg_score=avg_score,
                max_score=round(max(scores), 2) if scores else 0.0,
                risk_score=round(mean(item["risk_scores"]), 4) if item["risk_scores"] else None,
                candidate_types=sorted(item["candidate_types"]),
                tags=sorted(item["tags"]),
                risk_flags=sorted(item["risk_flags"]),
                reasons=sorted(item["reasons"]),
            )
        )

    rows = sorted(
        rows,
        key=lambda row: (
            -row.hit_count,
            -row.avg_score,
            -row.max_score,
            len(row.risk_flags),
            row.symbol,
        ),
    )
    return ConsensusResult(
        as_of=(as_of.isoformat() if as_of else "latest"),
        min_hit=min_hit,
        rows=rows,
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
