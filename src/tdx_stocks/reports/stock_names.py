from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

StockKey = tuple[str, str]

_DISPLAY_SYMBOL_RE = re.compile(r"^(?P<symbol>\d{6})\.(?P<market>SH|SZ|BJ)$", re.IGNORECASE)


def normalize_stock_key(market: object, symbol: object) -> StockKey | None:
    market_text = str(market or "").strip().lower()
    symbol_text = str(symbol or "").strip()
    if not symbol_text:
        return None
    if not market_text:
        parsed = parse_display_symbol(symbol_text)
        if parsed is not None:
            return parsed
        return None
    if market_text in {"sh", "sz", "bj"}:
        return (market_text, symbol_text.zfill(6) if symbol_text.isdigit() else symbol_text)
    return None


def parse_display_symbol(value: object) -> StockKey | None:
    match = _DISPLAY_SYMBOL_RE.match(str(value or "").strip())
    if not match:
        return None
    return (match.group("market").lower(), match.group("symbol"))


def display_code(market: object, symbol: object) -> str:
    key = normalize_stock_key(market, symbol)
    if key is None:
        text = str(symbol or "").strip()
        return text or "无"
    return f"{key[1]}.{key[0].upper()}"


def collect_stock_keys(payload: object) -> set[StockKey]:
    keys: set[StockKey] = set()

    def visit(value: object) -> None:
        if isinstance(value, dict):
            key = normalize_stock_key(value.get("market"), value.get("symbol"))
            if key is not None:
                keys.add(key)
            for item in value.values():
                visit(item)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                visit(item)
            return
        if isinstance(value, str):
            key = parse_display_symbol(value)
            if key is not None:
                keys.add(key)

    visit(payload)
    return keys


def build_stock_name_map(export_dir: Path | None, keys: Iterable[StockKey]) -> dict[StockKey, str]:
    if export_dir is None or not export_dir.exists():
        return {}
    names: dict[StockKey, str] = {}
    for market, symbol in sorted(set(keys)):
        name = resolve_stock_name(export_dir, market, symbol)
        if name:
            names[(market, symbol)] = name
    return names


def resolve_stock_name(export_dir: Path, market: str, symbol: str) -> str | None:
    candidates = [
        export_dir / f"{market.upper()}#{symbol}.txt",
        export_dir / f"{market.lower()}#{symbol}.txt",
        export_dir / f"{market}{symbol}.txt",
        export_dir / f"{market.upper()}{symbol}.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            header = path.read_text(encoding="gbk", errors="ignore").splitlines()[0].strip()
        except (OSError, IndexError):
            continue
        name = _extract_name_from_header(header)
        if name:
            return name
    return None


def _extract_name_from_header(header: str) -> str | None:
    if not header:
        return None
    parts = [part.strip() for part in header.replace(",", " ").split() if part.strip()]
    if len(parts) >= 2:
        candidate = parts[1]
        if candidate and not candidate.lower() in {"date", "open", "high", "low", "close"}:
            return candidate
    return None


def stock_display(
    row_or_symbol: object,
    stock_names: dict[StockKey, str] | None = None,
    market: object | None = None,
    *,
    include_code: bool = False,
) -> str:
    """Return a user-facing stock display name.

    When include_code=True and a stock name is available, append the normalized
    stock code in Chinese parentheses, for example: 星宇股份（601799.SH）.
    The optional flag keeps older callers compatible while allowing report
    renderers to preserve traceability for skipped trades and details.
    """
    stock_names = stock_names or {}

    def finish(name_or_code: str, code: str | None = None) -> str:
        text = str(name_or_code or "无")
        if include_code and code and text != code:
            return f"{text}（{code}）"
        return text

    if isinstance(row_or_symbol, dict):
        row = row_or_symbol
        explicit = row.get("stock_name") or row.get("name") or row.get("股票名称")
        key = normalize_stock_key(row.get("market"), row.get("symbol"))
        if key is None:
            key = parse_display_symbol(row.get("display_symbol"))
        code = display_code(*key) if key is not None else str(row.get("display_symbol") or row.get("symbol") or "无")
        if explicit:
            return finish(str(explicit), code)
        if key is not None:
            return finish(stock_names.get(key) or code, code)
        return code

    key = normalize_stock_key(market, row_or_symbol)
    if key is None:
        key = parse_display_symbol(row_or_symbol)
    if key is None:
        return str(row_or_symbol or "无")
    code = display_code(*key)
    return finish(stock_names.get(key) or code, code)


def stock_code(row_or_symbol: object, market: object | None = None) -> str:
    if isinstance(row_or_symbol, dict):
        key = normalize_stock_key(row_or_symbol.get("market"), row_or_symbol.get("symbol"))
        if key is None:
            key = parse_display_symbol(row_or_symbol.get("display_symbol"))
    else:
        key = normalize_stock_key(market, row_or_symbol) or parse_display_symbol(row_or_symbol)
    if key is None:
        return str(row_or_symbol or "无")
    return display_code(*key)
