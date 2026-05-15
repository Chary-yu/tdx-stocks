from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .tdx_day import DayRecord


def _import_pyarrow():
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "pyarrow is required for Parquet writes. Install project dependencies first."
        ) from exc
    return pa, pq


def raw_daily_schema():
    pa, _pq = _import_pyarrow()
    return pa.schema(
        [
            ("market", pa.string()),
            ("symbol", pa.string()),
            ("trade_date", pa.date32()),
            ("trade_year", pa.int16()),
            ("open", pa.float64()),
            ("high", pa.float64()),
            ("low", pa.float64()),
            ("close", pa.float64()),
            ("volume", pa.int64()),
            ("amount", pa.float64()),
        ]
    )


def corporate_actions_schema():
    pa, _pq = _import_pyarrow()
    return pa.schema(
        [
            ("market", pa.string()),
            ("symbol", pa.string()),
            ("ex_date", pa.date32()),
            ("cash_dividend", pa.float64()),
            ("bonus_share", pa.float64()),
            ("transfer_share", pa.float64()),
            ("allotment_share", pa.float64()),
            ("allotment_price", pa.float64()),
            ("source", pa.string()),
        ]
    )


class RawDailyWriter:
    def __init__(self, root_path: Path, compression: str = "zstd", batch_rows: int = 200_000):
        self.root_path = root_path
        self.compression = compression
        self.batch_rows = batch_rows
        self._batch_id = 0
        self._rows: list[DayRecord] = []
        self.rows_written = 0

    def add_many(self, records: Iterable[DayRecord]) -> None:
        for record in records:
            self._rows.append(record)
            if len(self._rows) >= self.batch_rows:
                self.flush()

    def flush(self) -> None:
        if not self._rows:
            return
        pa, pq = _import_pyarrow()
        schema = raw_daily_schema()
        table = pa.Table.from_pydict(
            {
                "market": [r.market for r in self._rows],
                "symbol": [r.symbol for r in self._rows],
                "trade_date": [r.trade_date for r in self._rows],
                "trade_year": [r.trade_year for r in self._rows],
                "open": [r.open for r in self._rows],
                "high": [r.high for r in self._rows],
                "low": [r.low for r in self._rows],
                "close": [r.close for r in self._rows],
                "volume": [r.volume for r in self._rows],
                "amount": [r.amount for r in self._rows],
            },
            schema=schema,
        )
        self.root_path.mkdir(parents=True, exist_ok=True)
        pq.write_to_dataset(
            table,
            root_path=self.root_path,
            partition_cols=["trade_year", "market"],
            compression=self.compression,
            basename_template=f"part-{self._batch_id:06d}-{{i}}.parquet",
        )
        self.rows_written += len(self._rows)
        self._rows.clear()
        self._batch_id += 1

    def close(self) -> None:
        self.flush()


def write_empty_corporate_actions(root_path: Path, compression: str = "zstd") -> None:
    pa, pq = _import_pyarrow()
    root_path.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_arrays(
        [pa.array([], type=field.type) for field in corporate_actions_schema()],
        schema=corporate_actions_schema(),
    )
    pq.write_table(table, root_path / "empty.parquet", compression=compression)
