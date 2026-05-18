from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Callable

from ...config import AppConfig
from ...query import open_query_context
from ..base import (
    CANDIDATE_TYPE_ORDER,
    HARD_REASON_ORDER,
    RISK_FLAG_ORDER,
    TAG_ORDER,
    StrategyParams,
    StrategyReport,
)
from ..data import (
    fetch_strategy_rows,
    fetch_strategy_rows_for_symbol,
    resolve_as_of_date,
    resolve_execute_date,
    resolve_factor_version,
    resolve_markets,
)
from ..registry import StrategyDefinition, get_strategy, register_strategy
from ..scoring import build_trend_score_breakdown
from ..signals import build_trend_risk_flags, build_trend_watch_plan, classify_trend_candidate
from ..universe import display_symbol, float_or_none, hard_exclusion_reason

OpenQueryContextFn = Callable[[AppConfig], Any]


def run_trend_strength_strategy(
    config: AppConfig,
    params: StrategyParams,
    *,
    open_query_context_fn: OpenQueryContextFn | None = None,
    strategy_name: str = "trend-strength",
    preset_candidate_type: str | None = None,
) -> StrategyReport:
    open_context = open_query_context_fn or open_query_context
    definition = get_strategy(strategy_name)
    required_fields = definition.required_fields
    ctx = open_context(config)
    try:
        manifest = ctx.manifest
        dataset_run_id = str(manifest.get("run_id")) if manifest.get("run_id") is not None else None
        factor_version = resolve_factor_version(manifest)
        markets = resolve_markets(config, params.market)
        effective_candidate_type = params.candidate_type or preset_candidate_type
        requested_as_of = params.as_of
        trade_date = resolve_as_of_date(ctx.con, markets, requested_as_of)
        execute_date = resolve_execute_date(ctx.con, markets, trade_date)
        rows = fetch_strategy_rows(
            ctx.con,
            markets,
            trade_date,
            required_fields=required_fields,
        )
        analyzed_rows = _analyze_rows(rows, params, execute_date, dataset_run_id, factor_version, strategy_name)
        summary = _build_summary(
            analyzed_rows,
            params,
            effective_candidate_type,
            requested_as_of,
            trade_date,
            execute_date,
            dataset_run_id,
            factor_version,
            markets,
            strategy_name,
        )
        picks, excluded = _finalize_report_rows(analyzed_rows, params, effective_candidate_type)
        if params.explain_symbol:
            explain = _build_explain(
                ctx.con,
                analyzed_rows,
                params.explain_symbol,
                params,
                effective_candidate_type,
                trade_date,
                dataset_run_id,
                factor_version,
                execute_date,
                strategy_name,
                required_fields,
            )
        else:
            explain = None
        summary["picked"] = len(picks)
        summary["excluded_returned"] = len(excluded) if params.include_excluded else 0
        return StrategyReport(summary=summary, picks=picks, excluded=excluded, explain=explain)
    finally:
        ctx.close()


def _analyze_rows(
    rows: list[dict[str, Any]],
    params: StrategyParams,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
    strategy_name: str,
) -> list[dict[str, Any]]:
    return [
        _analyze_row(row, params, execute_date, dataset_run_id, factor_version, strategy_name)
        for row in rows
    ]


def _analyze_row(
    row: dict[str, Any],
    params: StrategyParams,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
    strategy_name: str,
) -> dict[str, Any]:
    market = str(row["market"])
    symbol = str(row["symbol"])
    display_symbol_value = display_symbol(market, symbol)
    trade_date = row["trade_date"]

    hard_reason = hard_exclusion_reason(row, params)
    if hard_reason is not None:
        return {
            "status": "excluded",
            "trade_date": trade_date,
            "execute_date": execute_date,
            "market": market,
            "symbol": symbol,
            "amount_ma20": float_or_none(row.get("amount_ma20")),
            "display_symbol": display_symbol_value,
            "score": None,
            "score_breakdown": None,
            "candidate_type": None,
            "tags": [],
            "priority_weight": None,
            "reasons": [],
            "risk_flags": [],
            "watch_plan": build_trend_watch_plan(None, [], strategy_name=strategy_name),
            "dataset_run_id": dataset_run_id,
            "factor_version": factor_version,
            "excluded": True,
            "excluded_reason": hard_reason,
        }

    candidate_type, tags, reasons = classify_trend_candidate(row, params, strategy_name=strategy_name)
    risk_flags = build_trend_risk_flags(row, strategy_name=strategy_name)
    score_breakdown = build_trend_score_breakdown(
        row,
        params.min_amount_ma20,
        risk_flags,
        strategy_name=strategy_name,
    )
    if strategy_name == "low-vol-breakout":
        score = _clamp(
            score_breakdown["trend"]
            + score_breakdown["breakout"]
            + score_breakdown["low_volatility"]
            + score_breakdown["liquidity"]
            + score_breakdown["risk_penalty"],
            0.0,
            100.0,
        )
    elif strategy_name == "ma-pullback":
        score = _clamp(
            score_breakdown["trend"]
            + score_breakdown["pullback"]
            + score_breakdown["liquidity"]
            + score_breakdown["risk_penalty"],
            0.0,
            100.0,
        )
    elif strategy_name == "relative-strength":
        score = _clamp(
            score_breakdown["trend"]
            + score_breakdown["momentum"]
            + score_breakdown["position"]
            + score_breakdown["liquidity"]
            + score_breakdown["risk_penalty"],
            0.0,
            100.0,
        )
    elif strategy_name == "volume-breakout":
        score = _clamp(
            score_breakdown["trend"]
            + score_breakdown["breakout"]
            + score_breakdown["volume"]
            + score_breakdown["liquidity"]
            + score_breakdown["risk_penalty"],
            0.0,
            100.0,
        )
    else:
        score = _clamp(
            score_breakdown["trend"]
            + score_breakdown["liquidity"]
            + score_breakdown["position"]
            + score_breakdown["short_strength"]
            + score_breakdown["risk_penalty"],
            0.0,
            100.0,
        )
    score = round(score, 2)
    priority_weight = round(score / 100.0, 4)
    watch_plan = build_trend_watch_plan(candidate_type, risk_flags, strategy_name=strategy_name)

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
        "amount_ma20": float_or_none(row.get("amount_ma20")),
        "display_symbol": display_symbol_value,
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


def _build_summary(
    analyzed_rows: list[dict[str, Any]],
    params: StrategyParams,
    candidate_type_filter: str | None,
    requested_as_of: date | None,
    trade_date: date,
    execute_date: date | None,
    dataset_run_id: str | None,
    factor_version: str | None,
    markets: tuple[str, ...],
    strategy_name: str,
) -> dict[str, object]:
    summary = {
        "strategy": strategy_name,
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
        "candidate_type_filter": candidate_type_filter,
        "min_score": params.min_score,
        "min_amount_ma20": params.min_amount_ma20,
        "markets": list(markets),
        "candidate_type_counts": {},
        "tag_counts": {},
        "risk_flag_counts": {},
        "warnings": [],
    }

    eligible_rows = [row for row in analyzed_rows if row["status"] in {"picked", "low_score_filtered"}]
    if candidate_type_filter is not None:
        eligible_rows = [row for row in eligible_rows if row["candidate_type"] == candidate_type_filter]
    excluded_rows = [row for row in analyzed_rows if row["status"] == "excluded"]
    summary["eligible"] = len(eligible_rows)
    summary["low_score_filtered"] = sum(1 for row in eligible_rows if row["status"] == "low_score_filtered")
    summary["picked"] = sum(1 for row in eligible_rows if row["status"] == "picked")
    summary["excluded"] = len(excluded_rows)
    summary["missing_factor_excluded"] = sum(
        1 for row in excluded_rows if row["excluded_reason"] == "missing_required_factor"
    )
    summary["liquidity_excluded"] = sum(
        1 for row in excluded_rows if row["excluded_reason"] == "insufficient_liquidity"
    )
    summary["risk_excluded"] = sum(
        1 for row in excluded_rows if row["excluded_reason"] in {"overheated_ret_5", "extreme_rsi", "excessive_volatility"}
    )
    summary["unclassified_filtered"] = sum(1 for row in analyzed_rows if row["status"] == "unclassified_filtered")

    if execute_date is None:
        summary["warnings"].append("next trading date not found")
    if requested_as_of is not None and summary["trade_date"] != requested_as_of.isoformat():
        summary["warnings"].append("as_of date is not a trading date; using latest available trade_date <= as_of")

    candidate_counter = Counter(row["candidate_type"] for row in eligible_rows if row["candidate_type"] is not None)
    tag_counter = Counter(tag for row in eligible_rows for tag in row["tags"])
    risk_counter = Counter(flag for row in eligible_rows for flag in row["risk_flags"])
    summary["candidate_type_counts"] = _ordered_counter(candidate_counter, CANDIDATE_TYPE_ORDER)
    summary["tag_counts"] = _ordered_counter(tag_counter, TAG_ORDER)
    summary["risk_flag_counts"] = _ordered_counter(risk_counter, RISK_FLAG_ORDER)
    return summary


def _finalize_report_rows(
    analyzed_rows: list[dict[str, Any]],
    params: StrategyParams,
    candidate_type_filter: str | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    eligible_rows = [row for row in analyzed_rows if row["status"] in {"picked", "low_score_filtered"}]
    if candidate_type_filter is not None:
        eligible_rows = [row for row in eligible_rows if row["candidate_type"] == candidate_type_filter]

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
            row
            for row in filtered_rows
            if row["candidate_type"] is not None
            and row["score"] is not None
            and float(row["score"]) >= params.min_score
        )
    ][: params.limit]

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
    excluded: list[dict[str, object]] = []
    if params.include_excluded:
        excluded = [_excluded_view(row) for row in excluded_rows[: params.show_excluded_limit]]
    return picks, excluded


def _build_explain(
    con,
    analyzed_rows: list[dict[str, Any]],
    explain_symbol: str,
    params: StrategyParams,
    candidate_type_filter: str | None,
    trade_date: date,
    dataset_run_id: str | None,
    factor_version: str | None,
    execute_date: date | None,
    strategy_name: str,
    required_fields: tuple[str, ...],
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
        fetched = fetch_strategy_rows_for_symbol(
            con,
            (symbol_parts["market"],),
            trade_date,
            symbol_parts["symbol"],
            required_fields=required_fields,
        )
        if fetched:
            matching = [
                _analyze_row(
                    fetched[0],
                    params,
                    execute_date,
                    dataset_run_id,
                    factor_version,
                    strategy_name,
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
    if candidate_type_filter is not None and row["candidate_type"] != candidate_type_filter:
        return {
            "status": "unclassified_filtered",
            "pick": _explain_view(row, dataset_run_id, factor_version, execute_date),
            "excluded_reason": None,
            "message": "does not match the current preset candidate type",
        }
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


def _parse_symbol(value: str) -> dict[str, str | None]:
    text = value.strip()
    if "." in text:
        symbol, market = text.split(".", 1)
        return {"symbol": symbol, "market": market.lower() or None}
    lowered = text.lower()
    if len(text) == 8 and lowered[:2] in {"sh", "sz", "bj"}:
        return {"symbol": text[2:], "market": lowered[:2]}
    return {"symbol": text, "market": None}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


register_strategy(
    StrategyDefinition(
        name="trend-strength",
        description="Generate the short-term trend observation pool.",
        runner=run_trend_strength_strategy,
        aliases=("trend_strength",),
        required_fields=(
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
        ),
        default_params=StrategyParams(),
    )
)
