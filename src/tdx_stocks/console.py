from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Sequence
from typing import Any

try:  # pragma: no cover - optional dependency
    from rich.console import Console
    from rich.table import Table
except ModuleNotFoundError:  # pragma: no cover - fallback when rich is absent
    Console = None
    Table = None


def should_use_rich(stream) -> bool:
    if Console is None:
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("CI") not in (None, "", "0", "false", "False"):
        return False
    return hasattr(stream, "isatty") and stream.isatty()


def print_notice(message: str, stream=None) -> None:
    stream = sys.stderr if stream is None else stream
    if should_use_rich(stream):
        console = Console(file=stream, force_terminal=True, color_system="auto")
        console.print(f"[yellow]{message}[/yellow]")
        return
    print(message, file=stream)


def print_key_values(
    title: str,
    items: Iterable[tuple[str, object]],
    *,
    stream=None,
) -> None:
    stream = sys.stdout if stream is None else stream
    rows = [(str(key), _stringify(value)) for key, value in items]
    if should_use_rich(stream) and Table is not None:
        console = Console(file=stream, force_terminal=True, color_system="auto")
        table = Table(title=title, show_header=True, header_style="bold cyan")
        table.add_column("Key", style="bold")
        table.add_column("Value")
        for key, value in rows:
            table.add_row(key, value)
        console.print(table)
        return

    print(title, file=stream)
    for key, value in rows:
        print(f"{key}={value}", file=stream)


def print_json(data: object, *, stream=None) -> None:
    stream = sys.stdout if stream is None else stream
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str), file=stream)


def print_table(columns: Sequence[str], rows: Sequence[dict[str, object]], *, stream=None) -> None:
    stream = sys.stdout if stream is None else stream
    if should_use_rich(stream) and Table is not None:
        console = Console(file=stream, force_terminal=True, color_system="auto")
        table = Table(show_header=True, header_style="bold cyan")
        for column in columns:
            table.add_column(str(column))
        for row in rows:
            table.add_row(*[_stringify(row.get(column)) for column in columns])
        console.print(table)
        return

    if not rows:
        print("(no rows)", file=stream)
        return
    widths = [len(str(column)) for column in columns]
    rendered_rows = [[_stringify(row.get(column)) for column in columns] for row in rows]
    for index, column in enumerate(columns):
        widths[index] = max(widths[index], *(len(row[index]) for row in rendered_rows))
    print("  ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns)), file=stream)
    print("  ".join("-" * width for width in widths), file=stream)
    for row in rendered_rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(columns))), file=stream)


def _stringify(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return str(value)
    return str(value)
