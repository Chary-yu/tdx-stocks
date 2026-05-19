from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import AppConfig


@dataclass(frozen=True)
class RunStepResult:
    name: str
    status: str
    message: str
    metrics: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "metrics": self.metrics,
            "outputs": self.outputs,
        }


@dataclass(frozen=True)
class RunResult:
    task_type: str
    name: str
    status: str
    summary: dict[str, Any]
    outputs: dict[str, str] = field(default_factory=dict)
    steps: list[RunStepResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "name": self.name,
            "status": self.status,
            "summary": self.summary,
            "outputs": self.outputs,
            "steps": [step.to_dict() for step in self.steps],
        }


@dataclass(frozen=True)
class RunConfig:
    path: Path
    base_dir: Path
    data: dict[str, Any]
    app_config: AppConfig
    task_type: str

    def section(self, name: str, default: Any | None = None) -> Any:
        return self.data.get(name, default)
