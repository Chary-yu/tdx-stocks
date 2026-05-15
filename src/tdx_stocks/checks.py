from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

from .duckdb_ops import parquet_glob, sql_literal


@dataclass
class CheckResult:
    name: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, int | float | str | None] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return asdict(self)


def check_raw_daily(con, raw_daily_dir: Path) -> CheckResult:
    result = CheckResult(name="raw_daily")
    source = f"read_parquet('{sql_literal(parquet_glob(raw_daily_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            min(trade_date) AS min_date,
            max(trade_date) AS max_date,
            sum(CASE WHEN open <= 0 OR high <= 0 OR low <= 0 OR close <= 0 THEN 1 ELSE 0 END) AS non_positive_price_rows,
            sum(CASE WHEN low > high OR open > high OR close > high OR open < low OR close < low THEN 1 ELSE 0 END) AS invalid_ohlc_rows,
            sum(CASE WHEN volume < 0 OR amount < 0 THEN 1 ELSE 0 END) AS negative_volume_amount_rows
        FROM {source}
        """
    ).fetchone()
    dup_count = con.execute(
        f"""
        SELECT count(*)
        FROM (
            SELECT market, symbol, trade_date, count(*) AS n
            FROM {source}
            GROUP BY 1, 2, 3
            HAVING count(*) > 1
        )
        """
    ).fetchone()[0]

    metrics = {
        "rows": row[0],
        "symbols": row[1],
        "min_date": str(row[2]) if row[2] is not None else None,
        "max_date": str(row[3]) if row[3] is not None else None,
        "non_positive_price_rows": row[4],
        "invalid_ohlc_rows": row[5],
        "negative_volume_amount_rows": row[6],
        "duplicate_key_rows": dup_count,
    }
    result.metrics.update(metrics)

    if metrics["rows"] == 0:
        result.errors.append("raw_daily has no rows")
    if dup_count:
        result.errors.append(f"raw_daily has duplicate primary keys: {dup_count}")
    if metrics["invalid_ohlc_rows"]:
        result.errors.append(f"raw_daily has invalid OHLC rows: {metrics['invalid_ohlc_rows']}")
    if metrics["negative_volume_amount_rows"]:
        result.errors.append(
            f"raw_daily has negative volume/amount rows: {metrics['negative_volume_amount_rows']}"
        )
    if metrics["non_positive_price_rows"]:
        result.warnings.append(
            f"raw_daily has non-positive price rows: {metrics['non_positive_price_rows']}"
        )
    return result


def check_adj_daily(con, adj_daily_dir: Path) -> CheckResult:
    result = CheckResult(name="adj_daily")
    source = f"read_parquet('{sql_literal(parquet_glob(adj_daily_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            sum(CASE WHEN adj_factor <= 0 THEN 1 ELSE 0 END) AS invalid_factor_rows,
            sum(CASE WHEN adj_open <= 0 OR adj_high <= 0 OR adj_low <= 0 OR adj_close <= 0 THEN 1 ELSE 0 END) AS non_positive_price_rows,
            sum(CASE WHEN adj_low > adj_high OR adj_open > adj_high OR adj_close > adj_high OR adj_open < adj_low OR adj_close < adj_low THEN 1 ELSE 0 END) AS invalid_ohlc_rows
        FROM {source}
        """
    ).fetchone()
    result.metrics.update(
        {
            "rows": row[0],
            "symbols": row[1],
            "invalid_factor_rows": row[2],
            "non_positive_price_rows": row[3],
            "invalid_ohlc_rows": row[4],
        }
    )
    if row[0] == 0:
        result.errors.append("adj_daily has no rows")
    if row[2]:
        result.errors.append(f"adj_daily has invalid adj_factor rows: {row[2]}")
    if row[4]:
        result.errors.append(f"adj_daily has invalid OHLC rows: {row[4]}")
    if row[3]:
        result.warnings.append(f"adj_daily has non-positive price rows: {row[3]}")
    return result


def check_factors(con, factors_dir: Path) -> CheckResult:
    result = CheckResult(name="factors")
    source = f"read_parquet('{sql_literal(parquet_glob(factors_dir))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            avg(CASE WHEN pct_chg IS NULL THEN 1.0 ELSE 0.0 END) AS pct_chg_null_ratio,
            sum(CASE WHEN abs(pct_chg) > 0.5 THEN 1 ELSE 0 END) AS extreme_pct_chg_rows
        FROM {source}
        """
    ).fetchone()
    result.metrics.update(
        {
            "rows": row[0],
            "symbols": row[1],
            "pct_chg_null_ratio": row[2],
            "extreme_pct_chg_rows": row[3],
        }
    )
    if row[0] == 0:
        result.errors.append("factors has no rows")
    if row[2] is not None and row[2] > 0.1:
        result.warnings.append(f"pct_chg null ratio is high: {row[2]:.4f}")
    if row[3]:
        result.warnings.append(f"factors has extreme pct_chg rows: {row[3]}")
    return result
