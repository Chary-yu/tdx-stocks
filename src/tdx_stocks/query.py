from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .duckdb_ops import connect_duckdb, parquet_glob, sql_literal

TABLES = ("raw_daily", "adj_daily", "factors", "corporate_actions")
SCALED_COLUMNS = {"volume", "amount"}


@dataclass(frozen=True)
class QueryContext:
    con: object
    manifest: dict

    def close(self) -> None:
        self.con.close()


def load_latest_manifest(data_root: Path) -> dict:
    path = data_root / "latest.json"
    if not path.exists():
        raise FileNotFoundError(f"latest manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def open_query_context(config: AppConfig) -> QueryContext:
    manifest = load_latest_manifest(config.paths.data_root)
    con = connect_duckdb(
        config.paths.data_root / "duckdb" / "tmp",
        config.build.duckdb_memory_limit,
    )
    register_latest_views(con, manifest)
    register_query_macros(con)
    return QueryContext(con=con, manifest=manifest)


def register_latest_views(con, manifest: dict) -> None:
    for table in TABLES:
        path = table_path(manifest, table)
        con.execute(
            f"""
            CREATE OR REPLACE VIEW {table} AS
            SELECT *
            FROM read_parquet('{sql_literal(parquet_glob(path))}', hive_partitioning=true)
            """
        )


def register_query_macros(con) -> None:
    con.execute(
        """
        CREATE OR REPLACE MACRO tdx_symbol_code(input_symbol) AS (
            CASE
                WHEN strpos(CAST(input_symbol AS VARCHAR), '.') > 0
                    THEN split_part(CAST(input_symbol AS VARCHAR), '.', 1)
                WHEN length(CAST(input_symbol AS VARCHAR)) = 8
                    AND substr(lower(CAST(input_symbol AS VARCHAR)), 1, 2) IN ('sh', 'sz', 'bj')
                    THEN substr(CAST(input_symbol AS VARCHAR), 3, 6)
                ELSE CAST(input_symbol AS VARCHAR)
            END
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE MACRO tdx_symbol_market(input_symbol) AS (
            CASE
                WHEN strpos(CAST(input_symbol AS VARCHAR), '.') > 0
                    THEN lower(split_part(CAST(input_symbol AS VARCHAR), '.', 2))
                WHEN length(CAST(input_symbol AS VARCHAR)) = 8
                    AND substr(lower(CAST(input_symbol AS VARCHAR)), 1, 2) IN ('sh', 'sz', 'bj')
                    THEN substr(lower(CAST(input_symbol AS VARCHAR)), 1, 2)
                ELSE NULL
            END
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE MACRO last_n_days(input_symbol, day_count) AS TABLE (
            SELECT *
            FROM adj_daily
            WHERE symbol = tdx_symbol_code(input_symbol)
                AND (
                    tdx_symbol_market(input_symbol) IS NULL
                    OR market = tdx_symbol_market(input_symbol)
                )
            ORDER BY trade_date DESC
            LIMIT CAST(day_count AS BIGINT)
        )
        """
    )
    con.execute(
        """
        CREATE OR REPLACE MACRO last_n_factors(input_symbol, day_count) AS TABLE (
            SELECT *
            FROM factors
            WHERE symbol = tdx_symbol_code(input_symbol)
                AND (
                    tdx_symbol_market(input_symbol) IS NULL
                    OR market = tdx_symbol_market(input_symbol)
                )
            ORDER BY trade_date DESC
            LIMIT CAST(day_count AS BIGINT)
        )
        """
    )


def table_path(manifest: dict, table: str) -> Path:
    validate_table(table)
    value = manifest.get(table)
    if not value:
        raise KeyError(f"manifest does not contain table path: {table}")
    return Path(value)


def validate_table(table: str) -> None:
    if table not in TABLES:
        raise ValueError(f"unknown table {table!r}; expected one of: {', '.join(TABLES)}")


def table_columns(con, table: str) -> list[tuple[str, str]]:
    validate_table(table)
    rows = con.execute(f"DESCRIBE {table}").fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def table_column_names(con, table: str) -> set[str]:
    return {name for name, _type in table_columns(con, table)}


def date_column(con, table: str) -> str | None:
    columns = table_column_names(con, table)
    if "trade_date" in columns:
        return "trade_date"
    if "ex_date" in columns:
        return "ex_date"
    return None


def build_filters(
    con,
    table: str,
    symbol: str | None = None,
    market: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    where: str | None = None,
) -> list[str]:
    columns = table_column_names(con, table)
    filters: list[str] = []
    if symbol:
        if "symbol" not in columns:
            raise ValueError(f"{table} has no symbol column")
        filters.append(f"symbol = '{sql_literal(symbol)}'")
    if market:
        if "market" not in columns:
            raise ValueError(f"{table} has no market column")
        filters.append(f"market = '{sql_literal(market)}'")
    date_col = date_column(con, table)
    if from_date:
        if date_col is None:
            raise ValueError(f"{table} has no date column")
        filters.append(f"{date_col} >= DATE '{sql_literal(from_date)}'")
    if to_date:
        if date_col is None:
            raise ValueError(f"{table} has no date column")
        filters.append(f"{date_col} <= DATE '{sql_literal(to_date)}'")
    if where:
        filters.append(f"({where})")
    return filters


def build_select_sql(
    con,
    table: str,
    columns: Sequence[str] | None = None,
    symbol: str | None = None,
    market: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    where: str | None = None,
    order_by: str | None = None,
    desc: bool = False,
    limit: int | None = None,
) -> str:
    validate_table(table)
    known_columns = table_column_names(con, table)
    if columns:
        unknown = [column for column in columns if column not in known_columns]
        if unknown:
            raise ValueError(f"{table} has no columns: {', '.join(unknown)}")
        select_expr = ", ".join(columns)
    else:
        select_expr = "*"

    filters = build_filters(con, table, symbol, market, from_date, to_date, where)
    sql = [f"SELECT {select_expr}", f"FROM {table}"]
    if filters:
        sql.append("WHERE " + " AND ".join(filters))

    if order_by:
        if order_by not in known_columns:
            raise ValueError(f"{table} has no order-by column: {order_by}")
        sql.append(f"ORDER BY {order_by} {'DESC' if desc else 'ASC'}")
    elif "trade_date" in known_columns:
        sql.append(f"ORDER BY trade_date {'DESC' if desc else 'ASC'}")
    elif "ex_date" in known_columns:
        sql.append(f"ORDER BY ex_date {'DESC' if desc else 'ASC'}")

    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        sql.append(f"LIMIT {limit}")
    return "\n".join(sql)


def build_stock_sql(
    con,
    input_symbol: str,
    from_date: str | None = None,
    to_date: str | None = None,
    order_by: str = "trade_date",
    desc: bool = True,
    limit: int | None = 100,
) -> str:
    code_expr = f"tdx_symbol_code('{sql_literal(input_symbol)}')"
    market_expr = f"tdx_symbol_market('{sql_literal(input_symbol)}')"
    where = [
        f"raw.symbol = {code_expr}",
        f"({market_expr} IS NULL OR raw.market = {market_expr})",
    ]
    if from_date:
        where.append(f"raw.trade_date >= DATE '{sql_literal(from_date)}'")
    if to_date:
        where.append(f"raw.trade_date <= DATE '{sql_literal(to_date)}'")

    sql = [
        "SELECT",
        "    raw.market,",
        "    raw.symbol,",
        "    raw.trade_date,",
        "    raw.trade_year,",
        "    raw.open,",
        "    raw.high,",
        "    raw.low,",
        "    raw.close,",
        "    raw.volume,",
        "    raw.amount,",
        "    adj.adj_open,",
        "    adj.adj_high,",
        "    adj.adj_low,",
        "    adj.adj_close,",
        "    adj.adj_factor,",
        "    factors.pct_chg,",
        "    factors.ma5,",
        "    factors.ma10,",
        "    factors.ma20,",
        "    factors.ma60,",
        "    factors.vol_ma5,",
        "    factors.vol_ma20,",
        "    factors.high_20,",
        "    factors.low_20,",
        "    factors.range_20",
        "FROM raw_daily AS raw",
        "LEFT JOIN adj_daily AS adj USING (market, symbol, trade_date, trade_year)",
        "LEFT JOIN factors USING (market, symbol, trade_date, trade_year)",
        "WHERE " + " AND ".join(where),
    ]
    if order_by not in {"trade_date", "trade_year"}:
        raise ValueError("order_by must be trade_date or trade_year")
    order_target = f"raw.{order_by}"
    sql.append(f"ORDER BY {order_target} {'DESC' if desc else 'ASC'}")
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        sql.append(f"LIMIT {limit}")
    return "\n".join(sql)


def fetch_dicts(con, sql: str) -> tuple[list[str], list[dict]]:
    result = con.execute(sql)
    columns = [description[0] for description in result.description]
    rows = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
    return columns, rows


def print_rows(columns: Sequence[str], rows: Sequence[dict], max_width: int = 28) -> None:
    if not rows:
        print("(no rows)")
        return
    rendered_rows = [
        [format_cell(row.get(column), column=column, max_width=max_width) for column in columns]
        for row in rows
    ]
    widths = [
        min(
            max(len(str(column)), *(len(row[index]) for row in rendered_rows)),
            max_width,
        )
        for index, column in enumerate(columns)
    ]
    header = "  ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns))
    sep = "  ".join("-" * width for width in widths)
    print(header)
    print(sep)
    for row in rendered_rows:
        print("  ".join(row[index].ljust(widths[index]) for index in range(len(columns))))


def format_cell(value, column: str | None = None, max_width: int = 28) -> str:
    if value is None:
        text = "NULL"
    elif isinstance(value, bool):
        text = "TRUE" if value else "FALSE"
    elif isinstance(value, int) and not isinstance(value, bool):
        text = format_scaled_number(float(value)) if should_scale_column(column) else str(value)
    elif isinstance(value, float):
        text = (
            format_scaled_number(value)
            if should_scale_column(column)
            else format_number(value)
        )
    else:
        text = str(value)
    if len(text) > max_width:
        return text[: max_width - 1] + "…"
    return text


def format_number(value: float) -> str:
    text = f"{value:.2f}"
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_scaled_number(value: float) -> str:
    abs_value = abs(value)
    for divisor, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if abs_value >= divisor:
            return f"{format_number(value / divisor)}{suffix}"
    return format_number(value)


def normalize_output_data(data):
    if isinstance(data, dict):
        return {key: normalize_output_data_for_column(value, key) for key, value in data.items()}
    if isinstance(data, list):
        return [normalize_output_data(item) for item in data]
    return data


def normalize_output_data_for_column(value, column: str | None = None):
    if isinstance(value, dict):
        return {key: normalize_output_data_for_column(item, key) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_output_data_for_column(item, column=column) for item in value]
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if should_scale_column(column):
            return format_scaled_number(float(value))
        return value
    if isinstance(value, float):
        if should_scale_column(column):
            return format_scaled_number(value)
        rounded = round(value, 2)
        return int(rounded) if rounded.is_integer() else rounded
    return value


def should_scale_column(column: str | None) -> bool:
    if column is None:
        return False
    lower = column.lower()
    return lower in SCALED_COLUMNS or lower.startswith("vol")


def disk_usage(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def format_bytes(value: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def table_summary(con, manifest: dict, table: str) -> dict:
    validate_table(table)
    columns = table_column_names(con, table)
    metrics = {
        "table": table,
        "rows": con.execute(f"SELECT count(*) FROM {table}").fetchone()[0],
        "disk": format_bytes(disk_usage(table_path(manifest, table))),
        "path": table_path(manifest, table).as_posix(),
    }
    if "symbol" in columns:
        metrics["symbols"] = con.execute(
            f"SELECT count(DISTINCT symbol) FROM {table}"
        ).fetchone()[0]
    date_col = date_column(con, table)
    if date_col:
        min_date, max_date = con.execute(
            f"SELECT min({date_col}), max({date_col}) FROM {table}"
        ).fetchone()
        metrics["min_date"] = str(min_date) if min_date is not None else None
        metrics["max_date"] = str(max_date) if max_date is not None else None
    return metrics


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            count += 1
    return count


def export_query_csv(con, sql: str, path: Path, batch_size: int = 10_000) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = con.execute(sql)
    columns = [description[0] for description in result.description]
    count = 0
    with path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.writer(fp)
        writer.writerow(columns)
        while True:
            batch = result.fetchmany(batch_size)
            if not batch:
                break
            writer.writerows(batch)
            count += len(batch)
    return count
