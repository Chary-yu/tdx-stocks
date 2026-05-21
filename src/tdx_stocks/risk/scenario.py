from __future__ import annotations

from typing import Any


def generate_risk_scenarios(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    symbol = str(candidate.get("symbol") or "")
    return [
        {
            "symbol": symbol,
            "scenario": "流动性骤降",
            "probability": "medium",
            "impact": "high",
            "trigger": "amount_ma20 连续下滑",
        },
        {
            "symbol": symbol,
            "scenario": "技术面转弱",
            "probability": "medium",
            "impact": "medium",
            "trigger": "跌破 MA20 或动量转负",
        },
    ]
