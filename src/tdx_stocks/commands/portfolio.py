from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import load_config
from ..console import print_json, print_key_values, print_table
from ..io_utils import write_json_atomic
from ..pipeline import parse_iso_date
from ..portfolio import (
    build_portfolio,
    build_rebalance_plan,
    check_portfolio_risk,
    list_portfolio_reports,
    load_current_holdings_csv,
    load_latest_portfolio_report,
    load_portfolio_report,
    run_portfolio_backtest,
    save_portfolio_backtest_report,
    save_portfolio_report,
    save_rebalance_plan,
)
from ..portfolio.models import Holding, PortfolioBacktestReport, PortfolioReport, RebalancePlan
from ..query import normalize_output_data
from ..reports.renderers import render_portfolio_markdown
from .common import add_config_arg, add_output_arg, validate_output_alias


def register_portfolio_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    hidden: bool = False,
) -> None:
    portfolio_parser = subparsers.add_parser(
        "portfolio",
        help=argparse.SUPPRESS if hidden else "Portfolio construction and risk commands.",
    )
    portfolio_subparsers = portfolio_parser.add_subparsers(dest="portfolio_command", required=True)

    build_parser = portfolio_subparsers.add_parser("build", help="Build a target portfolio.")
    _add_build_args(build_parser)
    build_parser.set_defaults(func=cmd_portfolio_build)

    risk_parser = portfolio_subparsers.add_parser("risk", help="Inspect a saved portfolio report.")
    add_config_arg(risk_parser)
    risk_parser.add_argument("--portfolio", default="latest")
    risk_parser.add_argument("--path", type=Path)
    risk_parser.add_argument("--json", action="store_true")
    risk_parser.set_defaults(func=cmd_portfolio_risk)

    rebalance_parser = portfolio_subparsers.add_parser("rebalance-plan", help="Create a rebalance plan.")
    _add_build_args(rebalance_parser)
    rebalance_parser.add_argument("--current", type=Path, required=True)
    rebalance_parser.add_argument("--min-trade-weight", type=float, default=0.0)
    rebalance_parser.add_argument("--max-turnover", type=float)
    rebalance_parser.set_defaults(func=cmd_portfolio_rebalance_plan)

    backtest_parser = portfolio_subparsers.add_parser("backtest", help="Backtest a portfolio strategy.")
    _add_build_args(backtest_parser)
    backtest_parser.add_argument("--from-date", required=True)
    backtest_parser.add_argument("--to-date", required=True)
    backtest_parser.add_argument("--rebalance-days", type=int, default=5)
    backtest_parser.add_argument("--fee-bps", type=float, default=0.0)
    backtest_parser.add_argument("--slippage-bps", type=float, default=0.0)
    backtest_parser.set_defaults(func=cmd_portfolio_backtest)

    report_parser = portfolio_subparsers.add_parser("report", help="Manage saved portfolio reports.")
    report_subparsers = report_parser.add_subparsers(dest="report_command", required=True)
    report_list_parser = report_subparsers.add_parser("list", help="List saved portfolio reports.")
    add_config_arg(report_list_parser)
    report_list_parser.add_argument("--json", action="store_true")
    report_list_parser.set_defaults(func=cmd_portfolio_report_list)
    report_latest_parser = report_subparsers.add_parser("latest", help="Show the latest portfolio report.")
    add_config_arg(report_latest_parser)
    report_latest_parser.add_argument("--json", action="store_true")
    report_latest_parser.set_defaults(func=cmd_portfolio_report_latest)
    report_show_parser = report_subparsers.add_parser("show", help="Show a saved portfolio report by path.")
    add_config_arg(report_show_parser)
    report_show_parser.add_argument("path", type=Path)
    report_show_parser.add_argument("--json", action="store_true")
    report_show_parser.set_defaults(func=cmd_portfolio_report_show)


def _add_build_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--from", dest="source", choices=("consensus", "strategy", "report"), default="consensus")
    parser.add_argument("--strategy")
    parser.add_argument("--top", type=int, default=20)
    parser.add_argument("--weighting", choices=("equal", "score", "risk-adjusted", "liquidity-risk"), default="equal")
    parser.add_argument("--max-weight", type=float, default=0.10)
    parser.add_argument("--min-weight", type=float, default=0.0)
    parser.add_argument("--max-risk-score", type=float)
    parser.add_argument("--exclude-risk-tags")
    parser.add_argument("--market", choices=("sh", "sz", "bj"))
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--json", action="store_true")
    add_output_arg(parser)
    parser.add_argument("--save", action="store_true")


def cmd_portfolio_build(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    if args.source == "report" and not args.strategy:
        raise ValueError("--strategy is required when --from report")
    report = build_portfolio(
        config,
        source=args.source,
        strategy=args.strategy,
        top=args.top,
        weighting=args.weighting,
        max_weight=args.max_weight,
        min_weight=args.min_weight,
        max_risk_score=args.max_risk_score,
        exclude_risk_tags=_parse_csv(args.exclude_risk_tags),
        market=args.market,
        as_of=None if args.as_of == "latest" else parse_iso_date(args.as_of),
    )
    if args.save:
        save_portfolio_report(config.paths.data_root, report)
    _emit_portfolio_report(report, json_mode=args.json, output=getattr(args, "output", None) or getattr(args, "to", None))
    return 0


def cmd_portfolio_risk(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    doc = _load_portfolio_doc(config, args)
    holdings = [_holding_from_dict(row) for row in doc.get("holdings") or doc.get("target_holdings") or []]
    risk = check_portfolio_risk(holdings)
    payload = {
        "holdings_count": len(holdings),
        "max_single_weight": risk.summary.get("max_single_weight"),
        "market_exposure": risk.summary.get("market_exposure"),
        "risk_tag_distribution": risk.summary.get("risk_tag_distribution"),
        "avg_risk_score": risk.summary.get("avg_risk_score"),
        "high_risk_stock_count": risk.summary.get("high_risk_stock_count"),
        "low_liquidity_stock_count": risk.summary.get("low_liquidity_stock_count"),
        "weight_sum": risk.summary.get("weight_sum"),
        "risk_check": risk.to_dict(),
    }
    if args.json:
        print_json(normalize_output_data(payload))
    else:
        print_key_values(
            "portfolio risk",
            [
                ("持仓数量", payload["holdings_count"]),
                ("最大单票权重", payload["max_single_weight"]),
                ("市场暴露", json.dumps(payload["market_exposure"], ensure_ascii=False, default=str)),
                ("风险标签分布", json.dumps(payload["risk_tag_distribution"], ensure_ascii=False, default=str)),
                ("平均 risk_score", payload["avg_risk_score"]),
                ("高风险股票数量", payload["high_risk_stock_count"]),
                ("低流动性股票数量", payload["low_liquidity_stock_count"]),
                ("权重合计", payload["weight_sum"]),
                ("风险检查结果", "通过" if payload["risk_check"]["passed"] else "未通过"),
            ],
        )
    return 0


def cmd_portfolio_rebalance_plan(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    target = build_portfolio(
        config,
        source=args.source,
        strategy=args.strategy,
        top=args.top,
        weighting=args.weighting,
        max_weight=args.max_weight,
        min_weight=args.min_weight,
        max_risk_score=args.max_risk_score,
        exclude_risk_tags=_parse_csv(args.exclude_risk_tags),
        market=args.market,
        as_of=None if args.as_of == "latest" else parse_iso_date(args.as_of),
    )
    current = load_current_holdings_csv(args.current)
    plan = build_rebalance_plan(
        current,
        [_holding_from_dict(row) for row in target.holdings],
        as_of=target.as_of,
        min_trade_weight=args.min_trade_weight,
        max_turnover=args.max_turnover,
    )
    if getattr(args, "save", False):
        save_rebalance_plan(config.paths.data_root, plan)
    _emit_rebalance_plan(plan, json_mode=args.json, output=getattr(args, "output", None) or getattr(args, "to", None))
    return 0


def cmd_portfolio_backtest(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    report = run_portfolio_backtest(
        config,
        source=args.source,
        strategy=args.strategy,
        from_date=parse_iso_date(args.from_date),
        to_date=parse_iso_date(args.to_date),
        top=args.top,
        weighting=args.weighting,
        rebalance_days=args.rebalance_days,
        max_weight=args.max_weight,
        min_weight=args.min_weight,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        market=args.market,
    )
    if getattr(args, "save", False):
        save_portfolio_backtest_report(config.paths.data_root, report)
    _emit_backtest_report(report, json_mode=args.json, output=getattr(args, "output", None) or getattr(args, "to", None))
    return 0


def cmd_portfolio_report_list(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    rows = list_portfolio_reports(config.paths.data_root)
    if args.json:
        print_json(normalize_output_data(rows))
    else:
        print_table(["as_of", "generated_at", "source", "data_run_id", "holdings", "path"], rows)
    return 0


def cmd_portfolio_report_latest(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    doc = load_latest_portfolio_report(config.paths.data_root)
    if doc is None:
        raise FileNotFoundError("latest portfolio report not found")
    if args.json:
        print_json(normalize_output_data(doc))
    else:
        print(render_portfolio_markdown(doc), end="")
    return 0


def cmd_portfolio_report_show(args: argparse.Namespace) -> int:
    doc = load_portfolio_report(args.path)
    if args.json:
        print_json(normalize_output_data(doc))
    else:
        print(render_portfolio_markdown(doc), end="")
    return 0


def _emit_portfolio_report(report: PortfolioReport, *, json_mode: bool, output: Path | None) -> None:
    payload = report.to_dict()
    if output is not None:
        write_json_atomic(output, payload)
    if json_mode:
        print_json(normalize_output_data(payload))
        return
    print_key_values(
        "portfolio build",
        [
            ("source", payload.get("source")),
            ("as_of", payload.get("as_of")),
            ("holdings", len(payload.get("holdings") or [])),
            ("summary", json.dumps(payload.get("summary"), ensure_ascii=False, default=str)),
            ("risk_summary", json.dumps(payload.get("risk_summary"), ensure_ascii=False, default=str)),
        ],
    )
    print_table(
        ["market", "symbol", "weight", "score", "source_strategy", "candidate_type", "risk_flags", "tags", "reason"],
        payload.get("holdings") or [],
    )


def _emit_rebalance_plan(plan: RebalancePlan, *, json_mode: bool, output: Path | None) -> None:
    payload = plan.to_dict()
    if output is not None:
        write_json_atomic(output, payload)
    if json_mode:
        print_json(normalize_output_data(payload))
        return
    print_key_values(
        "rebalance plan",
        [
            ("as_of", payload.get("as_of")),
            ("turnover", payload.get("turnover")),
            ("risk_summary", json.dumps(payload.get("risk_summary"), ensure_ascii=False, default=str)),
            ("diagnostics", json.dumps(payload.get("diagnostics"), ensure_ascii=False, default=str)),
        ],
    )
    print_table(["market", "symbol", "current_weight", "target_weight", "delta_weight", "action", "reason"], payload.get("weight_changes") or [])


def _emit_backtest_report(report: PortfolioBacktestReport, *, json_mode: bool, output: Path | None) -> None:
    payload = report.to_dict()
    if output is not None:
        write_json_atomic(output, payload)
    if json_mode:
        print_json(normalize_output_data(payload))
        return
    print_key_values(
        "portfolio backtest",
        [
            ("total_return", payload.get("total_return")),
            ("annual_return", payload.get("annual_return")),
            ("max_drawdown", payload.get("max_drawdown")),
            ("volatility", payload.get("volatility")),
            ("win_rate", payload.get("win_rate")),
            ("turnover", payload.get("turnover")),
            ("avg_holdings", payload.get("avg_holdings")),
            ("max_single_weight", payload.get("max_single_weight")),
            ("market_exposure", json.dumps(payload.get("market_exposure"), ensure_ascii=False, default=str)),
        ],
    )
    print_table(["signal_date", "buy_date", "sell_date", "holdings", "period_return", "equity", "turnover", "missing_prices"], payload.get("periods") or [])


def _load_portfolio_doc(config, args) -> dict[str, object]:
    if getattr(args, "path", None) is not None:
        return load_portfolio_report(args.path)
    if getattr(args, "portfolio", "latest") == "latest":
        doc = load_latest_portfolio_report(config.paths.data_root)
        if doc is None:
            raise FileNotFoundError("latest portfolio report not found")
        return doc
    path = Path(args.portfolio)
    if path.exists():
        return load_portfolio_report(path)
    doc = load_latest_portfolio_report(config.paths.data_root)
    if doc is None:
        raise FileNotFoundError("latest portfolio report not found")
    return doc


def _holding_from_dict(row: dict[str, object]) -> Holding:
    return Holding(
        market=str(row.get("market") or "").lower(),
        symbol=str(row.get("symbol") or ""),
        weight=float(row.get("weight") or 0.0),
        score=float(row.get("score")) if row.get("score") is not None else None,
        source_strategy=str(row.get("source_strategy") or ""),
        source_strategies=[str(item) for item in row.get("source_strategies") or []],
        candidate_type=str(row.get("candidate_type") or "") or None,
        risk_flags=[str(item) for item in row.get("risk_flags") or []],
        tags=[str(item) for item in row.get("tags") or []],
        reason=str(row.get("reason") or ""),
        risk_score=float(row.get("risk_score")) if row.get("risk_score") is not None else None,
        factor_values=dict(row.get("factor_values") or {}),
    )


def _parse_csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())
