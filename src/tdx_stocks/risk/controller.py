
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..portfolio.risk_controls import candidate_tags, risk_interception


@dataclass(frozen=True)
class RiskControllerResult:
    candidates: list[dict[str, Any]]
    interceptions: list[dict[str, Any]]
    overrides: dict[str, Any]
    diagnostics: dict[str, Any]


def apply_risk_management(candidates: list[dict[str, Any]], risk_cfg: dict[str, Any] | None = None, *, market_regime: dict[str, Any] | None = None) -> RiskControllerResult:
    cfg = risk_cfg or {}
    hard = cfg.get("hard") if isinstance(cfg.get("hard"), dict) else {}
    soft = cfg.get("soft") if isinstance(cfg.get("soft"), dict) else {}
    dynamic = cfg.get("dynamic") if isinstance(cfg.get("dynamic"), dict) else {}
    block_tags = {str(x) for x in hard.get("block_tags") or []}
    block_sectors = {str(x) for x in hard.get("block_sectors") or []}
    kept: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    for row in candidates:
        tags = candidate_tags(row)
        matched_tags = sorted(block_tags & tags)
        if matched_tags:
            logs.append(risk_interception(row, reason="统一硬风控标签拦截", trigger_tags=matched_tags))
            continue
        sector = _sector(row)
        if sector and sector in block_sectors:
            logs.append(risk_interception(row, reason=f"统一硬风控行业拦截：{sector}", trigger_tags=["blocked_sector"]))
            continue
        kept.append(row)
    overrides: dict[str, Any] = {}
    regime = market_regime or {}
    if dynamic:
        if str(regime.get("status") or "").lower() == "bear" or str(regime.get("action") or "").lower() == "reduce_position":
            hv = dynamic.get("high_volatility_mode") if isinstance(dynamic.get("high_volatility_mode"), dict) else {}
            overrides.update(_known_overrides(hv))
        low = dynamic.get("low_liquidity_mode") if isinstance(dynamic.get("low_liquidity_mode"), dict) else {}
        if low and str(regime.get("liquidity") or "").lower() in {"low", "low_liquidity"}:
            overrides.update(_known_overrides(low))
    diagnostics = {
        "hard": {"block_tags": sorted(block_tags), "block_sectors": sorted(block_sectors), "interception_count": len(logs)},
        "soft": {"configured": bool(soft), "warnings": []},
        "dynamic": {"configured": bool(dynamic), "overrides": dict(overrides)},
    }
    return RiskControllerResult(kept, logs, overrides, diagnostics)


def _known_overrides(values: dict[str, Any]) -> dict[str, Any]:
    mapping = {
        "max_weight": "max_weight",
        "max_sector": "max_sector_weight",
        "max_sector_weight": "max_sector_weight",
        "max_adv_participation": "max_adv_participation",
        "min_amount_ma20": "min_amount_ma20",
        "max_liquidation_days": "max_liquidation_days",
    }
    out: dict[str, Any] = {}
    for key, target in mapping.items():
        if key in values:
            out[target] = values[key]
    return out


def _sector(row: dict[str, Any]) -> str | None:
    factors = row.get("factor_values") if isinstance(row.get("factor_values"), dict) else {}
    value = row.get("sector") or row.get("industry") or factors.get("sector") or factors.get("industry") or factors.get("申万行业")
    return str(value) if value not in (None, "") else None
