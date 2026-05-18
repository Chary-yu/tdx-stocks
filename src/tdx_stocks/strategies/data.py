from __future__ import annotations

from datetime import date
from typing import Any

from ..config import AppConfig
from ..exit_codes import NoDataError
from ..duckdb_ops import sql_literal
from ..query import table_column_names
from .base import DEFAULT_MARKETS


def resolve_factor_version(manifest: dict) -> str | None:
    summary = manifest.get("summary", {})
    if isinstance(summary, dict):
        factor_version = summary.get("factor_version")
        if factor_version is not None:
            return str(factor_version)
    factor_version = manifest.get("factor_version")
    return str(factor_version) if factor_version is not None else None


def resolve_markets(config: AppConfig, market: str | None) -> tuple[str, ...]:
    if market:
        return (market,)
    return tuple(config.build.markets) or DEFAULT_MARKETS


def resolve_as_of_date(con, markets: tuple[str, ...], as_of: date | None) -> date:
    market_clause = market_clause_sql(markets)
    if as_of is None:
        row = con.execute(f"SELECT max(trade_date) FROM factors WHERE {market_clause}").fetchone()
    else:
        row = con.execute(
            f"""
            SELECT max(trade_date)
            FROM factors
            WHERE {market_clause}
                AND trade_date <= DATE '{as_of.isoformat()}'
            """
        ).fetchone()
    resolved = row[0] if row else None
    if resolved is None:
        raise NoDataError("no factors rows found for the selected market/date range")
    return resolved


def resolve_execute_date(con, markets: tuple[str, ...], trade_date: date) -> date | None:
    market_clause = market_clause_sql(markets)
    row = con.execute(
        f"""
        SELECT min(trade_date)
        FROM adj_daily
        WHERE {market_clause}
            AND trade_date > DATE '{trade_date.isoformat()}'
        """
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def fetch_strategy_rows(
    con,
    markets: tuple[str, ...],
    trade_date: date,
    *,
    required_fields: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    return _fetch_rows(
        con,
        markets,
        trade_date,
        symbol=None,
        required_fields=required_fields,
    )


def fetch_strategy_rows_for_symbol(
    con,
    markets: tuple[str, ...],
    trade_date: date,
    symbol: str,
    *,
    required_fields: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    return _fetch_rows(con, markets, trade_date, symbol=symbol, required_fields=required_fields)


def _fetch_rows(
    con,
    markets: tuple[str, ...],
    trade_date: date,
    symbol: str | None,
    required_fields: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    columns = [
        "market",
        "symbol",
        "trade_date",
        "adj_close",
        "ma5",
        "ma20",
        "ma60",
        "ret_5",
        "ret_20",
        "ret_60",
        "amount_ma20",
        "pos_20",
        "pos_60",
        "dd_20",
        "vol_ratio_20",
        "rsi_14",
        "atr_pct_14",
        "vol_20",
        "vol_60",
        "high_20",
        "low_20",
    ]
    available_columns = table_column_names(con, "factors")
    missing_columns = [column for column in columns if column not in available_columns]
    missing_required_fields = [column for column in required_fields if column not in available_columns]
    if missing_columns:
        raise ValueError(
            "factors table is missing required columns: "
            + ", ".join(missing_columns)
            + "; rebuild the dataset with a compatible factor version"
        )
    if missing_required_fields:
        raise ValueError(
            "strategy requires factors fields: "
            + ", ".join(missing_required_fields)
            + "; rebuild the dataset with a compatible factor version"
        )
    where_sql = [market_clause_sql(markets), f"trade_date = DATE '{trade_date.isoformat()}'"]
    if symbol is not None:
        where_sql.append(f"symbol = '{sql_literal(symbol)}'")
    sql = f"""
        SELECT {", ".join(columns)}
        FROM factors
        WHERE {" AND ".join(where_sql)}
        ORDER BY market, symbol
    """
    result = con.execute(sql)
    return [
        dict(zip((desc[0] for desc in result.description), row, strict=True))
        for row in result.fetchall()
    ]


def market_clause_sql(markets: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{sql_literal(market)}'" for market in markets)
    return f"market IN ({quoted})"
