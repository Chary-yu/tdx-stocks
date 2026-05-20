from __future__ import annotations

from pathlib import Path

from ..platform_paths import format_report_path, open_file


def should_open_report(args, json_mode: bool) -> bool:
    return not json_mode and not getattr(args, "no_open", False)


def print_report_path(path: Path, json_mode: bool) -> None:
    if json_mode:
        return
    print(format_report_path(path))


def open_report_if_needed(args, path: Path | None, json_mode: bool) -> None:
    if path is None or not should_open_report(args, json_mode):
        return
    open_file(path)
