from __future__ import annotations

from pathlib import Path
from typing import Any

from ..io_utils import write_json_atomic, write_text_atomic


def save_output(path: Path, payload: Any, *, format_name: str = "json") -> Path:
    if format_name == "json":
        write_json_atomic(path, payload)
    else:
        write_text_atomic(path, str(payload))
    return path
