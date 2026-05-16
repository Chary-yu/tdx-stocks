from __future__ import annotations

import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DAY_RECORD_SIZE = 32
DAY_RECORD = struct.Struct("<IIIIIfII")


@dataclass(frozen=True)
class DayRecord:
    market: str
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    amount: float
    volume: int

    @property
    def trade_year(self) -> int:
        return self.trade_date.year


def parse_tdx_date(value: int) -> date:
    year = value // 10000
    month = value // 100 % 100
    day = value % 100
    return date(year, month, day)


def code_from_path(path: Path) -> tuple[str, str]:
    stem = path.stem.lower()
    if len(stem) < 8:
        raise ValueError(f"Invalid TDX day filename: {path.name}")
    market = stem[:2]
    symbol = stem[2:]
    if market not in {"sh", "sz", "bj"} or len(symbol) != 6 or not symbol.isdigit():
        raise ValueError(f"Invalid TDX day filename: {path.name}")
    return market, symbol


def is_a_share_symbol(market: str, symbol: str) -> bool:
    if market == "sh":
        return symbol.startswith(("600", "601", "603", "605", "688", "689"))
    if market == "sz":
        return symbol.startswith(("000", "001", "002", "003", "300", "301"))
    if market == "bj":
        return symbol.startswith(("43", "83", "87", "88", "92"))
    return False


def iter_day_files(
    vipdoc: Path,
    markets: Iterable[str] = ("sh", "sz"),
    universe: str = "ashare",
) -> Iterator[Path]:
    for market in markets:
        lday_dir = vipdoc / market / "lday"
        if not lday_dir.exists():
            continue
        for path in sorted(lday_dir.glob(f"{market}[0-9][0-9][0-9][0-9][0-9][0-9].day")):
            file_market, symbol = code_from_path(path)
            if universe == "ashare" and not is_a_share_symbol(file_market, symbol):
                continue
            if universe not in {"ashare", "all"}:
                raise ValueError(f"Unsupported universe: {universe}")
            yield path


def read_day_records(
    path: Path,
    from_date: date | None = None,
    to_date: date | None = None,
) -> Iterator[DayRecord]:
    market, symbol = code_from_path(path)
    data = path.read_bytes()
    usable_size = len(data) - (len(data) % DAY_RECORD_SIZE)

    for offset in range(0, usable_size, DAY_RECORD_SIZE):
        raw_date, raw_open, raw_high, raw_low, raw_close, amount, volume, _reserved = (
            DAY_RECORD.unpack_from(data, offset)
        )
        trade_date = parse_tdx_date(raw_date)
        if from_date is not None and trade_date < from_date:
            continue
        if to_date is not None and trade_date > to_date:
            continue
        yield DayRecord(
            market=market,
            symbol=symbol,
            trade_date=trade_date,
            open=raw_open / 100.0,
            high=raw_high / 100.0,
            low=raw_low / 100.0,
            close=raw_close / 100.0,
            amount=float(amount),
            volume=int(volume),
        )
