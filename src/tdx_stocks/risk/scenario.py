from __future__ import annotations

from typing import Any


def generate_risk_scenarios(candidate: dict[str, Any], cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    config = cfg or {}
    templates = config.get("templates") if isinstance(config.get("templates"), dict) else {}
    symbol = str(candidate.get("symbol") or "")
    market = str(candidate.get("market") or "")
    rows = [
        _row(symbol, market, "technical", templates.get("technical") or "股价跌破{ma}日均线，趋势走坏", {"ma": 20}, 0.30, "medium", "跌破20日均线"),
        _row(symbol, market, "sector", templates.get("sector") or "行业政策收紧，竞争加剧", {}, 0.20, "medium", "行业政策或景气度转弱"),
    ]
    if candidate.get("event_type"):
        rows.append(_row(symbol, market, "event", "事件窗口内波动放大", {}, 0.25, "medium", str(candidate.get("event_type"))))
    if candidate.get("risk_flags"):
        rows.append(_row(symbol, market, "technical", "风险标签触发：{tags}", {"tags": ",".join(str(x) for x in candidate.get("risk_flags") or [])}, 0.35, "high", "风险标签持续存在"))
    min_count = int(config.get("min_scenarios_per_stock") or 2)
    while len(rows) < min_count:
        rows.append(_row(symbol, market, "macro", templates.get("macro") or "宏观环境恶化，风险偏好下降", {}, 0.20, "medium", "宏观滤网转弱"))
    return rows


def _row(symbol: str, market: str, category: str, template: str, values: dict[str, Any], probability: float, impact: str, trigger: str) -> dict[str, Any]:
    try:
        description = template.format(**values)
    except Exception:
        description = template
    return {
        "market": market,
        "symbol": symbol,
        "scenario_type": category,
        "scenario_description": description,
        "scenario_probability": probability,
        "scenario_impact": impact,
        "scenario_trigger": trigger,
    }
