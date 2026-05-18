from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class DailyStepResult:
    step_name: str
    status: str
    message: str
    output_paths: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DailyRunReport:
    schema_version: str
    app_version: str
    as_of: str
    generated_at: str
    data_run_id: str | None
    status: str
    steps: list[dict[str, Any]]
    summary: dict[str, Any]
    data_quality: dict[str, Any]
    strategy_summary: dict[str, Any]
    consensus_summary: dict[str, Any]
    portfolio_summary: dict[str, Any]
    rebalance_summary: dict[str, Any]
    warnings: list[str]
    errors: list[str]
    outputs: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
