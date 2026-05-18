from __future__ import annotations

from collections.abc import Iterable
from math import isclose
from typing import Any


def build_portfolio_weights(
    items: Iterable[dict[str, Any]],
    weighting: str,
    *,
    max_weight: float = 0.10,
    min_weight: float = 0.0,
    normalize: bool = True,
) -> list[float]:
    rows = [dict(item) for item in items]
    if not rows:
        return []

    weights = _initial_weights(rows, weighting)
    weights = _apply_min_weight(weights, min_weight)
    if not any(weight > 0 for weight in weights):
        weights = [1.0 / len(rows)] * len(rows)
    weights = _cap_and_redistribute(weights, max_weight=max_weight)
    if normalize:
        weights = _normalize(weights)
    return [round(weight, 12) for weight in weights]


def _initial_weights(rows: list[dict[str, Any]], weighting: str) -> list[float]:
    if weighting == "equal":
        return [1.0 / len(rows)] * len(rows)

    scores = [float(row.get("score") or 0.0) for row in rows]
    if weighting == "risk-adjusted":
        adjusted_scores: list[float] = []
        for row, score in zip(rows, scores, strict=True):
            risk_score = row.get("risk_score")
            if risk_score is None:
                adjusted_scores.append(score)
                continue
            adjusted_scores.append(max(0.0, score * (1.0 - float(risk_score))))
        if sum(adjusted_scores) <= 0:
            return [1.0 / len(rows)] * len(rows)
        return _normalize(adjusted_scores)

    total = sum(scores)
    if total <= 0:
        return [1.0 / len(rows)] * len(rows)
    return [score / total for score in scores]


def _apply_min_weight(weights: list[float], min_weight: float) -> list[float]:
    if min_weight <= 0:
        return list(weights)
    filtered = [weight if weight >= min_weight else 0.0 for weight in weights]
    if sum(filtered) <= 0:
        return list(weights)
    return filtered


def _cap_and_redistribute(weights: list[float], *, max_weight: float) -> list[float]:
    if max_weight <= 0:
        return _normalize(weights)

    capped = list(weights)
    while True:
        over = [index for index, weight in enumerate(capped) if weight > max_weight + 1e-12]
        if not over:
            break
        excess = 0.0
        for index in over:
            excess += capped[index] - max_weight
            capped[index] = max_weight
        remaining = [index for index, weight in enumerate(capped) if weight < max_weight - 1e-12 and weight > 0]
        if not remaining or excess <= 0:
            break
        remaining_total = sum(capped[index] for index in remaining)
        if remaining_total <= 0:
            break
        for index in remaining:
            share = capped[index] / remaining_total
            capped[index] += excess * share
    return capped


def _normalize(weights: list[float]) -> list[float]:
    total = sum(weights)
    if total <= 0:
        return [1.0 / len(weights)] * len(weights)
    normalized = [weight / total for weight in weights]
    if isclose(sum(normalized), 1.0, rel_tol=1e-9, abs_tol=1e-9):
        return normalized
    return normalized
