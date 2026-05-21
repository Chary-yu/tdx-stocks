
from __future__ import annotations

from datetime import date
from typing import Any

from ..config import AppConfig
from ..query import open_query_context


def collect_market_indicators(config: AppConfig, as_of: date | str | None = None) -> dict[str, Any]:
    try:
        ctx = open_query_context(config)
    except Exception:
        return {}
    try:
        return collect_market_indicators_from_connection(ctx.con, as_of=as_of)
    finally:
        try:
            ctx.close()
        except Exception:
            pass


def collect_market_indicators_from_connection(con: Any, as_of: date | str | None = None) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if not hasattr(con, "execute"):
        return values
    trade_date = _latest_trade_date(con, as_of)
    if trade_date is None:
        return values
    values["trade_date"] = str(trade_date)[:10]
    breadth = _market_breadth(con, trade_date)
    if breadth is not None:
        values["market_breadth"] = breadth
    ma_state = _index_ma_state(con, trade_date)
    values.update(ma_state)
    return values


def _latest_trade_date(con: Any, as_of: date | str | None) -> Any | None:
    try:
        if as_of in (None, "latest"):
            row = con.execute("SELECT MAX(trade_date) FROM adj_daily").fetchone()
        else:
            row = con.execute("SELECT MAX(trade_date) FROM adj_daily WHERE trade_date <= ?", (str(as_of)[:10],)).fetchone()
        return row[0] if row else None
    except Exception:
        return None


def _market_breadth(con: Any, trade_date: Any) -> float | None:
    sql = """
    WITH prev AS (
      SELECT market, symbol, trade_date, adj_close,
             LAG(adj_close) OVER (PARTITION BY market, symbol ORDER BY trade_date) AS prev_close
      FROM adj_daily
      WHERE trade_date <= ?
    )
    SELECT AVG(CASE WHEN adj_close > prev_close THEN 1.0 ELSE 0.0 END)
    FROM prev
    WHERE trade_date = ? AND prev_close IS NOT NULL
    """
    try:
        row = con.execute(sql, (trade_date, trade_date)).fetchone()
        if row and row[0] is not None:
            return round(float(row[0]), 6)
    except Exception:
        return None
    return None


def _index_ma_state(con: Any, trade_date: Any) -> dict[str, Any]:
    # Prefer explicit index rows when present. If the local dataset does not contain
    # benchmark/index rows, leave the fields absent and let macro_filter fail closed.
    sql = """
    SELECT adj_close,
           AVG(adj_close) OVER (ORDER BY trade_date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
           AVG(adj_close) OVER (ORDER BY trade_date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60
    FROM adj_daily
    WHERE symbol IN ('000300', '000985', '399317') AND trade_date <= ?
    QUALIFY trade_date = ?
    LIMIT 1
    """
    try:
        row = con.execute(sql, (trade_date, trade_date)).fetchone()
        if row and row[0] is not None:
            close, ma20, ma60 = row
            return {
                "index_close": float(close),
                "index_ma20": float(ma20) if ma20 is not None else None,
                "index_ma60": float(ma60) if ma60 is not None else None,
            }
    except Exception:
        return {}
    return {}
