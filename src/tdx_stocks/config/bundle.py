from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfigBundle:
    task_path: Path
    task_config: dict[str, Any]
    merged_config: dict[str, Any]
    auxiliary_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    auxiliary_sources: dict[str, Path] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
