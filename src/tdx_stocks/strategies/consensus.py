from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
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
    bucket: dict[tuple[str, str], dict[str, Any]] = {}
    for strategy_name, doc in docs.items():
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
                "scores": [],
                "risk_scores": [],
                "candidate_types": set(),
                "tags": set(),
                "risk_flags": set(),
                "reasons": set(),
            },
            )
            item["strategies"].add(strategy_name)
            if candidate.get("score") is not None:
                item["scores"].append(float(candidate["score"]))
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
        scores = item["scores"]
        rows.append(
            ConsensusRow(
                market=item["market"],
                symbol=item["symbol"],
                hit_count=hit_count,
                strategies=sorted(item["strategies"]),
                avg_score=round(mean(scores), 2) if scores else 0.0,
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
