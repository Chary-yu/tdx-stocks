from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from ..config import load_config
from ..console import print_json, print_key_values
from ..daily import (
    list_daily_reports,
    load_daily_report,
    load_latest_daily_report,
    render_daily_json,
    render_daily_markdown,
    run_daily_workflow,
)
from ..io_utils import write_json_atomic, write_text_atomic
from ..query import load_latest_manifest, normalize_output_data
from .common import add_config_arg, add_output_arg, validate_output_alias


def register_daily_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    hidden: bool = False,
) -> None:
    daily_parser = subparsers.add_parser("daily", help=argparse.SUPPRESS if hidden else "Daily orchestration commands.")
    daily_subparsers = daily_parser.add_subparsers(dest="daily_command", required=True)

    run_parser = daily_subparsers.add_parser("run", help="Run the daily research workflow.")
    _add_common_args(run_parser)
    run_parser.add_argument("--strategies")
    run_parser.add_argument("--strategy-limit", type=int)
    run_parser.add_argument("--min-score", type=float)
    run_parser.add_argument("--min-hit", type=int)
    run_parser.add_argument("--portfolio-top", type=int)
    run_parser.add_argument("--portfolio-weighting")
    run_parser.add_argument("--current-holdings", type=Path)
    run_parser.add_argument("--skip-strategies", action="store_true")
    run_parser.add_argument("--skip-portfolio", action="store_true")
    run_parser.add_argument("--skip-rebalance", action="store_true")
    run_parser.add_argument("--skip-report", action="store_true")
    run_parser.add_argument("--build", action="store_true")
    run_parser.set_defaults(func=cmd_daily_run)

    status_parser = daily_subparsers.add_parser("status", help="Show the latest daily status.")
    add_config_arg(status_parser)
    status_parser.add_argument("--json", action="store_true")
    status_parser.set_defaults(func=cmd_daily_status)

    report_parser = daily_subparsers.add_parser("report", help="Show a saved daily report.")
    add_config_arg(report_parser)
    report_parser.add_argument("--as-of", default="latest")
    report_parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    report_parser.add_argument("--output", type=Path)
    report_parser.set_defaults(func=cmd_daily_report)


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    add_config_arg(parser)
    parser.add_argument("--as-of", default="latest")
    parser.add_argument("--json", action="store_true")
    add_output_arg(parser)


def cmd_daily_run(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    report = run_daily_workflow(
        config,
        as_of=None if args.as_of == "latest" else date.fromisoformat(args.as_of),
        strategies=_parse_csv(args.strategies),
        strategy_limit=args.strategy_limit,
        min_score=args.min_score,
        min_hit=args.min_hit,
        portfolio_top=args.portfolio_top,
        portfolio_weighting=args.portfolio_weighting,
        current_holdings=str(args.current_holdings) if args.current_holdings else None,
        skip_strategies=args.skip_strategies,
        skip_portfolio=args.skip_portfolio,
        skip_rebalance=args.skip_rebalance,
        skip_report=args.skip_report,
        build_data=args.build,
    )
    if args.output is not None:
        if args.json:
            write_json_atomic(args.output, render_daily_json(report.report))
        else:
            write_text_atomic(args.output, report.markdown)
    if args.json:
        print_json(normalize_output_data(report.report.to_dict()))
    else:
        print(report.markdown, end="")
    return 0


def cmd_daily_status(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    manifest = None
    try:
        manifest = load_latest_manifest(config.paths.data_root)
    except FileNotFoundError:
        manifest = None
    latest_daily = load_latest_daily_report(config.paths.data_root)
    daily_reports = list_daily_reports(config.paths.data_root)
    daily_outputs = dict(latest_daily.get("outputs") or {}) if latest_daily else {}
    payload = {
        "latest_trade_date": manifest.get("summary", {}).get("trade_date") if manifest else None,
        "latest_data_run_id": manifest.get("run_id") if manifest else None,
        "latest_daily_run_at": latest_daily.get("generated_at") if latest_daily else None,
        "strategy_report_exists": bool((config.paths.data_root / "reports" / "strategies" / "latest").exists()),
        "compare_exists": bool(daily_outputs.get("compare_json")),
        "consensus_exists": bool(daily_outputs.get("consensus_json")),
        "portfolio_exists": bool(daily_outputs.get("latest_json") or (config.paths.data_root / "reports" / "portfolios" / "latest.json").exists()),
        "daily_report_exists": bool(latest_daily),
        "warnings": len(latest_daily.get("warnings") or []) if latest_daily else 0,
        "errors": len(latest_daily.get("errors") or []) if latest_daily else 0,
        "daily_report_count": len(daily_reports),
    }
    if args.json:
        print_json(normalize_output_data(payload))
    else:
        print_key_values(
            "daily status",
            [
                ("最新交易日", payload["latest_trade_date"]),
                ("最新数据版本", payload["latest_data_run_id"]),
                ("最近 daily run 时间", payload["latest_daily_run_at"]),
                ("策略报告是否存在", payload["strategy_report_exists"]),
                ("compare 是否存在", payload["compare_exists"]),
                ("consensus 是否存在", payload["consensus_exists"]),
                ("portfolio 是否存在", payload["portfolio_exists"]),
                ("daily report 是否存在", payload["daily_report_exists"]),
                ("warnings", payload["warnings"]),
                ("errors", payload["errors"]),
            ],
        )
    return 0


def cmd_daily_report(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    doc = load_daily_report(config.paths.data_root, args.as_of)
    if doc is None:
        raise FileNotFoundError(f"daily report not found for as_of={args.as_of!r}")
    if args.format == "json":
        payload = render_daily_json(_to_report(doc))
        if args.output is not None:
            write_json_atomic(args.output, payload)
        print_json(normalize_output_data(payload))
    else:
        markdown = render_daily_markdown(_to_report(doc))
        if args.output is not None:
            write_text_atomic(args.output, markdown)
        print(markdown, end="")
    return 0


def _parse_csv(value: str | None) -> list[str] | None:
    if value is None:
        return None
    values = [item.strip() for item in value.split(",")]
    return [item for item in values if item]


def _to_report(doc) -> object:
    from ..daily.models import DailyRunReport

    return DailyRunReport(
        schema_version=str(doc.get("schema_version") or "daily-report-v1"),
        app_version=str(doc.get("app_version") or ""),
        as_of=str(doc.get("as_of") or "latest"),
        generated_at=str(doc.get("generated_at") or ""),
        data_run_id=doc.get("data_run_id"),
        status=str(doc.get("status") or ""),
        steps=list(doc.get("steps") or []),
        summary=dict(doc.get("summary") or {}),
        data_quality=dict(doc.get("data_quality") or {}),
        strategy_summary=dict(doc.get("strategy_summary") or {}),
        consensus_summary=dict(doc.get("consensus_summary") or {}),
        portfolio_summary=dict(doc.get("portfolio_summary") or {}),
        rebalance_summary=dict(doc.get("rebalance_summary") or {}),
        warnings=list(doc.get("warnings") or []),
        errors=list(doc.get("errors") or []),
        outputs=dict(doc.get("outputs") or {}),
    )
