from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any


PriceLoader = Callable[[Any, str, str, date], float | None]


def load_adj_open_price(con, market: str, symbol: str, trade_date: date) -> float | None:
    row = con.execute(
        """
        SELECT adj_open
        FROM adj_daily
        WHERE market = ? AND symbol = ? AND trade_date = ?
        """,
        (market, symbol, trade_date),
    ).fetchone()
    return None if row is None else float(row[0])


def load_trading_dates(con, from_date: date, to_date: date, market: str | None = None) -> list[date]:
    where = ["trade_date >= ?", "trade_date <= ?"]
    args: list[object] = [from_date, to_date]
    if market is not None:
        where.append("market = ?")
        args.append(market)
    rows = con.execute(
        f"""
        SELECT DISTINCT trade_date
        FROM factors
        WHERE {" AND ".join(where)}
        ORDER BY trade_date
        """,
        args,
    ).fetchall()
    return [row[0] for row in rows]
