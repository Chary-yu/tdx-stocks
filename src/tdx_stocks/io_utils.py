from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json_atomic(path: Path, document: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(path)
    return path


def write_text_atomic(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(payload, encoding="utf-8")
    tmp_path.replace(path)
    return path
