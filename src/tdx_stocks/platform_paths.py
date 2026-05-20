from __future__ import annotations

import os
import platform
import subprocess
from pathlib import Path


def is_wsl() -> bool:
    if platform.system() != "Linux":
        return False
    release = platform.release().lower()
    if "microsoft" in release or "wsl" in release:
        return True
    version = platform.version().lower()
    return "microsoft" in version or "wsl" in version


def to_windows_path(path: Path) -> str | None:
    parts = path.as_posix().split("/")
    if len(parts) < 4 or parts[1] != "mnt" or len(parts[2]) != 1:
        return None
    drive = parts[2].upper()
    tail = "\\".join(part for part in parts[3:] if part)
    if tail:
        return f"{drive}:\\{tail}"
    return f"{drive}:\\"


def open_file(path: Path) -> None:
    if is_wsl():
        windows_path = to_windows_path(path) or path.as_posix().replace("/", "\\")
        subprocess.run(["explorer.exe", windows_path], check=False)
        return

    system = platform.system()
    if system == "Windows":
        startfile = getattr(os, "startfile", None)
        if startfile is not None:
            startfile(path)
            return
        subprocess.run(["explorer.exe", str(path)], check=False)
        return
    if system == "Darwin":
        subprocess.run(["open", str(path)], check=False)
        return
    subprocess.run(["xdg-open", str(path)], check=False)


def format_report_path(path: Path) -> str:
    windows_path = to_windows_path(path)
    windows_display = windows_path if windows_path is not None else str(path)
    return f"Report:\nWSL: {path.as_posix()}\nWindows: {windows_display}"
