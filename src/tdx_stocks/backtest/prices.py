from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class AdjOpenPrice:
    price: float
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_suspended: bool = False


@dataclass(frozen=True)
class AdjDailyPrice:
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    is_limit_up: bool = False
    is_limit_down: bool = False
    is_suspended: bool = False


PriceLike = AdjOpenPrice | dict[str, Any] | float | int
PriceLoader = Callable[[Any, str, str, date], AdjOpenPrice | None]


def load_adj_open_price(con, market: str, symbol: str, trade_date: date) -> AdjOpenPrice | None:
    bar = load_adj_daily_price(con, market, symbol, trade_date)
    if bar is None:
        return None
    return AdjOpenPrice(
        price=bar.open_price,
        is_limit_up=bar.is_limit_up,
        is_limit_down=bar.is_limit_down,
        is_suspended=bar.is_suspended,
    )


def load_adj_daily_price(con, market: str, symbol: str, trade_date: date) -> AdjDailyPrice | None:
    columns = _table_columns(con, "adj_daily")
    high_expr = "adj_high" if "adj_high" in columns else "adj_open"
    low_expr = "adj_low" if "adj_low" in columns else "adj_open"
    close_expr = "adj_close" if "adj_close" in columns else "adj_open"
    volume_expr = "volume" if "volume" in columns else "NULL::BIGINT"
    row = con.execute(
        f"""
        WITH priced AS (
            SELECT
                trade_date,
                adj_open,
                {high_expr} AS adj_high,
                {low_expr} AS adj_low,
                {close_expr} AS adj_close,
                {volume_expr} AS volume,
                lag({close_expr}) OVER (PARTITION BY market, symbol ORDER BY trade_date) AS prev_close
            FROM adj_daily
            WHERE market = ? AND symbol = ? AND trade_date <= ?
        )
        SELECT
            adj_open,
            adj_close,
            adj_high,
            adj_low,
            CASE
                WHEN prev_close IS NOT NULL AND adj_open = adj_high AND adj_close > prev_close * 1.04 THEN TRUE
                ELSE FALSE
            END AS is_limit_up,
            CASE
                WHEN prev_close IS NOT NULL AND adj_open = adj_low AND adj_close < prev_close * 0.96 THEN TRUE
                ELSE FALSE
            END AS is_limit_down,
            CASE WHEN volume = 0 THEN TRUE ELSE FALSE END AS is_suspended
        FROM priced
        WHERE trade_date = ?
        """,
        (market, symbol, trade_date, trade_date),
    ).fetchone()
    if row is None:
        return None
    return AdjDailyPrice(
        open_price=float(row[0]),
        close_price=float(row[1]),
        high_price=float(row[2]),
        low_price=float(row[3]),
        is_limit_up=bool(row[4]),
        is_limit_down=bool(row[5]),
        is_suspended=bool(row[6]),
    )


def coerce_adj_open_price(value: PriceLike | None) -> AdjOpenPrice | None:
    if value is None:
        return None
    if isinstance(value, AdjOpenPrice):
        return value
    if isinstance(value, dict):
        price = value.get("price")
        if price is None:
            return None
        return AdjOpenPrice(
            price=float(price),
            is_limit_up=bool(value.get("is_limit_up", False)),
            is_limit_down=bool(value.get("is_limit_down", False)),
            is_suspended=bool(value.get("is_suspended", False)),
        )
    return AdjOpenPrice(price=float(value))


def coerce_adj_daily_price(value: AdjDailyPrice | dict[str, Any] | None) -> AdjDailyPrice | None:
    if value is None:
        return None
    if isinstance(value, AdjDailyPrice):
        return value
    if isinstance(value, dict):
        open_price = value.get("open_price", value.get("price"))
        close_price = value.get("close_price", open_price)
        high_price = value.get("high_price", open_price)
        low_price = value.get("low_price", open_price)
        if open_price is None or close_price is None or high_price is None or low_price is None:
            return None
        return AdjDailyPrice(
            open_price=float(open_price),
            close_price=float(close_price),
            high_price=float(high_price),
            low_price=float(low_price),
            is_limit_up=bool(value.get("is_limit_up", False)),
            is_limit_down=bool(value.get("is_limit_down", False)),
            is_suspended=bool(value.get("is_suspended", False)),
        )
    return AdjDailyPrice(
        open_price=float(value),
        close_price=float(value),
        high_price=float(value),
        low_price=float(value),
    )


def _table_columns(con, table: str) -> set[str]:
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    return {str(row[0]) for row in rows}


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
