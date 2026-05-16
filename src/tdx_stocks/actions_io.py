from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ActionInputs:
    corporate_actions: Path | None = None
    adjustment_factors: Path | None = None


def resolve_action_inputs(path: Path | None) -> ActionInputs:
    if path is None:
        return ActionInputs()
    if path.is_file():
        stem = path.stem.lower()
        if "factor" in stem:
            return ActionInputs(adjustment_factors=path)
        return ActionInputs(corporate_actions=path)

    if not path.exists():
        raise FileNotFoundError(f"input path does not exist: {path}")

    actions = first_existing(
        path,
        (
            "corporate_actions.csv",
            "actions.csv",
            "corporate_actions.parquet",
            "actions.parquet",
        ),
    )
    factors = first_existing(
        path,
        (
            "adjustment_factors.csv",
            "factors.csv",
            "adjustment_factors.parquet",
            "factors.parquet",
        ),
    )
    return ActionInputs(corporate_actions=actions, adjustment_factors=factors)


def first_existing(root: Path, names: tuple[str, ...]) -> Path | None:
    for name in names:
        candidate = root / name
        if candidate.exists():
            return candidate
    return None


def load_corporate_action_rows(path: Path) -> list[dict[str, Any]]:
    rows = list(read_rows(path))
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "market": parse_str(row, "market"),
                "symbol": parse_str(row, "symbol"),
                "ex_date": parse_date(row, "ex_date"),
                "category": parse_int(row, "category", default=1),
                "cash_dividend": parse_float(row, "cash_dividend", default=0.0),
                "stock_dividend": parse_float(row, "stock_dividend", default=0.0),
                "allotment_share": parse_float(row, "allotment_share", default=0.0),
                "allotment_price": parse_float(row, "allotment_price", default=0.0),
                "raw_c1": parse_float(row, "raw_c1", default=0.0),
                "raw_c2": parse_float(row, "raw_c2", default=0.0),
                "raw_c3": parse_float(row, "raw_c3", default=0.0),
                "raw_c4": parse_float(row, "raw_c4", default=0.0),
                "source": parse_str(row, "source", default=str(path)),
            }
        )
    return normalized


def load_adjustment_factor_rows(path: Path) -> list[dict[str, Any]]:
    rows = list(read_rows(path))
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            {
                "market": parse_str(row, "market"),
                "symbol": parse_str(row, "symbol"),
                "trade_date": parse_date(row, "trade_date"),
                "start_date": parse_date(row, "start_date"),
                "end_date": parse_date(row, "end_date"),
                "qfq_factor": parse_float(row, "qfq_factor", default=1.0),
                "hfq_factor": parse_float(row, "hfq_factor", default=1.0),
                "source": parse_str(row, "source", default=str(path)),
            }
        )
    return normalized


def read_rows(path: Path):
    if path.suffix.lower() == ".parquet":
        yield from read_parquet_rows(path)
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        yield from reader


def read_parquet_rows(path: Path):
    try:
        import pyarrow.parquet as pq
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("pyarrow is required to read Parquet inputs") from exc
    table = pq.read_table(path)
    yield from table.to_pylist()


def parse_str(row: dict[str, Any], key: str, default: str = "") -> str:
    value = row.get(key)
    if value is None or value == "":
        return default
    return str(value)


def parse_date(row: dict[str, Any], key: str) -> date | None:
    value = row.get(key)
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def parse_float(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = row.get(key)
    if value is None or value == "":
        return default
    return float(value)


def parse_int(row: dict[str, Any], key: str, default: int = 0) -> int:
    value = row.get(key)
    if value is None or value == "":
        return default
    return int(value)
