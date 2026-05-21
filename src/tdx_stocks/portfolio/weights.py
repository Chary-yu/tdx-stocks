from __future__ import annotations

from collections.abc import Iterable
from math import isclose
from typing import Any

from .risk_controls import amount_ma20


def build_portfolio_weights(
    items: Iterable[dict[str, Any]],
    weighting: str,
    *,
    max_weight: float = 0.10,
    min_weight: float = 0.0,
    normalize: bool = True,
    capital: float | None = None,
    max_adv_participation: float = 0.10,
    max_liquidation_days: float = 3.0,
    hybrid_weights: dict[str, float] | None = None,
) -> list[float]:
    rows = [dict(item) for item in items]
    if not rows:
        return []

    weights = _initial_weights(rows, weighting, hybrid_weights=hybrid_weights)
    weights = _apply_min_weight(weights, min_weight)
    weights = _apply_liquidity_caps(weights, rows, capital=capital, max_adv_participation=max_adv_participation, max_liquidation_days=max_liquidation_days)
    if not any(weight > 0 for weight in weights):
        weights = [1.0 / len(rows)] * len(rows)
    weights = _cap_and_redistribute(weights, max_weight=max_weight)
    if normalize:
        weights = _normalize(weights)
    return [round(weight, 12) for weight in weights]


def _initial_weights(rows: list[dict[str, Any]], weighting: str, *, hybrid_weights: dict[str, float] | None = None) -> list[float]:
    if weighting == "equal":
        return [1.0 / len(rows)] * len(rows)
    if weighting == "signal-strength":
        scores = [max(float(row.get("score") or 0.0), 0.0) for row in rows]
        if sum(scores) <= 0:
            return [1.0 / len(rows)] * len(rows)
        return _normalize(scores)
    if weighting == "hybrid":
        cfg = hybrid_weights or {}
        signal_w = float(cfg.get("signal_strength", 0.40))
        liquidity_w = float(cfg.get("liquidity_risk", 0.30))
        sector_w = float(cfg.get("sector_alpha", 0.20))
        event_w = float(cfg.get("event_confidence", 0.10))
        total_w = max(signal_w + liquidity_w + sector_w + event_w, 1e-9)
        signal_w, liquidity_w, sector_w, event_w = (signal_w / total_w, liquidity_w / total_w, sector_w / total_w, event_w / total_w)
        scores = _normalize([max(float(row.get("score") or 0.0), 0.0) for row in rows])
        adv_scores = _normalize([max(float(amount_ma20(row) or 0.0), 1.0) for row in rows])
        sector_scores = _normalize([max(float((row.get("factor_values") or {}).get("sector_score") or row.get("sector_score") or 1.0), 0.0) for row in rows])
        event_scores = _normalize([max(float(row.get("event_confidence") or (row.get("factor_values") or {}).get("event_confidence") or 1.0), 0.0) for row in rows])
        combo = [
            signal_w * s + liquidity_w * a + sector_w * sec + event_w * ev
            for s, a, sec, ev in zip(scores, adv_scores, sector_scores, event_scores, strict=True)
        ]
        return _normalize(combo)

    scores = [float(row.get("score") or 0.0) for row in rows]
    if weighting in {"risk-adjusted", "liquidity-risk", "liquidity_risk"}:
        adjusted_scores: list[float] = []
        for row, score in zip(rows, scores, strict=True):
            risk_score = row.get("risk_score")
            if risk_score is None:
                adjusted_scores.append(score)
                continue
            adjusted_scores.append(max(0.0, score * (1.0 - float(risk_score))))
        if weighting in {"liquidity-risk", "liquidity_risk"}:
            liquidity_adjusted = []
            for row, score in zip(rows, adjusted_scores, strict=True):
                adv = amount_ma20(row) or 0.0
                liquidity_adjusted.append(max(0.0, score * max(adv, 1.0)))
            adjusted_scores = liquidity_adjusted
        if sum(adjusted_scores) <= 0:
            return [1.0 / len(rows)] * len(rows)
        return _normalize(adjusted_scores)

    total = sum(scores)
    if total <= 0:
        return [1.0 / len(rows)] * len(rows)
    return [score / total for score in scores]



def _apply_liquidity_caps(
    weights: list[float],
    rows: list[dict[str, Any]],
    *,
    capital: float | None,
    max_adv_participation: float,
    max_liquidation_days: float,
) -> list[float]:
    if not capital or capital <= 0:
        return list(weights)
    capped = list(weights)
    for index, row in enumerate(rows):
        adv = amount_ma20(row)
        if adv is None or adv <= 0:
            continue
        liquidity_cap_amount = adv * max_adv_participation * max_liquidation_days
        cap = liquidity_cap_amount / capital
        if cap > 0 and capped[index] > cap:
            capped[index] = cap
    return capped

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
