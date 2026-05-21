from __future__ import annotations

from pathlib import Path
from typing import Any

from .store import load_latest_portfolio_report, load_portfolio_report


def load_portfolio_target(*, data_root: Path, source: str) -> dict[str, Any]:
    src = str(source or "portfolio")
    if src == "portfolio":
        doc = load_latest_portfolio_report(data_root)
        if doc is None:
            raise FileNotFoundError("latest portfolio report not found")
        return doc
    if src == "portfolio_report":
        doc = load_latest_portfolio_report(data_root)
        if doc is None:
            raise FileNotFoundError("latest portfolio report not found")
        return doc
    if src.startswith("file:"):
        path = Path(src[len("file:") :]).expanduser()
        return load_portfolio_report(path)
    raise ValueError(f"unsupported target_source: {src}")
