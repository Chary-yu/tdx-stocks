from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .tdx_day import code_from_path, is_a_share_symbol, iter_day_files, read_day_records


@dataclass(frozen=True)
class ExportDailyRecord:
    market: str
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    amount: float


@dataclass(frozen=True)
class ExportAdjustmentFactorResult:
    rows: list[dict[str, object]]
    report: dict[str, object]


def code_from_export_path(path: Path) -> tuple[str, str]:
    stem = path.stem.lower()
    if len(stem) != 9 or stem[2] != "#" or not stem[:2].isalpha() or not stem[3:].isdigit():
        raise ValueError(f"Invalid TDX export filename: {path.name}")
    market = stem[:2]
    symbol = stem[3:]
    if market not in {"sh", "sz", "bj"}:
        raise ValueError(f"Invalid TDX export filename: {path.name}")
    return market, symbol


def iter_export_files(
    export_dir: Path,
    markets: tuple[str, ...] = ("sh", "sz"),
    universe: str = "ashare",
) -> Iterator[Path]:
    if not export_dir.exists():
        return
    for path in sorted(export_dir.glob("*#*.txt")):
        market, symbol = code_from_export_path(path)
        if universe == "ashare" and not is_a_share_symbol(market, symbol):
            continue
        if universe not in {"ashare", "all"}:
            raise ValueError(f"Unsupported universe: {universe}")
        if market not in markets:
            continue
        yield path


def read_export_records(path: Path) -> Iterator[ExportDailyRecord]:
    market, symbol = code_from_export_path(path)
    with path.open("r", encoding="gbk", newline="") as handle:
        header = handle.readline()
        if not header:
            return
        _columns = handle.readline()
        reader = csv.reader(handle, delimiter="\t")
        for row in reader:
            if not row:
                continue
            cells = [cell.strip() for cell in row if cell is not None]
            if len(cells) < 7:
                continue
            trade_date = datetime.strptime(cells[0], "%Y/%m/%d").date()
            yield ExportDailyRecord(
                market=market,
                symbol=symbol,
                trade_date=trade_date,
                open=float(cells[1]),
                high=float(cells[2]),
                low=float(cells[3]),
                close=float(cells[4]),
                volume=int(float(cells[5])),
                amount=float(cells[6]),
            )


def build_export_adjustment_factor_result(
    export_dir: Path,
    raw_vipdoc: Path,
    markets: tuple[str, ...] = ("sh", "sz"),
    universe: str = "ashare",
    from_date: date | None = None,
    to_date: date | None = None,
) -> ExportAdjustmentFactorResult:
    export_files = _resolve_export_files(export_dir, markets, universe)
    rows: list[dict[str, object]] = []
    matched_symbols: list[dict[str, object]] = []
    skipped_details: list[dict[str, object]] = []
    matched_keys: set[tuple[str, str]] = set()
    min_trade_date: date | None = None
    max_trade_date: date | None = None
    raw_file_count = 0
    bad_rows_dropped = 0

    def skip_detail(
        *,
        market: str,
        symbol: str,
        reason: str,
        path: Path,
        bad_rows: int = 0,
        extra: dict[str, object] | None = None,
    ) -> None:
        detail: dict[str, object] = {
            "market": market,
            "symbol": symbol,
            "reason": reason,
            "path": path.as_posix(),
            "bad_rows": bad_rows,
        }
        if extra:
            detail.update(extra)
        skipped_details.append(detail)

    for raw_path in iter_day_files(raw_vipdoc, markets=markets, universe=universe):
        raw_file_count += 1
        market, symbol = code_from_path(raw_path)
        export_path = export_files.get((market, symbol))
        if export_path is None:
            skip_detail(
                market=market,
                symbol=symbol,
                reason="missing_export_file",
                path=raw_path,
            )
            continue

        raw_records = {
            record.trade_date: record
            for record in read_day_records(raw_path, from_date=from_date, to_date=to_date)
        }
        export_records = {
            record.trade_date: record
            for record in read_export_records(export_path)
            if (from_date is None or record.trade_date >= from_date)
            and (to_date is None or record.trade_date <= to_date)
        }
        common_dates = sorted(raw_records.keys() & export_records.keys())
        if not common_dates:
            skip_detail(
                market=market,
                symbol=symbol,
                reason="no_common_dates",
                path=export_path,
            )
            continue

        raw_ratios: list[tuple[date, float]] = []
        skipped_rows = 0
        for trade_date in common_dates:
            raw_close = raw_records[trade_date].close
            export_close = export_records[trade_date].close
            if raw_close <= 0 or export_close <= 0:
                skipped_rows += 1
                continue
            raw_ratios.append((trade_date, export_close / raw_close))
        bad_rows_dropped += skipped_rows

        if not raw_ratios:
            skip_detail(
                market=market,
                symbol=symbol,
                reason="no_positive_rows",
                path=export_path,
                bad_rows=skipped_rows,
            )
            continue

        normalized_base = raw_ratios[-1][1]
        if normalized_base <= 0:
            skip_detail(
                market=market,
                symbol=symbol,
                reason="invalid_normalization_base",
                path=export_path,
            )
            continue

        qfq_rows: list[tuple[date, float]] = []
        for trade_date, raw_ratio in raw_ratios:
            qfq_rows.append((trade_date, round(raw_ratio / normalized_base, 6)))

        first_qfq_factor = qfq_rows[0][1]
        if first_qfq_factor <= 0:
            skip_detail(
                market=market,
                symbol=symbol,
                reason="invalid_qfq_factor_base",
                path=export_path,
            )
            continue

        matched_keys.add((market, symbol))
        matched_symbols.append(
            {
                "market": market,
                "symbol": symbol,
                "export_path": export_path.as_posix(),
                "common_dates": len(common_dates),
                "positive_rows": len(qfq_rows),
                "skipped_rows": skipped_rows,
                "start_date": str(qfq_rows[0][0]),
                "end_date": str(qfq_rows[-1][0]),
            }
        )
        min_trade_date = qfq_rows[0][0] if min_trade_date is None else min(min_trade_date, qfq_rows[0][0])
        max_trade_date = qfq_rows[-1][0] if max_trade_date is None else max(max_trade_date, qfq_rows[-1][0])

        for trade_date, qfq_factor in qfq_rows:
            rows.append(
                {
                    "market": market,
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "start_date": trade_date,
                    "end_date": trade_date,
                    "qfq_factor": qfq_factor,
                    "hfq_factor": round(qfq_factor / first_qfq_factor, 6),
                    "source": f"export:{export_path.as_posix()}",
                }
            )

    for key, export_path in export_files.items():
        if key not in matched_keys and not any(
            detail.get("reason") == "no_common_dates"
            and detail.get("market") == key[0]
            and detail.get("symbol") == key[1]
            for detail in skipped_details
        ):
            skip_detail(
                market=key[0],
                symbol=key[1],
                reason="missing_raw_file",
                path=export_path,
            )

    successful = len(matched_symbols)
    skipped = len(skipped_details)
    metrics = {
        "total_scanned": raw_file_count,
        "successful": successful,
        "skipped": skipped,
        "bad_rows_dropped": bad_rows_dropped,
        "rows_generated": len(rows),
        "date_range": {
            "min": str(min_trade_date) if min_trade_date else None,
            "max": str(max_trade_date) if max_trade_date else None,
        },
    }

    report = {
        "source": "export",
        "export_dir": export_dir.as_posix(),
        "raw_vipdoc": raw_vipdoc.as_posix(),
        "export_files": len(export_files),
        "raw_files": raw_file_count,
        "matched_symbols": successful,
        "rows_written": len(rows),
        "skipped_issue_count": skipped,
        "metrics": metrics,
        "skipped_details": skipped_details,
        "matched_symbols_sample": matched_symbols[:50],
        "issues_sample": skipped_details[:100],
        "min_trade_date": metrics["date_range"]["min"],
        "max_trade_date": metrics["date_range"]["max"],
    }
    return ExportAdjustmentFactorResult(rows=rows, report=report)


def load_export_adjustment_factor_rows(
    export_dir: Path,
    raw_vipdoc: Path,
    markets: tuple[str, ...] = ("sh", "sz"),
    universe: str = "ashare",
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, object]]:
    return build_export_adjustment_factor_result(
        export_dir,
        raw_vipdoc,
        markets=markets,
        universe=universe,
        from_date=from_date,
        to_date=to_date,
    ).rows


def build_export_adjustment_factor_report(
    export_dir: Path,
    raw_vipdoc: Path,
    markets: tuple[str, ...] = ("sh", "sz"),
    universe: str = "ashare",
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, object]:
    return build_export_adjustment_factor_result(
        export_dir,
        raw_vipdoc,
        markets=markets,
        universe=universe,
        from_date=from_date,
        to_date=to_date,
    ).report


def _resolve_export_files(
    export_dir: Path,
    markets: tuple[str, ...],
    universe: str,
) -> dict[tuple[str, str], Path]:
    if export_dir.is_file():
        return {code_from_export_path(export_dir): export_dir}
    return {
        code_from_export_path(path): path
        for path in iter_export_files(export_dir, markets, universe)
    }
