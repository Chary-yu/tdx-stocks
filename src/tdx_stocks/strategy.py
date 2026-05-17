from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import AppConfig
from .duckdb_ops import sql_literal
from .exit_codes import NoDataError
from .query import open_query_context

GLOBAL_REQUIRED_FIELDS = ("adj_close", "ma20", "ma60", "ret_5", "ret_20", "amount_ma20")
BREAKOUT_REQUIRED_FIELDS = ("pos_20", "dd_20", "vol_ratio_20")
PULLBACK_REQUIRED_FIELDS = ("dd_20", "atr_pct_14")
DEFAULT_MARKETS = ("sh", "sz")
DEFAULT_LIMIT = 20
DEFAULT_MIN_SCORE = 60.0
DEFAULT_MIN_AMOUNT_MA20 = 50_000_000.0
DEFAULT_SHOW_EXCLUDED_LIMIT = 20

CANDIDATE_TYPE_ORDER = ("breakout_watch", "strong_trend", "pullback_watch")
HARD_REASON_ORDER = (
    "missing_required_factor",
    "insufficient_liquidity",
    "overheated_ret_5",
    "extreme_rsi",
    "excessive_volatility",
)
TAG_ORDER = (
    "breakout_watch",
    "trend_strong",
    "pullback_watch",
    "near_20d_high",
    "volume_expansion",
    "active_amount",
    "ma_bullish",
)
RISK_FLAG_ORDER = (
    "ret_5_strong",
    "rsi_high",
    "mild_volatility",
    "near_20d_high",
    "risk_factor_missing",
)


@dataclass(frozen=True)
class StrategyParams:
    limit: int = DEFAULT_LIMIT
    min_score: float = DEFAULT_MIN_SCORE
    min_amount_ma20: float = DEFAULT_MIN_AMOUNT_MA20
    market: str | None = None
    candidate_type: str | None = None
    include_excluded: bool = False
    show_excluded_limit: int = DEFAULT_SHOW_EXCLUDED_LIMIT
    explain_symbol: str | None = None
    as_of: date | None = None
    to: Path | None = None
    json: bool = False


@dataclass(frozen=True)
class StrategyReport:
    summary: dict[str, object]
    picks: list[dict[str, object]]
    excluded: list[dict[str, object]]
    explain: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "picks": self.picks,
            "excluded": self.excluded,
            "explain": self.explain,
        }


def run_trend_strength_strategy(config: AppConfig, params: StrategyParams) -> StrategyReport:
    ctx = open_query_context(config)
    try:
        manifest = ctx.manifest
        dataset_run_id = str(manifest.get("run_id")) if manifest.get("run_id") is not None else None
        factor_version = _resolve_factor_version(manifest)
        markets = _resolve_markets(config, params)
        requested_as_of = params.as_of
        trade_date = _resolve_as_of_date(ctx.con, markets, requested_as_of)
        execute_date = _resolve_execute_date(ctx.con, markets, trade_date)
        rows = _fetch_strategy_rows(ctx.con, markets, trade_date)
        analyzed_rows = _analyze_rows(rows, params, execute_date, dataset_run_id, factor_version)
        summary = _build_summary(
            analyzed_rows,
            params,
            requested_as_of,
            trade_date,
            execute_date,
            dataset_run_id,
            factor_version,
            markets,
        )
        picks, excluded = _finalize_report_rows(analyzed_rows, params)
        if params.explain_symbol:
            explain = _build_explain(
                ctx.con,
                analyzed_rows,
                params.explain_symbol,
                params,
                trade_date,
                dataset_run_id,
                factor_version,
                execute_date,
            )
        else:
            explain = None
        summary["picked"] = len(picks)
        summary["excluded_returned"] = len(excluded) if params.include_excluded else 0
        return StrategyReport(summary=summary, picks=picks, excluded=excluded, explain=explain)
    finally:
        ctx.close()


def _resolve_factor_version(manifest: dict) -> str | None:
    summary = manifest.get("summary", {})
    if isinstance(summary, dict):
        factor_version = summary.get("factor_version")
        if factor_version is not None:
            return str(factor_version)
    factor_version = manifest.get("factor_version")
    return str(factor_version) if factor_version is not None else None


def _resolve_markets(config: AppConfig, params: StrategyParams) -> tuple[str, ...]:
    if params.market:
        return (params.market,)
    return tuple(config.build.markets) or DEFAULT_MARKETS


def _resolve_as_of_date(con, markets: tuple[str, ...], as_of: date | None) -> date:
    market_clause = _market_clause(markets)
    if as_of is None:
        row = con.execute(
            f"SELECT max(trade_date) FROM factors WHERE {market_clause}"
        ).fetchone()
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


def _resolve_execute_date(con, markets: tuple[str, ...], trade_date: date) -> date | None:
    market_clause = _market_clause(markets)
    row = con.execute(
        f"""
        SELECT min(trade_date)
        FROM adj_daily
        WHERE {market_clause}
            AND trade_date > DATE '{trade_date.isoformat()}'
        """
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _fetch_strategy_rows(con, markets: tuple[str, ...], trade_date: date) -> list[dict[str, Any]]:
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
        "amount_ma20",
        "pos_20",
        "dd_20",
        "vol_ratio_20",
        "rsi_14",
        "atr_pct_14",
        "vol_20",
        "high_20",
        "low_20",
    ]
    sql = f"""
        SELECT {", ".join(columns)}
        FROM factors
        WHERE { _market_clause(markets) }
            AND trade_date = DATE '{trade_date.isoformat()}'
        ORDER BY market, symbol
    """
    result = con.execute(sql)
    rows = [dict(zip((desc[0] for desc in result.description), row, strict=True)) for row in result.fetchall()]
    return rows


def _fetch_strategy_rows_for_symbol(
    con,
    markets: tuple[str, ...],
    trade_date: date,
    symbol: str,
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
        "amount_ma20",
        "pos_20",
        "dd_20",
        "vol_ratio_20",
        "rsi_14",
        "atr_pct_14",
        "vol_20",
        "high_20",
        "low_20",
    ]
    sql = f"""
        SELECT {", ".join(columns)}
        FROM factors
        WHERE {_market_clause(markets)}
            AND trade_date = DATE '{trade_date.isoformat()}'
            AND symbol = '{sql_literal(symbol)}'
        ORDER BY market, symbol
    """
    result = con.execute(sql)
    rows = [dict(zip((desc[0] for desc in result.description), row, strict=True)) for row in result.fetchall()]
    return rows


def _analyze_rows(
    rows: list[dict[str, Any]],
    params: StrategyParams,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
) -> list[dict[str, Any]]:
    analyzed: list[dict[str, Any]] = []
    for row in rows:
        analyzed.append(
            _analyze_row(row, params, execute_date, dataset_run_id, factor_version)
        )
    return analyzed


def _analyze_row(
    row: dict[str, Any],
    params: StrategyParams,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
) -> dict[str, Any]:
    market = str(row["market"])
    symbol = str(row["symbol"])
    display_symbol = _display_symbol(market, symbol)
    trade_date = row["trade_date"]

    hard_reason = _hard_exclusion_reason(row, params)
    if hard_reason is not None:
        return {
            "status": "excluded",
            "trade_date": trade_date,
            "execute_date": execute_date,
            "market": market,
            "symbol": symbol,
            "amount_ma20": _float_or_none(row.get("amount_ma20")),
            "display_symbol": display_symbol,
            "score": None,
            "score_breakdown": None,
            "candidate_type": None,
            "tags": [],
            "priority_weight": None,
            "reasons": [],
            "risk_flags": [],
            "watch_plan": _watch_plan(None, []),
            "dataset_run_id": dataset_run_id,
            "factor_version": factor_version,
            "excluded": True,
            "excluded_reason": hard_reason,
        }

    candidate_type, tags, reasons = _classify_row(row, params)
    risk_flags = _risk_flags(row)
    score_breakdown = _score_breakdown(row, params, risk_flags)
    score = _clamp(score_breakdown["trend"] + score_breakdown["liquidity"] + score_breakdown["position"] + score_breakdown["short_strength"] + score_breakdown["risk_penalty"], 0.0, 100.0)
    score = round(score, 2)
    priority_weight = round(score / 100.0, 4)
    watch_plan = _watch_plan(candidate_type, risk_flags)

    status = "unclassified_filtered"
    excluded = False
    excluded_reason = None
    if candidate_type is not None:
        status = "picked" if score >= params.min_score else "low_score_filtered"

    if candidate_type is None:
        watch_plan = "不满足当前策略候选类型，暂不进入观察池"

    return {
        "status": status,
        "trade_date": trade_date,
        "execute_date": execute_date,
        "market": market,
        "symbol": symbol,
        "amount_ma20": _float_or_none(row.get("amount_ma20")),
        "display_symbol": display_symbol,
        "score": score,
        "score_breakdown": score_breakdown,
        "candidate_type": candidate_type,
        "tags": tags,
        "priority_weight": priority_weight,
        "reasons": reasons,
        "risk_flags": risk_flags,
        "watch_plan": watch_plan,
        "dataset_run_id": dataset_run_id,
        "factor_version": factor_version,
        "excluded": excluded,
        "excluded_reason": excluded_reason,
    }


def _hard_exclusion_reason(row: dict[str, Any], params: StrategyParams) -> str | None:
    if _missing_any(row, GLOBAL_REQUIRED_FIELDS):
        return "missing_required_factor"
    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is None or amount_ma20 < params.min_amount_ma20:
        return "insufficient_liquidity"
    ret_5 = _float_or_none(row.get("ret_5"))
    if ret_5 is not None and ret_5 >= 0.15:
        return "overheated_ret_5"
    rsi_14 = _float_or_none(row.get("rsi_14"))
    if rsi_14 is not None and rsi_14 >= 85:
        return "extreme_rsi"
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    if (atr_pct_14 is not None and atr_pct_14 >= 0.10) or (vol_20 is not None and vol_20 >= 0.08):
        return "excessive_volatility"
    return None


def _classify_row(row: dict[str, Any], params: StrategyParams) -> tuple[str | None, list[str], list[str]]:
    candidate_type: str | None = None
    tags: list[str] = []
    reasons: list[str] = []

    adj_close = _float_or_none(row.get("adj_close"))
    ma20 = _float_or_none(row.get("ma20"))
    ma60 = _float_or_none(row.get("ma60"))
    ret_5 = _float_or_none(row.get("ret_5"))
    ret_20 = _float_or_none(row.get("ret_20"))
    pos_20 = _float_or_none(row.get("pos_20"))
    dd_20 = _float_or_none(row.get("dd_20"))
    vol_ratio_20 = _float_or_none(row.get("vol_ratio_20"))

    strong_trend = (
        adj_close is not None
        and ma20 is not None
        and ma60 is not None
        and ret_20 is not None
        and adj_close > ma20
        and ma20 > ma60
        and ret_20 > 0
    )
    breakout_watch = (
        ret_20 is not None
        and pos_20 is not None
        and dd_20 is not None
        and vol_ratio_20 is not None
        and ret_20 > 0
        and pos_20 >= 0.85
        and dd_20 >= -0.03
        and vol_ratio_20 > 0
    )
    pullback_watch = (
        ma20 is not None
        and ma60 is not None
        and adj_close is not None
        and ret_5 is not None
        and ret_20 is not None
        and dd_20 is not None
        and ma20 > ma60
        and adj_close >= ma20
        and ret_5 <= 0
        and ret_20 > 0
        and dd_20 >= -0.12
    )

    if breakout_watch:
        candidate_type = "breakout_watch"
    elif strong_trend:
        candidate_type = "strong_trend"
    elif pullback_watch:
        candidate_type = "pullback_watch"

    if candidate_type == "breakout_watch":
        tags.extend(["breakout_watch", "trend_strong", "near_20d_high"])
        reasons.extend(["接近20日高点", "量能放大", "趋势延续"])
    elif candidate_type == "strong_trend":
        tags.extend(["trend_strong", "ma_bullish"])
        reasons.extend(["均线多头", "趋势向上", "成交额活跃"])
    elif candidate_type == "pullback_watch":
        tags.extend(["pullback_watch", "ma_bullish"])
        reasons.extend(["中期趋势向上", "短线回踩", "等待企稳"])

    amount_ma20 = _float_or_none(row.get("amount_ma20"))
    if amount_ma20 is not None and amount_ma20 >= params.min_amount_ma20 * 2:
        tags.append("active_amount")
    if vol_ratio_20 is not None and vol_ratio_20 > 0.1:
        tags.append("volume_expansion")

    return candidate_type, _dedupe_preserve_order(tags), reasons


def _risk_flags(row: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    ret_5 = _float_or_none(row.get("ret_5"))
    dd_20 = _float_or_none(row.get("dd_20"))

    if rsi_14 is None or atr_pct_14 is None or vol_20 is None:
        flags.append("risk_factor_missing")
    if ret_5 is not None and ret_5 >= 0.08:
        flags.append("ret_5_strong")
    if rsi_14 is not None and rsi_14 >= 75:
        flags.append("rsi_high")
    if (atr_pct_14 is not None and atr_pct_14 >= 0.05) or (vol_20 is not None and vol_20 >= 0.04):
        flags.append("mild_volatility")
    if dd_20 is not None and dd_20 >= -0.03:
        flags.append("near_20d_high")
    return _dedupe_preserve_order(flags)


def _score_breakdown(row: dict[str, Any], params: StrategyParams, risk_flags: list[str]) -> dict[str, float]:
    adj_close = _float_or_none(row.get("adj_close")) or 0.0
    ma20 = _float_or_none(row.get("ma20")) or 0.0
    ma60 = _float_or_none(row.get("ma60")) or 0.0
    ret_5 = _float_or_none(row.get("ret_5")) or 0.0
    ret_20 = _float_or_none(row.get("ret_20")) or 0.0
    amount_ma20 = _float_or_none(row.get("amount_ma20")) or 0.0
    pos_20 = _float_or_none(row.get("pos_20")) or 0.0
    rsi_14 = _float_or_none(row.get("rsi_14"))
    atr_pct_14 = _float_or_none(row.get("atr_pct_14"))
    vol_20 = _float_or_none(row.get("vol_20"))
    dd_20 = _float_or_none(row.get("dd_20"))

    trend = 0.0
    if adj_close > ma20:
        trend += 15.0
    if ma20 > ma60:
        trend += 10.0
    trend += 10.0 * _clamp(ret_20 / 0.20, 0.0, 1.0)
    trend = round(min(35.0, trend), 2)

    liquidity = round(20.0 * _clamp(amount_ma20 / max(params.min_amount_ma20 * 5.0, 1.0), 0.0, 1.0), 2)
    position = round(20.0 * _clamp(pos_20, 0.0, 1.0), 2)
    short_strength = round(15.0 * _clamp((ret_5 + 0.05) / 0.20, 0.0, 1.0), 2)

    risk_penalty = 0.0
    if "risk_factor_missing" in risk_flags:
        risk_penalty -= 1.0
    if ret_5 >= 0.08:
        risk_penalty -= 4.0
    if rsi_14 is not None and rsi_14 >= 75:
        risk_penalty -= 4.0
    if (atr_pct_14 is not None and atr_pct_14 >= 0.05) or (vol_20 is not None and vol_20 >= 0.04):
        risk_penalty -= 4.0
    if dd_20 is not None and dd_20 >= -0.03:
        risk_penalty -= 2.0
    risk_penalty = round(max(-30.0, risk_penalty), 2)

    return {
        "trend": trend,
        "liquidity": liquidity,
        "position": position,
        "short_strength": short_strength,
        "risk_penalty": risk_penalty,
    }


def _watch_plan(candidate_type: str | None, risk_flags: list[str]) -> str:
    if candidate_type == "breakout_watch":
        plan = "放量突破前高才确认，尾盘回落不追"
    elif candidate_type == "strong_trend":
        plan = "高开过多不追，回踩不破 ma5 或 ma20 再观察"
    elif candidate_type == "pullback_watch":
        plan = "回踩 ma20 企稳再观察，跌破支撑则放弃"
    else:
        plan = "不满足当前策略候选类型，暂不进入观察池"
    if "ret_5_strong" in risk_flags:
        plan += "；短线已有加速，避免追高"
    if "rsi_high" in risk_flags:
        plan += "；RSI 偏高，注意回撤"
    return plan


def _build_summary(
    analyzed_rows: list[dict[str, Any]],
    params: StrategyParams,
    requested_as_of: date | None,
    trade_date: date,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
    markets: tuple[str, ...],
) -> dict[str, object]:
    summary = {
        "strategy": "trend-strength",
        "trade_date": trade_date.isoformat(),
        "execute_date": execute_date.isoformat() if execute_date else None,
        "dataset_run_id": dataset_run_id,
        "factor_version": factor_version,
        "total_scanned": len(analyzed_rows),
        "missing_factor_excluded": 0,
        "liquidity_excluded": 0,
        "risk_excluded": 0,
        "unclassified_filtered": 0,
        "eligible": 0,
        "low_score_filtered": 0,
        "picked": 0,
        "excluded": 0,
        "excluded_returned": 0,
        "candidate_type_filter": params.candidate_type,
        "min_score": params.min_score,
        "min_amount_ma20": params.min_amount_ma20,
        "markets": list(markets),
        "candidate_type_counts": {},
        "tag_counts": {},
        "risk_flag_counts": {},
        "warnings": [],
    }

    eligible_rows = [row for row in analyzed_rows if row["status"] in {"picked", "low_score_filtered"}]
    excluded_rows = [row for row in analyzed_rows if row["status"] == "excluded"]
    summary["eligible"] = len(eligible_rows)
    summary["low_score_filtered"] = sum(1 for row in eligible_rows if row["status"] == "low_score_filtered")
    summary["picked"] = sum(1 for row in eligible_rows if row["status"] == "picked")
    summary["excluded"] = len(excluded_rows)
    summary["missing_factor_excluded"] = sum(1 for row in excluded_rows if row["excluded_reason"] == "missing_required_factor")
    summary["liquidity_excluded"] = sum(1 for row in excluded_rows if row["excluded_reason"] == "insufficient_liquidity")
    summary["risk_excluded"] = sum(
        1 for row in excluded_rows if row["excluded_reason"] in {"overheated_ret_5", "extreme_rsi", "excessive_volatility"}
    )
    summary["unclassified_filtered"] = sum(1 for row in analyzed_rows if row["status"] == "unclassified_filtered")

    if execute_date is None:
        summary["warnings"].append("next trading date not found")

    if requested_as_of is not None and summary["trade_date"] != requested_as_of.isoformat():
        summary["warnings"].append("as_of date is not a trading date; using latest available trade_date <= as_of")

    candidate_counter = Counter(
        row["candidate_type"] for row in eligible_rows if row["candidate_type"] is not None
    )
    tag_counter = Counter(tag for row in eligible_rows for tag in row["tags"])
    risk_counter = Counter(flag for row in eligible_rows for flag in row["risk_flags"])
    summary["candidate_type_counts"] = _ordered_counter(candidate_counter, CANDIDATE_TYPE_ORDER)
    summary["tag_counts"] = _ordered_counter(tag_counter, TAG_ORDER)
    summary["risk_flag_counts"] = _ordered_counter(risk_counter, RISK_FLAG_ORDER)
    return summary


def _finalize_report_rows(
    analyzed_rows: list[dict[str, Any]],
    params: StrategyParams,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    eligible_rows = [row for row in analyzed_rows if row["status"] in {"picked", "low_score_filtered"}]
    filtered_rows = eligible_rows
    if params.candidate_type is not None:
        filtered_rows = [row for row in filtered_rows if row["candidate_type"] == params.candidate_type]

    filtered_rows = sorted(
        filtered_rows,
        key=lambda row: (
            -float(row["score"] or 0.0),
            -float(row["amount_ma20"]) if row.get("amount_ma20") is not None else float("inf"),
            row["market"],
            row["symbol"],
        ),
    )

    picks = [
        _pick_view(row, rank=index + 1)
        for index, row in enumerate(
            row for row in filtered_rows if row["candidate_type"] is not None and row["score"] is not None and float(row["score"]) >= params.min_score
        )
    ]
    picks = picks[: params.limit]

    excluded_rows = [row for row in analyzed_rows if row["status"] == "excluded"]
    excluded_rows = sorted(
        excluded_rows,
        key=lambda row: (
            HARD_REASON_ORDER.index(row["excluded_reason"])
            if row["excluded_reason"] in HARD_REASON_ORDER
            else len(HARD_REASON_ORDER),
            -float(row["score"]) if row["score"] is not None else float("inf"),
            -float(row["amount_ma20"]) if row.get("amount_ma20") is not None else float("inf"),
            row["market"],
            row["symbol"],
        ),
    )
    excluded = []
    if params.include_excluded:
        excluded = [_excluded_view(row) for row in excluded_rows[: params.show_excluded_limit]]

    return picks, excluded


def _build_explain(
    con,
    analyzed_rows: list[dict[str, Any]],
    explain_symbol: str,
    params: StrategyParams,
    trade_date: date,
    dataset_run_id: str | None,
    factor_version: str | None,
    execute_date: date | None,
) -> dict[str, object]:
    symbol_parts = _parse_symbol(explain_symbol)
    matching = []
    for row in analyzed_rows:
        row_market = str(row["market"])
        row_symbol = str(row["symbol"])
        if symbol_parts["market"] is not None:
            if row_market == symbol_parts["market"] and row_symbol == symbol_parts["symbol"]:
                matching.append(row)
        elif row_symbol == symbol_parts["symbol"]:
            matching.append(row)
    if symbol_parts["market"] is None and len({row["market"] for row in matching}) > 1:
        raise ValueError(f"symbol {explain_symbol!r} matches multiple markets; please specify market")
    if not matching and symbol_parts["market"] is not None:
        fetched = _fetch_strategy_rows_for_symbol(
            con,
            (symbol_parts["market"],),
            trade_date,
            symbol_parts["symbol"],
        )
        if fetched:
            matching = [
                _analyze_row(
                    fetched[0],
                    params,
                    execute_date,
                    dataset_run_id,
                    factor_version,
                )
            ]
    if not matching:
        return {
            "status": "not_found",
            "pick": None,
            "excluded_reason": None,
            "message": "symbol not found in the selected strategy universe",
        }
    row = matching[0]
    if row["status"] == "excluded":
        return {
            "status": "excluded",
            "pick": _explain_view(row, dataset_run_id, factor_version, execute_date),
            "excluded_reason": row["excluded_reason"],
            "message": "hard exclusion",
        }
    if row["status"] == "unclassified_filtered":
        return {
            "status": "unclassified_filtered",
            "pick": _explain_view(row, dataset_run_id, factor_version, execute_date),
            "excluded_reason": None,
            "message": "does not match any candidate type",
        }
    if row["score"] is not None and float(row["score"]) < params.min_score:
        return {
            "status": "low_score_filtered",
            "pick": _explain_view(row, dataset_run_id, factor_version, execute_date),
            "excluded_reason": None,
            "message": "score is below min_score",
        }
    return {
        "status": "picked",
        "pick": _explain_view(row, dataset_run_id, factor_version, execute_date),
        "excluded_reason": None,
        "message": "picked into the observation pool",
    }


def _pick_view(row: dict[str, Any], rank: int) -> dict[str, object]:
    return {
        "trade_date": row["trade_date"].isoformat() if hasattr(row["trade_date"], "isoformat") else row["trade_date"],
        "execute_date": row["execute_date"].isoformat() if row["execute_date"] is not None else None,
        "market": row["market"],
        "symbol": row["symbol"],
        "display_symbol": row["display_symbol"],
        "score": row["score"],
        "score_breakdown": row["score_breakdown"],
        "rank": rank,
        "candidate_type": row["candidate_type"],
        "tags": row["tags"],
        "priority_weight": row["priority_weight"],
        "reasons": row["reasons"],
        "risk_flags": row["risk_flags"],
        "watch_plan": row["watch_plan"],
        "dataset_run_id": row["dataset_run_id"],
        "factor_version": row["factor_version"],
        "excluded": row["excluded"],
        "excluded_reason": row["excluded_reason"],
    }


def _excluded_view(row: dict[str, Any]) -> dict[str, object]:
    return {
        "trade_date": row["trade_date"].isoformat() if hasattr(row["trade_date"], "isoformat") else row["trade_date"],
        "execute_date": row["execute_date"].isoformat() if row["execute_date"] is not None else None,
        "market": row["market"],
        "symbol": row["symbol"],
        "display_symbol": row["display_symbol"],
        "score": row["score"],
        "score_breakdown": row["score_breakdown"],
        "candidate_type": row["candidate_type"],
        "tags": row["tags"],
        "priority_weight": row["priority_weight"],
        "reasons": row["reasons"],
        "risk_flags": row["risk_flags"],
        "watch_plan": row["watch_plan"],
        "dataset_run_id": row["dataset_run_id"],
        "factor_version": row["factor_version"],
        "excluded": row["excluded"],
        "excluded_reason": row["excluded_reason"],
    }


def _explain_view(
    row: dict[str, Any],
    dataset_run_id: str | None,
    factor_version: str | None,
    execute_date: date | None,
) -> dict[str, object]:
    return {
        "trade_date": row["trade_date"].isoformat() if hasattr(row["trade_date"], "isoformat") else row["trade_date"],
        "execute_date": execute_date.isoformat() if execute_date is not None else None,
        "market": row["market"],
        "symbol": row["symbol"],
        "display_symbol": row["display_symbol"],
        "score": row["score"],
        "score_breakdown": row["score_breakdown"],
        "candidate_type": row["candidate_type"],
        "tags": row["tags"],
        "priority_weight": row["priority_weight"],
        "reasons": row["reasons"],
        "risk_flags": row["risk_flags"],
        "watch_plan": row["watch_plan"],
        "dataset_run_id": dataset_run_id,
        "factor_version": factor_version,
        "excluded": row["excluded"],
        "excluded_reason": row["excluded_reason"],
    }


def _ordered_counter(counter: Counter[str], order: tuple[str, ...]) -> dict[str, int]:
    ordered: dict[str, int] = {}
    for key in order:
        if key in counter:
            ordered[key] = int(counter[key])
    for key in sorted(counter):
        if key not in ordered:
            ordered[key] = int(counter[key])
    return ordered


def _market_clause(markets: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{sql_literal(market)}'" for market in markets)
    return f"market IN ({quoted})"


def _parse_symbol(value: str) -> dict[str, str | None]:
    text = value.strip()
    if "." in text:
        symbol, market = text.split(".", 1)
        return {"symbol": symbol, "market": market.lower() or None}
    lowered = text.lower()
    if len(text) == 8 and lowered[:2] in {"sh", "sz", "bj"}:
        return {"symbol": text[2:], "market": lowered[:2]}
    return {"symbol": text, "market": None}


def _display_symbol(market: str, symbol: str) -> str:
    return f"{symbol}.{market.upper()}"


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _missing_any(row: dict[str, Any], fields: tuple[str, ...]) -> bool:
    return any(row.get(field) is None for field in fields)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
