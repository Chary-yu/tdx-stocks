from __future__ import annotations

import re
from dataclasses import dataclass

from ..config import AppConfig
from ..duckdb_ops import sql_literal
from ..pipeline import parse_iso_date
from ..query import open_query_context, table_column_names
from .base import StrategyParams, StrategyReport
from .data import resolve_as_of_date, resolve_execute_date, resolve_factor_version, resolve_markets
from .registry import StrategyDefinition, register_strategy


@dataclass(frozen=True)
class PairsParams(StrategyParams):
    symbols: tuple[str, ...] = ()
    lookback: int = 20
    zscore_threshold: float = 2.0
    max_pairs: int = 10

    def to_dict(self) -> dict[str, object]:
        payload = super().to_dict()
        payload["symbols"] = list(self.symbols)
        payload["lookback"] = self.lookback
        payload["zscore_threshold"] = self.zscore_threshold
        payload["max_pairs"] = self.max_pairs
        return payload


_PAIR_CODE_RE = re.compile(r"^\d{6}$")
_PAIR_PREFIX_RE = re.compile(r"^(sh|sz|bj)(\d{6})$", re.IGNORECASE)
_PAIR_SUFFIX_RE = re.compile(r"^(\d{6})\.(sh|sz|bj)$", re.IGNORECASE)


def _normalize_pair_symbol(symbol: str) -> str:
    value = str(symbol).strip()
    if not value:
        raise ValueError("pairs strategy symbol cannot be empty")
    if _PAIR_CODE_RE.fullmatch(value):
        return value
    prefix_match = _PAIR_PREFIX_RE.fullmatch(value)
    if prefix_match is not None:
        return prefix_match.group(2)
    suffix_match = _PAIR_SUFFIX_RE.fullmatch(value)
    if suffix_match is not None:
        return suffix_match.group(1)
    raise ValueError(
        "invalid pairs strategy symbol "
        f"{symbol!r}; expected a 6-digit code, sh600519, or 600519.SH"
    )


def _safe_in_list(symbols: tuple[str, ...]) -> str:
    normalized = [_normalize_pair_symbol(symbol) for symbol in symbols]
    if not normalized:
        raise ValueError("pairs strategy requires at least one valid symbol")
    return ", ".join(f"'{sql_literal(symbol)}'" for symbol in normalized)


def _build_params(args) -> PairsParams:
    raw_symbols = tuple(
        item.strip()
        for item in str(getattr(args, "symbols", "") or "").split(",")
        if item.strip()
    )
    symbols = tuple(_normalize_pair_symbol(item) for item in raw_symbols)
    return PairsParams(
        limit=args.limit,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
        market=args.market,
        candidate_type=args.candidate_type,
        include_excluded=args.include_excluded,
        show_excluded_limit=args.show_excluded_limit,
        explain_symbol=args.explain_symbol,
        as_of=parse_iso_date(args.as_of),
        symbols=symbols,
        lookback=int(getattr(args, "lookback", 20)),
        zscore_threshold=float(getattr(args, "zscore_threshold", 2.0)),
        max_pairs=int(getattr(args, "max_pairs", 10)),
    )


def _add_arguments(parser) -> None:
    parser.add_argument("--symbols", required=True, help="Comma-separated pair pool symbols.")
    parser.add_argument("--lookback", type=int, default=20)
    parser.add_argument("--zscore-threshold", type=float, default=2.0)
    parser.add_argument("--max-pairs", type=int, default=10)


def run_pairs_strategy(config: AppConfig, params: PairsParams) -> StrategyReport:
    open_context = open_query_context
    ctx = open_context(config)
    try:
        markets = resolve_markets(config, params.market)
        trade_date = resolve_as_of_date(ctx.con, markets, params.as_of)
        execute_date = resolve_execute_date(ctx.con, markets, trade_date)
        factor_version = resolve_factor_version(ctx.manifest)
        source_table = "factor_full" if _table_exists(ctx.con, "factor_full") else "factors"
        rows = _load_pairs(ctx.con, source_table, markets, trade_date, params)
        summary = {
            "strategy": "pairs-arb",
            "trade_date": trade_date.isoformat(),
            "execute_date": execute_date.isoformat() if execute_date else None,
            "pairs_pool_size": len(params.symbols),
            "pairs_hit_count": len(rows) // 2,
            "picked": len(rows),
            "excluded": 0,
            "excluded_returned": 0,
            "lookback": params.lookback,
            "zscore_threshold": params.zscore_threshold,
            "dataset_run_id": str(ctx.manifest.get("run_id")) if ctx.manifest.get("run_id") is not None else None,
            "factor_version": factor_version,
        }
        picks = rows[: params.limit]
        return StrategyReport(summary=summary, picks=picks, excluded=[], explain=None)
    finally:
        ctx.close()


def _load_pairs(con, source_table: str, markets: tuple[str, ...], trade_date, params: PairsParams) -> list[dict[str, object]]:
    symbols = list(params.symbols)
    if len(symbols) < 2:
        raise ValueError("pairs strategy requires at least two symbols")
    symbol_list = _safe_in_list(tuple(symbols))
    market_list = ", ".join(f"'{sql_literal(market)}'" for market in markets)
    sql = f"""
        WITH pool AS (
            SELECT
                market,
                symbol,
                trade_date,
                adj_close
            FROM {source_table}
            WHERE market IN ({market_list})
                AND symbol IN ({symbol_list})
                AND trade_date <= DATE '{trade_date.isoformat()}'
        ),
        pair_series AS (
            SELECT
                a.trade_date,
                a.market,
                a.symbol AS long_symbol,
                b.symbol AS peer_symbol,
                a.adj_close / NULLIF(b.adj_close, 0) AS ratio,
                row_number() OVER (
                    PARTITION BY a.symbol, b.symbol
                    ORDER BY a.trade_date DESC
                ) AS rn_desc,
                avg(a.adj_close / NULLIF(b.adj_close, 0)) OVER (
                    PARTITION BY a.symbol, b.symbol
                    ORDER BY a.trade_date
                    ROWS BETWEEN {params.lookback - 1} PRECEDING AND CURRENT ROW
                ) AS ratio_mean,
                stddev_samp(a.adj_close / NULLIF(b.adj_close, 0)) OVER (
                    PARTITION BY a.symbol, b.symbol
                    ORDER BY a.trade_date
                    ROWS BETWEEN {params.lookback - 1} PRECEDING AND CURRENT ROW
                ) AS ratio_std
            FROM pool a
            JOIN pool b
                ON a.trade_date = b.trade_date
                AND a.market = b.market
                AND a.symbol < b.symbol
        ),
        latest AS (
            SELECT
                *,
                CASE
                    WHEN ratio_std IS NULL OR ratio_std = 0 THEN NULL
                    ELSE (ratio - ratio_mean) / ratio_std
                END AS zscore
            FROM pair_series
            WHERE rn_desc = 1
        )
        SELECT *
        FROM latest
        WHERE zscore IS NOT NULL
            AND abs(zscore) >= {params.zscore_threshold}
        ORDER BY abs(zscore) DESC, long_symbol, peer_symbol
        LIMIT {params.max_pairs}
    """
    result = con.execute(sql)
    rows = [dict(zip((desc[0] for desc in result.description), row, strict=True)) for row in result.fetchall()]
    picks: list[dict[str, object]] = []
    for index, row in enumerate(rows):
        ratio = float(row["ratio"])
        zscore = float(row["zscore"])
        overvalued_symbol = str(row["long_symbol"]) if zscore > 0 else str(row["peer_symbol"])
        undervalued_symbol = str(row["peer_symbol"]) if zscore > 0 else str(row["long_symbol"])
        market = str(row["market"]).lower()
        pair_id = f"{row['long_symbol']}_{row['peer_symbol']}_{row['trade_date']}"
        picks.append(
            {
                "rank": index * 2,
                "market": market,
                "symbol": overvalued_symbol,
                "display_symbol": f"{overvalued_symbol}.{market.upper()}",
                "score": round(abs(zscore) * 10.0, 2),
                "candidate_type": "pair_short",
                "direction": "SHORT",
                "pair_id": pair_id,
                "peer_symbol": undervalued_symbol,
                "ratio": round(ratio, 6),
                "zscore": round(zscore, 6),
            }
        )
        picks.append(
            {
                "rank": index * 2 + 1,
                "market": market,
                "symbol": undervalued_symbol,
                "display_symbol": f"{undervalued_symbol}.{market.upper()}",
                "score": round(abs(zscore) * 10.0, 2),
                "candidate_type": "pair_long",
                "direction": "LONG",
                "pair_id": pair_id,
                "peer_symbol": overvalued_symbol,
                "ratio": round(ratio, 6),
                "zscore": round(zscore, 6),
            }
        )
    return picks


def _table_exists(con, table: str) -> bool:
    try:
        table_column_names(con, table)
    except Exception:
        return False
    return True


register_strategy(
    StrategyDefinition(
        name="pairs-arb",
        display_name="Pairs Arb",
        description="Generate a pairs-trading long/short signal set.",
        runner=run_pairs_strategy,
        group="pair",
        style="market_neutral",
        aliases=("pairs", "stat-arb"),
        required_fields=("adj_close",),
        default_params=PairsParams(),
        param_schema={
            "symbols": {"type": "list[str]", "description": "Pair universe symbols."},
            "lookback": {"type": "int", "description": "Rolling ratio lookback window."},
            "zscore_threshold": {"type": "float", "description": "Absolute z-score threshold."},
            "max_pairs": {"type": "int", "description": "Maximum pair rows to emit."},
        },
        candidate_types=("pair_short", "pair_long"),
        risk_tags=("pair_spread_risk",),
        introduced_in="0.5.0",
        add_arguments=_add_arguments,
        params_builder=_build_params,
    )
)
