from __future__ import annotations

import argparse
import json
from pathlib import Path
from collections.abc import Callable

from ..config import load_config
from ..console import print_json, print_table
from ..pipeline import parse_iso_date
from ..query import normalize_output_data
from ..strategies.base import StrategyParams
from ..strategies.registry import list_strategies
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


def _add_common_run_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true")
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


def cmd_strategy_run(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    from ..strategies.registry import get_strategy

    config = load_config(args.config)
    definition = get_strategy(args.strategy_name)
    report = definition.runner(config, _build_strategy_params(args))
    _write_strategy_output(report, args, export_dir=config.paths.tdx_export)
    return 0


def cmd_strategy_run_trend_strength(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    from ..strategy import run_trend_strength_strategy

    report = run_trend_strength_strategy(config, _build_strategy_params(args))
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
