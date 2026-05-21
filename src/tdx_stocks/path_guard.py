from __future__ import annotations

from pathlib import Path


def resolve_reports_root(base: Path, user_input: str | None) -> Path:
    allowed = base.expanduser().resolve(strict=False)
    if user_input is None or not str(user_input).strip():
        return allowed

    raw = Path(user_input).expanduser()
    candidate = raw if raw.is_absolute() else allowed / raw
    candidate = candidate.resolve(strict=False)
    if candidate != allowed and allowed not in candidate.parents:
        raise ValueError(f"path must be under {allowed}")
    return candidate
