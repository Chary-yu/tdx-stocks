from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Callable
from datetime import date
from datetime import datetime

from ..config import load_config
from ..console import print_json, print_table
from ..pipeline import parse_iso_date
from ..query import normalize_output_data
from ..strategies.base import StrategyParams
from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
from ..strategies.storage import (
    build_report_document,
    list_saved_reports,
    load_saved_report,
    save_report_document,
)
from ..strategies.registry import list_strategies
from ..backtest import BacktestParams, run_backtest
from .common import add_config_arg, legacy_notice as _legacy_notice

STRATEGY_TYPE_LABELS = {
    "breakout_watch": "突破观察",
    "strong_trend": "趋势强",
    "pullback_watch": "回调观察",
}

STRATEGY_TAG_LABELS = {
    "breakout_watch": "突破关注",
    "low_volatility": "低波动",
    "trend_strong": "趋势强",
    "pullback_watch": "回调关注",
    "near_20d_high": "近20日高位",
    "volume_expansion": "放量",
    "volume_breakout": "放量突破",
    "relative_strength": "相对强势",
    "active_amount": "资金活跃",
    "ma_bullish": "均线多头",
}

STRATEGY_RISK_LABELS = {
    "ret_5_strong": "短线加速",
    "rsi_high": "RSI偏高",
    "mild_volatility": "波动偏高",
    "near_20d_high": "接近高位",
    "risk_factor_missing": "风险因子缺失",
    "high_volatility": "波动偏高",
    "volume_climax": "放量冲顶",
}


def register_strategy_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_strategy_list: Callable[[argparse.Namespace], int],
    cmd_strategy_run: Callable[[argparse.Namespace], int],
) -> None:
    strategy_parser = subparsers.add_parser(
        "strategy",
        help="Strategy analysis commands.",
        description="Commands that generate read-only observation pools from the latest dataset.",
    )
    strategy_subparsers = strategy_parser.add_subparsers(dest="strategy_command", required=True)

    list_parser = strategy_subparsers.add_parser("list", help="List available strategy presets.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_strategy_list)

    run_parser = strategy_subparsers.add_parser("run", help="Run a strategy and emit a report.")
    run_subparsers = run_parser.add_subparsers(dest="strategy_name", required=True)

    for definition in list_strategies():
        strategy_parser = run_subparsers.add_parser(
            definition.name,
            help=definition.description,
            aliases=list(definition.aliases),
            description=definition.description,
        )
        _add_common_run_args(strategy_parser)
        strategy_parser.set_defaults(func=cmd_strategy_run, strategy_name=definition.name)

    compare_parser = strategy_subparsers.add_parser("compare", help="Compare strategy candidates.")
    _add_compare_args(compare_parser)
    compare_parser.set_defaults(func=cmd_strategy_compare)

    consensus_parser = strategy_subparsers.add_parser("consensus", help="Find strategy consensus candidates.")
    _add_consensus_args(consensus_parser)
    consensus_parser.set_defaults(func=cmd_strategy_consensus)

    backtest_parser = strategy_subparsers.add_parser("backtest", help="Backtest a strategy on historical dates.")
    _add_backtest_args(backtest_parser)
    backtest_parser.add_argument("strategy_name")
    backtest_parser.set_defaults(func=cmd_strategy_backtest)

    reports_parser = strategy_subparsers.add_parser("reports", help="Manage saved strategy reports.")
    reports_subparsers = reports_parser.add_subparsers(dest="reports_command", required=True)
    reports_list_parser = reports_subparsers.add_parser("list", help="List saved strategy reports.")
    reports_list_parser.add_argument("--json", action="store_true")
    reports_list_parser.set_defaults(func=cmd_strategy_reports_list)
    reports_show_parser = reports_subparsers.add_parser("show", help="Show a saved strategy report.")
    reports_show_parser.add_argument("strategy_name")
    reports_show_parser.add_argument("--as-of", default="latest")
    reports_show_parser.add_argument("--run-id")
    reports_show_parser.add_argument("--json", action="store_true")
    reports_show_parser.set_defaults(func=cmd_strategy_reports_show)


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--save", action="store_true")
    parser.add_argument("--as-of")
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument(
        "--candidate-type",
        choices=("strong_trend", "breakout_watch", "pullback_watch"),
    )
    parser.add_argument("--include-excluded", action="store_true")
    parser.add_argument("--show-excluded-limit", type=int, default=20)
    parser.add_argument("--explain-symbol")
    parser.add_argument("--to", type=Path)


def _add_compare_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--json", action="store_true")


def _add_consensus_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--min-hit", type=int, default=2)
    parser.add_argument("--json", action="store_true")


def _add_backtest_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=("strong_trend", "breakout_watch", "pullback_watch"))
    parser.add_argument("--json", action="store_true")


def _print_strategy_table(rows: list[dict[str, object]], stock_names: dict[tuple[str, str], str] | None = None) -> None:
    if not rows:
        print("(no rows)")
        return
    stock_names = stock_names or {}
    display_rows = []
    for row in rows:
        market = str(row.get("market") or "").lower()
        symbol = str(row.get("symbol") or "")
        display_rows.append(
            {
                "排名": row.get("rank"),
                "代码": row.get("display_symbol") or row.get("symbol"),
                "名称": stock_names.get((market, symbol), "未知"),
                "得分": row.get("score"),
                "类型": _format_candidate_type(row.get("candidate_type")),
                "标签": _format_tokens(row.get("tags"), STRATEGY_TAG_LABELS),
                "风险": _format_tokens(row.get("risk_flags"), STRATEGY_RISK_LABELS),
                "计划": row.get("watch_plan"),
            }
        )
    print_table(["排名", "代码", "名称", "得分", "类型", "标签", "风险", "计划"], display_rows)


def _format_candidate_type(value: object) -> str:
    if value is None:
        return "无"
    return STRATEGY_TYPE_LABELS.get(str(value), "其他")


def _format_tokens(values: object, labels: dict[str, str], max_items: int = 3) -> str:
    if not isinstance(values, list):
        return "无" if values is None else str(values)
    items: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = labels.get(str(item))
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
    if not items:
        return "无"
    if len(items) <= max_items:
        return "/".join(items)
    return "/".join(items[:max_items]) + "…"


def _resolve_stock_name(export_dir: Path | None, market: str, symbol: str) -> str:
    if export_dir is None or not export_dir.exists():
        return "未知"
    candidates = [
        export_dir / f"{market.upper()}#{symbol}.txt",
        export_dir / f"{market.lower()}#{symbol}.txt",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="gbk", errors="ignore") as handle:
                header = handle.readline().strip()
        except OSError:
            continue
        if not header:
            continue
        parts = header.split()
        if len(parts) >= 2:
            return parts[1].strip() or "未知"
    return "未知"


def _build_stock_name_map(export_dir: Path | None, rows: list[dict[str, object]]) -> dict[tuple[str, str], str]:
    if export_dir is None:
        return {}
    stock_names: dict[tuple[str, str], str] = {}
    for row in rows:
        market = str(row.get("market") or "").lower()
        symbol = str(row.get("symbol") or "")
        if not market or not symbol:
            continue
        stock_names[(market, symbol)] = _resolve_stock_name(export_dir, market, symbol)
    return stock_names


def _build_strategy_params(args: argparse.Namespace) -> StrategyParams:
    return StrategyParams(
        limit=args.limit,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
        market=args.market,
        candidate_type=args.candidate_type,
        include_excluded=args.include_excluded,
        show_excluded_limit=args.show_excluded_limit,
        explain_symbol=args.explain_symbol,
        as_of=parse_iso_date(args.as_of),
    )


def _parse_as_of(value: str | None) -> date | None:
    if value is None or value == "latest":
        return None
    return parse_iso_date(value)


def _parse_strategy_names(value: str | None) -> list[str]:
    if not value:
        return [definition.name for definition in list_strategies()]
    names = [item.strip() for item in value.split(",")]
    return [name for name in names if name]


def _write_strategy_output(report, args: argparse.Namespace, *, export_dir: Path | None = None) -> None:
    report_dict = report.to_dict()
    if args.to is not None:
        args.to.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(report_dict, ensure_ascii=False, indent=2, default=str)
        args.to.write_text(payload, encoding="utf-8")
    if args.json:
        print_json(report_dict)
    else:
        stock_names = _build_stock_name_map(export_dir, report.picks)
        _print_strategy_table(report.picks, stock_names)


def _save_strategy_report(report, args: argparse.Namespace, config, strategy_name: str) -> None:
    if not getattr(args, "save", False):
        return
    as_of = _parse_as_of(args.as_of) or parse_iso_date(str(report.summary.get("trade_date")) if report.summary.get("trade_date") else None)
    if as_of is None:
        return
    document = build_report_document(
        strategy_name=strategy_name,
        as_of=as_of,
        generated_at=datetime.now(),
        data_run_id=str(report.summary.get("dataset_run_id")) if report.summary.get("dataset_run_id") is not None else None,
        factor_version=str(report.summary.get("factor_version")) if report.summary.get("factor_version") is not None else None,
        params=_build_strategy_params(args),
        report=report,
    )
    save_report_document(config.paths.data_root, strategy_name, document)


def cmd_strategy_run(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    from ..strategies.registry import get_strategy

    config = load_config(args.config)
    definition = get_strategy(args.strategy_name)
    report = definition.runner(config, _build_strategy_params(args))
    _save_strategy_report(report, args, config, definition.name)
    _write_strategy_output(report, args, export_dir=config.paths.tdx_export)
    return 0


def cmd_strategy_run_trend_strength(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    from ..strategy import run_trend_strength_strategy

    report = run_trend_strength_strategy(config, _build_strategy_params(args))
    _save_strategy_report(report, args, config, "trend-strength")
    _write_strategy_output(report, args, export_dir=config.paths.tdx_export)
    return 0


def cmd_strategy_list(args: argparse.Namespace) -> int:
    strategies = [
        {
            "name": definition.name,
            "description": definition.description,
            "aliases": ", ".join(definition.aliases),
        }
        for definition in list_strategies()
    ]
    if getattr(args, "json", False):
        print_json(normalize_output_data(strategies))
    else:
        print_table(["name", "aliases", "description"], strategies)
    return 0


def cmd_strategy_reports_list(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rows = list_saved_reports(config.paths.data_root)
    if getattr(args, "json", False):
        print_json(normalize_output_data(rows))
    else:
        print_table(["strategy_name", "as_of", "generated_at", "data_run_id", "candidate_count", "excluded_count"], rows)
    return 0


def cmd_strategy_reports_show(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    report = load_saved_report(
        config.paths.data_root,
        args.strategy_name,
        as_of=args.as_of,
        run_id=args.run_id,
    )
    if report is None:
        raise FileNotFoundError(
            f"saved report not found for strategy={args.strategy_name!r}, as_of={args.as_of!r}, run_id={args.run_id!r}"
        )
    print_json(report)
    return 0


def cmd_strategy_compare(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
    result = compare_strategies(config, strategy_names, as_of=_parse_as_of(args.as_of))
    if getattr(args, "json", False):
        print_json(result.to_dict())
    else:
        print("strategy summary")
        print_table(["strategy_name", "candidate_count", "avg_score", "max_score", "high_score_count", "risk_flag_count"], [row.to_dict() for row in result.strategies])
        print("overlap summary")
        print_table(
            ["left_strategy", "right_strategy", "overlap_count", "stocks"],
            [
                {
                    **row,
                    "stocks": ", ".join(row.get("stocks") or []) or "无",
                }
                for row in result.overlaps
            ],
        )
        print("unique stocks")
        print_table(
            ["strategy_name", "unique_stocks"],
            [{"strategy_name": name, "unique_stocks": ", ".join(stocks) or "无"} for name, stocks in result.unique_stocks.items()],
        )
    return 0


def cmd_strategy_consensus(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
    result = build_consensus(config, strategy_names, as_of=_parse_as_of(args.as_of), min_hit=args.min_hit)
    if getattr(args, "json", False):
        print_json(result.to_dict())
    else:
        print_table(
            ["market", "symbol", "hit_count", "strategies", "avg_score", "max_score", "candidate_types", "tags", "risk_flags", "reasons"],
            [
                {
                    "market": row.market,
                    "symbol": row.symbol,
                    "hit_count": row.hit_count,
                    "strategies": ",".join(row.strategies),
                    "avg_score": row.avg_score,
                    "max_score": row.max_score,
                    "candidate_types": ",".join(row.candidate_types),
                    "tags": ",".join(row.tags),
                    "risk_flags": ",".join(row.risk_flags),
                    "reasons": ",".join(row.reasons),
                }
                for row in result.rows
            ],
        )
    return 0


def cmd_strategy_backtest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    params = BacktestParams(
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        top=args.top,
        hold_days=args.hold_days,
        fee_rate=args.fee_rate,
        slippage=args.slippage,
        market=args.market,
        candidate_type=args.candidate_type,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
    )
    report = run_backtest(config, args.strategy_name, params)
    if getattr(args, "json", False):
        print_json(report.to_dict())
    else:
        print_json(report.to_dict())
    return 0
