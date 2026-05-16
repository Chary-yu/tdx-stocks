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


def load_export_adjustment_factor_rows(
    export_dir: Path,
    raw_vipdoc: Path,
    markets: tuple[str, ...] = ("sh", "sz"),
    universe: str = "ashare",
    from_date: date | None = None,
    to_date: date | None = None,
) -> list[dict[str, object]]:
    if export_dir.is_file():
        export_files = {code_from_export_path(export_dir): export_dir}
    else:
        export_files = {
            code_from_export_path(path): path
            for path in iter_export_files(export_dir, markets, universe)
        }
    rows: list[dict[str, object]] = []

    for raw_path in iter_day_files(raw_vipdoc, markets=markets, universe=universe):
        market, symbol = code_from_path(raw_path)
        export_path = export_files.get((market, symbol))
        if export_path is None:
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
            continue

        raw_ratios: list[tuple[date, float]] = []
        for trade_date in common_dates:
            raw_close = raw_records[trade_date].close
            export_close = export_records[trade_date].close
            if raw_close <= 0:
                continue
            raw_ratios.append((trade_date, export_close / raw_close))

        if not raw_ratios:
            continue

        normalized_base = raw_ratios[-1][1]
        if normalized_base <= 0:
            raise ValueError(f"Invalid export normalization base for {market}:{symbol}")

        qfq_rows: list[tuple[date, float]] = []
        for trade_date, raw_ratio in raw_ratios:
            qfq_rows.append((trade_date, round(raw_ratio / normalized_base, 6)))

        first_qfq_factor = qfq_rows[0][1]
        if first_qfq_factor <= 0:
            raise ValueError(f"Invalid export qfq factor base for {market}:{symbol}")

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

    return rows
