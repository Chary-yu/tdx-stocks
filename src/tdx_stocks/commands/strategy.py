from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from ..backtest import (
    BacktestParams,
    analyze_forward_returns,
    analyze_risk_tags,
    backtest_consensus,
    compare_backtests,
    load_backtest_configs,
    run_backtest,
    run_batch,
    run_monte_carlo_simulation,
    run_stress_test_suite,
    run_walk_forward_validation,
    tune_strategy_parameters,
)
from ..config import load_config
from ..console import print_json, print_key_values, print_table
from ..io_utils import write_json_atomic
from ..pipeline import parse_iso_date
from ..query import normalize_output_data
from ..strategies.base import StrategyParams
from ..strategies.compare import compare_strategies
from ..strategies.consensus import build_consensus
from ..strategies.registry import get_strategy, list_strategies
from ..strategies.storage import (
    build_report_document,
    list_saved_reports,
    load_saved_report,
    save_report_document,
)
from .common import add_config_arg, add_output_arg, validate_output_alias
from .common import legacy_notice as _legacy_notice
from .output import emit_report_table, write_csv, write_rows

STRATEGY_TYPE_LABELS = {
    "breakout_watch": "突破观察",
    "strong_trend": "趋势强",
    "pullback_watch": "回调观察",
    "oversold_rebound": "超跌反弹",
    "smart_money": "聪明资金",
    "pair_short": "配对做空",
    "pair_long": "配对做多",
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
    "oversold_rebound": "超跌反弹",
    "smart_money": "聪明资金",
    "price_volume_alignment": "量价齐升",
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

COMMON_CANDIDATE_TYPES = (
    "strong_trend",
    "breakout_watch",
    "pullback_watch",
    "oversold_rebound",
    "smart_money",
    "pair_short",
    "pair_long",
)

STRESS_PERIODS = {
    "2015_crash": ("2015-06-12", "2015-09-30"),
    "2016_circuit_breaker": ("2016-01-01", "2016-02-28"),
    "2018_bear": ("2018-01-01", "2018-12-31"),
    "2024_micro_cap_crash": ("2024-01-01", "2024-02-08"),
}


def register_strategy_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_strategy_list: Callable[[argparse.Namespace], int],
    cmd_strategy_run: Callable[[argparse.Namespace], int],
    hidden: bool = False,
) -> None:
    strategy_parser = subparsers.add_parser(
        "strategy",
        help=argparse.SUPPRESS if hidden else "Strategy analysis commands.",
        description="Commands that generate read-only observation pools from the latest dataset.",
    )
    strategy_subparsers = strategy_parser.add_subparsers(dest="strategy_command", required=True)

    list_parser = strategy_subparsers.add_parser("list", help="List available strategy presets.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_strategy_list)

    groups_parser = strategy_subparsers.add_parser("groups", help="Show strategy distribution by group.")
    groups_parser.add_argument("--json", action="store_true")
    groups_parser.set_defaults(func=cmd_strategy_groups)

    describe_parser = strategy_subparsers.add_parser("describe", help="Describe a strategy preset.")
    describe_parser.add_argument("strategy")
    describe_parser.add_argument("--json", action="store_true")
    describe_parser.set_defaults(func=cmd_strategy_describe)

    explain_parser = strategy_subparsers.add_parser("explain", help="Explain why a symbol matches a strategy.")
    add_config_arg(explain_parser)
    explain_parser.add_argument("strategy")
    explain_parser.add_argument("symbol")
    explain_parser.add_argument("--as-of", default="latest")
    explain_parser.add_argument("--json", action="store_true")
    add_output_arg(explain_parser)
    explain_parser.add_argument("--market", choices=("sh", "sz", "bj"))
    explain_parser.add_argument("--limit", type=int, default=20)
    explain_parser.add_argument("--min-score", type=float, default=60.0)
    explain_parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    explain_parser.add_argument("--candidate-type")
    explain_parser.add_argument("--include-excluded", action="store_true")
    explain_parser.add_argument("--show-excluded-limit", type=int, default=20)
    explain_parser.set_defaults(func=cmd_strategy_explain)

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
        if definition.add_arguments is not None:
            definition.add_arguments(strategy_parser)
        strategy_parser.set_defaults(func=cmd_strategy_run, strategy_name=definition.name)

    compare_parser = strategy_subparsers.add_parser("compare", help="Compare strategy candidates.")
    _add_compare_args(compare_parser)
    compare_parser.set_defaults(func=cmd_strategy_compare)

    consensus_parser = strategy_subparsers.add_parser("consensus", help="Find strategy consensus candidates.")
    _add_consensus_args(consensus_parser)
    consensus_parser.set_defaults(func=cmd_strategy_consensus)

    backtest_parser = strategy_subparsers.add_parser(
        "backtest",
        help="Run a rolling T+1 signal backtest on historical dates.",
    )
    _add_backtest_args(backtest_parser)
    backtest_parser.add_argument("strategy_name")
    backtest_parser.set_defaults(func=cmd_strategy_backtest)

    backtest_compare_parser = strategy_subparsers.add_parser(
        "backtest-compare",
        help="Compare backtests across strategies.",
    )
    _add_backtest_compare_args(backtest_compare_parser)
    backtest_compare_parser.set_defaults(func=cmd_strategy_backtest_compare)

    tune_parser = strategy_subparsers.add_parser("tune", help="Scan strategy parameter combinations.")
    _add_tune_args(tune_parser)
    tune_parser.add_argument("strategy_name")
    tune_parser.set_defaults(func=cmd_strategy_tune)

    forward_parser = strategy_subparsers.add_parser(
        "analyze-forward-returns",
        help="Analyze forward returns after strategy hits.",
    )
    _add_forward_return_args(forward_parser)
    forward_parser.add_argument("strategy_name")
    forward_parser.set_defaults(func=cmd_strategy_analyze_forward_returns)

    risk_parser = strategy_subparsers.add_parser(
        "analyze-risk-tags",
        help="Analyze forward returns by risk tags.",
    )
    _add_risk_tag_args(risk_parser)
    risk_parser.add_argument("strategy_name")
    risk_parser.set_defaults(func=cmd_strategy_analyze_risk_tags)

    consensus_backtest_parser = strategy_subparsers.add_parser(
        "backtest-consensus",
        help="Backtest consensus hits across multiple strategies.",
    )
    _add_backtest_consensus_args(consensus_backtest_parser)
    consensus_backtest_parser.set_defaults(func=cmd_strategy_backtest_consensus)

    batch_parser = strategy_subparsers.add_parser(
        "batch",
        help="Run TOML-driven backtest experiments.",
        description="Load a single TOML file and run the backtest or batch search defined in it.",
    )
    _add_batch_args(batch_parser)
    batch_parser.set_defaults(func=cmd_strategy_batch)

    reports_parser = strategy_subparsers.add_parser("reports", help="Manage saved strategy reports.")
    reports_subparsers = reports_parser.add_subparsers(dest="reports_command", required=True)
    reports_list_parser = reports_subparsers.add_parser("list", help="List saved strategy reports.")
    add_config_arg(reports_list_parser)
    reports_list_parser.add_argument("--json", action="store_true")
    reports_list_parser.set_defaults(func=cmd_strategy_reports_list)
    reports_show_parser = reports_subparsers.add_parser("show", help="Show a saved strategy report.")
    add_config_arg(reports_show_parser)
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
        choices=(
            "strong_trend",
            "breakout_watch",
            "pullback_watch",
            "oversold_rebound",
            "smart_money",
            "pair_short",
            "pair_long",
        ),
    )
    parser.add_argument("--include-excluded", action="store_true")
    parser.add_argument("--show-excluded-limit", type=int, default=20)
    parser.add_argument("--explain-symbol")
    parser.add_argument("--output", type=Path)


def _add_compare_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_consensus_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--min-hit", type=int, default=2)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_backtest_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="from_date")
    parser.add_argument("--to", dest="to_date")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--walk-forward", action="store_true")
    parser.add_argument("--train-years", type=int, default=3)
    parser.add_argument("--test-years", type=int, default=1)
    parser.add_argument("--monte-carlo", action="store_true")
    parser.add_argument("--iterations", type=int, default=1000)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--stress-test", action="store_true")
    parser.add_argument("--stress-period", choices=("all",) + tuple(STRESS_PERIODS), default="all")


def _add_backtest_compare_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_tune_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--min-score", default="55,60,65")
    parser.add_argument("--top", default="10,20,30")
    parser.add_argument("--hold-days", default="5,10,20")
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_forward_return_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--horizons", default="1,5,10,20")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_risk_tag_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--horizons", default="5,10,20")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_backtest_consensus_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--strategies", help="Comma-separated strategy names. Defaults to all registered strategies.")
    parser.add_argument("--from", dest="from_date", required=True)
    parser.add_argument("--to", dest="to_date", required=True)
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--hold-days", type=int, default=5)
    parser.add_argument("--min-hit", type=int, default=2)
    parser.add_argument("--fee-rate", type=float, default=0.0)
    parser.add_argument("--slippage", type=float, default=0.0)
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--min-score", type=float, default=60.0)
    parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    parser.add_argument("--candidate-type", choices=COMMON_CANDIDATE_TYPES)
    parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)


def _add_batch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-c", "--config", type=Path, required=True, help="Path to the TOML config file.")
    parser.add_argument("--batch", action="store_true", help="Expand [batch_search] into a grid search.")


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
    strategy_name = getattr(args, "strategy_name", "trend-strength")
    definition = get_strategy(strategy_name)
    if definition.params_builder is not None:
        return definition.params_builder(args)
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


def _parse_csv_numbers(value: str, *, cast) -> list[object]:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def _parse_horizons(value: str) -> list[int]:
    return [int(item) for item in _parse_csv_numbers(value, cast=int)]


def _parse_float_list(value: str) -> list[float]:
    return [float(item) for item in _parse_csv_numbers(value, cast=float)]


def _parse_int_list(value: str) -> list[int]:
    return [int(item) for item in _parse_csv_numbers(value, cast=int)]


def _write_strategy_output(report, args: argparse.Namespace, *, export_dir: Path | None = None) -> None:
    validate_output_alias(args)
    report_dict = report.to_dict()
    output_path = getattr(args, "output", None) or getattr(args, "to", None)
    if output_path is not None:
        write_json_atomic(output_path, report_dict)
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
            "group": definition.group,
            "style": definition.style,
            "description": definition.description,
            "aliases": ", ".join(definition.aliases),
            "introduced_in": definition.introduced_in,
        }
        for definition in list_strategies()
    ]
    if getattr(args, "json", False):
        print_json(normalize_output_data(strategies))
    else:
        print_table(["name", "group", "style", "aliases", "introduced_in", "description"], strategies)
    return 0


def cmd_strategy_groups(args: argparse.Namespace) -> int:
    groups: dict[str, dict[str, object]] = {}
    for definition in list_strategies():
        item = groups.setdefault(
            definition.group,
            {
                "group": definition.group,
                "strategy_count": 0,
                "strategies": [],
                "description": _group_description(definition.group),
            },
        )
        item["strategy_count"] = int(item["strategy_count"]) + 1
        item["strategies"].append(definition.name)
    rows = sorted(groups.values(), key=lambda row: str(row["group"]))
    for row in rows:
        row["strategies"] = ", ".join(sorted(row["strategies"]))
    if getattr(args, "json", False):
        print_json(normalize_output_data(rows))
    else:
        print_table(["group", "strategy_count", "strategies", "description"], rows)
    return 0


def cmd_strategy_describe(args: argparse.Namespace) -> int:
    definition = get_strategy(args.strategy)
    payload = _strategy_description_payload(definition)
    if getattr(args, "json", False):
        print_json(normalize_output_data(payload))
    else:
        print_key_values(
            f"strategy: {definition.name}",
            [
                ("策略名称", definition.display_name or definition.name),
                ("策略分组", definition.group),
                ("策略风格", definition.style),
                ("策略说明", definition.description),
                ("依赖因子", ", ".join(definition.required_fields) or "无"),
                ("可选因子", ", ".join(definition.optional_fields) or "无"),
                ("默认参数", json.dumps(definition.default_params.to_dict(), ensure_ascii=False, default=str)),
                ("可调参数", json.dumps(definition.param_schema, ensure_ascii=False, default=str)),
                ("候选类型", ", ".join(definition.candidate_types) or "无"),
                ("风险标签", ", ".join(definition.risk_tags) or "无"),
                ("支持的研究能力", ", ".join(definition.research_capabilities())),
                ("别名", ", ".join(definition.aliases) or "无"),
                ("首次引入", definition.introduced_in),
            ],
        )
    return 0


def cmd_strategy_explain(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    definition = get_strategy(args.strategy)
    params = _build_explain_params(args, definition)
    report = definition.runner(config, params)
    payload = _normalize_explain_payload(definition, params, report, args.symbol)
    output_path = getattr(args, "output", None) or getattr(args, "to", None)
    if output_path is not None:
        write_json_atomic(output_path, payload)
    if getattr(args, "json", False):
        print_json(normalize_output_data(payload))
    else:
        print_key_values(
            f"strategy explain: {definition.name} {args.symbol}",
            [
                ("是否入选", payload.get("selected")),
                ("总分", payload.get("total_score")),
                ("未入选原因", payload.get("not_selected_reason")),
                ("风险标签", ", ".join(payload.get("risk_tags") or []) or "无"),
                ("缺失字段", ", ".join(payload.get("missing_fields") or []) or "无"),
                ("关键因子值", json.dumps(payload.get("key_factors"), ensure_ascii=False, default=str)),
            ],
        )
        print_table(["name", "passed", "detail"], payload.get("rule_checks") or [])
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
    if getattr(args, "json", False):
        print_json(report)
    else:
        print_json(report)
    return 0


def _strategy_description_payload(definition) -> dict[str, object]:
    return {
        **definition.to_dict(),
        "supported_research_capabilities": list(definition.research_capabilities()),
    }


def _group_description(group: str) -> str:
    return {
        "trend": "趋势与突破类策略",
        "momentum": "动量与强势类策略",
        "pullback": "回调与反转类策略",
        "breakout": "突破类策略",
        "pair": "配对与对冲类策略",
    }.get(group, "其他策略")


def _build_explain_params(args: argparse.Namespace, definition) -> StrategyParams:
    args.explain_symbol = args.symbol
    if definition.params_builder is not None:
        params = definition.params_builder(args)
    else:
        params = StrategyParams(
            limit=args.limit,
            min_score=args.min_score,
            min_amount_ma20=args.min_amount_ma20,
            market=args.market,
            candidate_type=args.candidate_type,
            include_excluded=args.include_excluded,
            show_excluded_limit=args.show_excluded_limit,
            explain_symbol=args.symbol,
            as_of=_parse_as_of(args.as_of),
        )
    return params


def _normalize_explain_payload(
    definition,
    params: StrategyParams,
    report,
    symbol: str,
) -> dict[str, object]:
    explain = report.explain or {}
    pick = explain.get("pick") or {}
    selected = explain.get("status") == "picked"
    factor_values = dict(pick.get("factor_values") or {})
    required_fields = tuple(getattr(definition, "required_fields", ()) or ())
    missing_fields = [
        field
        for field in required_fields
        if factor_values.get(field) is None
    ]
    rule_checks = [
        {
            "name": "selected",
            "passed": selected,
            "detail": explain.get("message") or explain.get("status"),
        },
        {
            "name": "candidate_type",
            "passed": bool(pick.get("candidate_type")),
            "detail": pick.get("candidate_type") or "无候选类型",
        },
        {
            "name": "min_score",
            "passed": pick.get("score") is None or float(pick.get("score") or 0.0) >= float(params.min_score or 0.0),
            "detail": f"min_score={params.min_score}",
        },
        {
            "name": "missing_fields",
            "passed": not missing_fields,
            "detail": ", ".join(missing_fields) or "无",
        },
    ]
    return {
        "strategy": getattr(definition, "name", "unknown"),
        "symbol": symbol,
        "selected": selected,
        "total_score": pick.get("score"),
        "not_selected_reason": None if selected else (explain.get("excluded_reason") or explain.get("message")),
        "rule_checks": rule_checks,
        "score_breakdown": pick.get("score_breakdown"),
        "key_factors": factor_values,
        "risk_tags": pick.get("risk_flags") or [],
        "missing_fields": missing_fields,
        "candidate_type": pick.get("candidate_type"),
        "tags": pick.get("tags") or [],
        "watch_plan": pick.get("watch_plan"),
        "as_of": params.as_of.isoformat() if params.as_of else "latest",
        "detail": explain,
    }


def cmd_strategy_compare(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
    result = compare_strategies(config, strategy_names, as_of=_parse_as_of(args.as_of))
    payload = result.to_dict()
    output_format = "json" if getattr(args, "json", False) else args.format
    output_path = getattr(args, "output", None) or getattr(args, "to", None)
    if output_format == "json":
        if output_path is not None:
            write_json_atomic(output_path, payload)
        else:
            print_json(payload)
    elif output_format == "csv":
        rows = [row.to_dict() for row in result.strategies]
        write_csv(rows, ["strategy_name", "candidate_count", "avg_score", "max_score", "high_score_count", "risk_flag_count", "stocks"], output_path)
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
    validate_output_alias(args)
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
    result = build_consensus(config, strategy_names, as_of=_parse_as_of(args.as_of), min_hit=args.min_hit)
    payload = result.to_dict()
    output_format = "json" if getattr(args, "json", False) else args.format
    output_path = getattr(args, "output", None) or getattr(args, "to", None)
    if output_format == "json":
        if output_path is not None:
            write_json_atomic(output_path, payload)
        else:
            print_json(payload)
    elif output_format == "csv":
        write_csv(
            [row.to_dict() for row in result.rows],
            ["market", "symbol", "hit_count", "strategies", "avg_score", "max_score", "candidate_types", "tags", "risk_flags", "reasons"],
            output_path,
        )
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


def cmd_strategy_backtest_compare(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
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
    report = compare_backtests(config, strategy_names, params)
    output_format = "json" if getattr(args, "json", False) else args.format
    write_rows(
        report["rows"],
        columns=[
            "strategy_name",
            "total_return",
            "annual_return",
            "max_drawdown",
            "win_rate",
            "avg_period_return",
            "turnover",
            "period_count",
            "empty_period_count",
        ],
        format_name=output_format,
        to=args.output,
    )
    return 0


def cmd_strategy_tune(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    params = BacktestParams(
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        top=20,
        hold_days=5,
        fee_rate=args.fee_rate,
        slippage=args.slippage,
        market=args.market,
        candidate_type=args.candidate_type,
        min_score=60.0,
        min_amount_ma20=args.min_amount_ma20,
    )
    report = tune_strategy_parameters(
        config,
        args.strategy_name,
        params,
        min_scores=_parse_float_list(args.min_score),
        tops=_parse_int_list(args.top),
        hold_days=_parse_int_list(args.hold_days),
    )
    output_format = "json" if getattr(args, "json", False) else args.format
    write_rows(
        report["rows"],
        columns=[
            "min_score",
            "top",
            "hold_days",
            "total_return",
            "annual_return",
            "max_drawdown",
            "win_rate",
            "turnover",
            "period_count",
            "empty_period_count",
            "research_score",
        ],
        format_name=output_format,
        to=args.output,
    )
    return 0


def cmd_strategy_analyze_forward_returns(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    params = BacktestParams(
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        top=args.limit,
        hold_days=1,
        fee_rate=0.0,
        slippage=0.0,
        market=args.market,
        candidate_type=args.candidate_type,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
    )
    report = analyze_forward_returns(config, args.strategy_name, params, horizons=_parse_horizons(args.horizons))
    output_format = "json" if getattr(args, "json", False) else args.format
    write_rows(
        report["rows"],
        columns=["horizon", "sample_count", "mean_return", "median_return", "win_rate", "p25", "p75", "best", "worst"],
        format_name=output_format,
        to=args.output,
    )
    return 0


def cmd_strategy_analyze_risk_tags(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    params = BacktestParams(
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        top=args.limit,
        hold_days=1,
        fee_rate=0.0,
        slippage=0.0,
        market=args.market,
        candidate_type=args.candidate_type,
        min_score=args.min_score,
        min_amount_ma20=args.min_amount_ma20,
    )
    report = analyze_risk_tags(config, args.strategy_name, params, horizons=_parse_horizons(args.horizons))
    output_format = "json" if getattr(args, "json", False) else args.format
    write_rows(
        report["rows"],
        columns=["risk_tag", "horizon", "sample_count", "mean_forward_return", "win_rate", "worst_return", "max_drawdown_after_entry"],
        format_name=output_format,
        to=args.output,
    )
    return 0


def cmd_strategy_backtest_consensus(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    strategy_names = _parse_strategy_names(args.strategies)
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
    report = backtest_consensus(config, strategy_names, params, min_hit=args.min_hit)
    output_format = "json" if getattr(args, "json", False) else args.format
    emit_report_table(report, format_name=output_format, to=args.output)
    return 0


def cmd_strategy_backtest(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    if args.stress_test:
        if args.from_date is None:
            args.from_date = min(period[0] for period in STRESS_PERIODS.values())
        if args.to_date is None:
            args.to_date = max(period[1] for period in STRESS_PERIODS.values())
    if args.from_date is None or args.to_date is None:
        raise ValueError("backtest requires --from and --to unless --stress-test is used")
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
    output_format = "json" if getattr(args, "json", False) else args.format
    if args.stress_test:
        periods = {args.stress_period: STRESS_PERIODS[args.stress_period]} if args.stress_period != "all" else STRESS_PERIODS
        report = run_stress_test_suite(config, args.strategy_name, params, periods)
        write_rows(
            report["rows"],
            columns=[
                "period",
                "from_date",
                "to_date",
                "trade_count",
                "period_count",
                "total_return",
                "annual_return",
                "max_drawdown",
                "win_rate",
                "turnover",
            ],
            format_name=output_format,
            to=args.output,
        )
        return 0
    if args.walk_forward:
        report = run_walk_forward_validation(
            config,
            args.strategy_name,
            params,
            train_years=args.train_years,
            test_years=args.test_years,
        )
        emit_report_table(report, format_name=output_format, to=args.output)
        return 0
    if args.monte_carlo:
        base_report = run_backtest(config, args.strategy_name, params)
        report = run_monte_carlo_simulation(base_report.trades, params.portfolio.initial_cash if params.portfolio else 1.0, iterations=args.iterations, seed=args.seed)
        emit_report_table(report, format_name=output_format, to=args.output)
        return 0
    report = run_backtest(config, args.strategy_name, params)
    emit_report_table(report.to_dict(), format_name=output_format, to=args.output)
    return 0


def cmd_strategy_batch(args: argparse.Namespace) -> int:
    configs = load_backtest_configs(args.config, batch=args.batch)
    reports = run_batch(configs)
    payload = [report.to_dict() for report in reports]
    print_json(payload if len(payload) != 1 else payload[0])
    return 0
