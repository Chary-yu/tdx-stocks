from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .config import AppConfig
from .export_io import code_from_export_path, read_export_records
from .query import build_select_sql, fetch_dicts, open_query_context


@dataclass(frozen=True)
class AdjustmentVerificationInput:
    symbol: str
    market: str | None
    code: str


def parse_adjustment_symbol(value: str) -> AdjustmentVerificationInput:
    text = value.strip()
    if not text:
        raise ValueError("symbol must not be empty")

    if "." in text:
        code, market = text.split(".", 1)
        market = market.lower()
        if market not in {"sh", "sz", "bj"}:
            raise ValueError(f"Unsupported market in symbol: {value}")
        if len(code) != 6 or not code.isdigit():
            raise ValueError(f"Unsupported symbol format: {value}")
        return AdjustmentVerificationInput(symbol=f"{code}.{market.upper()}", market=market, code=code)

    lowered = text.lower()
    if len(lowered) == 8 and lowered[:2] in {"sh", "sz", "bj"} and lowered[2:].isdigit():
        market = lowered[:2]
        code = lowered[2:]
        return AdjustmentVerificationInput(symbol=f"{code}.{market.upper()}", market=market, code=code)

    if len(text) == 6 and text.isdigit():
        return AdjustmentVerificationInput(symbol=text, market=None, code=text)

    raise ValueError(f"Unsupported symbol format: {value}")


def resolve_export_text_path(export_root: Path, symbol: AdjustmentVerificationInput) -> Path:
    if export_root.is_file():
        market, code = code_from_export_path(export_root)
        if code == symbol.code and (symbol.market is None or market == symbol.market):
            return export_root
        raise FileNotFoundError(f"export file does not match symbol: {symbol.symbol}")

    if not export_root.exists():
        raise FileNotFoundError(f"export directory not found: {export_root}")

    if symbol.market is not None:
        for candidate in (
            export_root / f"{symbol.market.upper()}#{symbol.code}.txt",
            export_root / f"{symbol.market.lower()}#{symbol.code}.txt",
        ):
            if candidate.exists():
                return candidate

    matches = sorted(export_root.glob(f"*#{symbol.code}.txt"))
    if not matches:
        raise FileNotFoundError(f"export file not found for symbol: {symbol.symbol}")
    if symbol.market is not None:
        filtered = [path for path in matches if code_from_export_path(path)[0] == symbol.market]
        if not filtered:
            raise FileNotFoundError(f"export file not found for symbol: {symbol.symbol}")
        if len(filtered) > 1:
            raise ValueError(f"Multiple export files matched symbol: {symbol.symbol}")
        return filtered[0]
    if len(matches) > 1:
        raise ValueError(f"Multiple export files matched symbol: {symbol.symbol}")
    return matches[0]


def build_adjustment_verification_report(
    config: AppConfig,
    symbol_text: str,
    input_path: Path | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    threshold: float = 0.01,
) -> dict[str, object]:
    symbol = parse_adjustment_symbol(symbol_text)
    export_root = input_path or config.paths.tdx_export
    export_path = resolve_export_text_path(export_root, symbol)

    export_rows = [
        record
        for record in read_export_records(export_path)
        if (from_date is None or record.trade_date >= from_date)
        and (to_date is None or record.trade_date <= to_date)
    ]

    ctx = open_query_context(config)
    try:
        columns, rows = fetch_dicts(
            ctx.con,
            build_select_sql(
                ctx.con,
                "adj_daily",
                columns=["trade_date", "adj_close"],
                symbol=symbol.code,
                market=symbol.market,
                from_date=from_date.isoformat() if from_date else None,
                to_date=to_date.isoformat() if to_date else None,
                order_by="trade_date",
                desc=False,
                limit=None,
            ),
        )
    finally:
        ctx.close()

    del columns

    export_map = {record.trade_date: record.close for record in export_rows}
    adj_map = {row["trade_date"]: row["adj_close"] for row in rows}
    common_dates = sorted(export_map.keys() & adj_map.keys())
    export_only = sorted(export_map.keys() - adj_map.keys())
    adj_only = sorted(adj_map.keys() - export_map.keys())

    mismatches: list[dict[str, object]] = []
    max_abs_error = 0.0
    max_abs_error_date: date | None = None
    sum_abs_error = 0.0

    for trade_date in common_dates:
        export_close = float(export_map[trade_date])
        adj_close = float(adj_map[trade_date])
        abs_error = abs(adj_close - export_close)
        sum_abs_error += abs_error
        if abs_error > max_abs_error:
            max_abs_error = abs_error
            max_abs_error_date = trade_date
        if abs_error > threshold:
            mismatches.append(
                {
                    "trade_date": trade_date,
                    "export_close": export_close,
                    "adj_close": adj_close,
                    "abs_error": round(abs_error, 6),
                }
            )

    report = {
        "symbol": symbol.symbol,
        "code": symbol.code,
        "market": symbol.market,
        "threshold": threshold,
        "export_path": export_path.as_posix(),
        "from_date": from_date.isoformat() if from_date else None,
        "to_date": to_date.isoformat() if to_date else None,
        "export_rows": len(export_rows),
        "adj_rows": len(rows),
        "common_rows": len(common_dates),
        "export_only_rows": len(export_only),
        "adj_only_rows": len(adj_only),
        "max_abs_error": round(max_abs_error, 6),
        "max_abs_error_date": max_abs_error_date.isoformat() if max_abs_error_date else None,
        "mean_abs_error": round(sum_abs_error / len(common_dates), 6) if common_dates else None,
        "mismatch_count": len(mismatches),
        "ok": len(mismatches) == 0 and not export_only and not adj_only,
        "mismatch_samples": mismatches[:50],
        "export_only_dates": [value.isoformat() for value in export_only[:50]],
        "adj_only_dates": [value.isoformat() for value in adj_only[:50]],
    }
    return report
