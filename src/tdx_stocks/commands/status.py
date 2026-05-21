from __future__ import annotations

import argparse
from pathlib import Path

from ..config import AppConfig, load_config
from ..console import print_json, print_key_values
from ..daily import load_latest_daily_report
from ..portfolio import load_latest_portfolio_report
from ..query import load_latest_manifest, normalize_output_data
from ..runner.outputs import load_latest_run_report
from .common import add_config_arg


def register_status_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("status", help="Show project status.")
    add_config_arg(parser)
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_status)


def cmd_status(args: argparse.Namespace) -> int:
    config = _load_optional_config(args.config)
    payload = _build_status_payload(config, config_path=args.config or Path("tdx_stocks.toml"))
    if args.json:
        print_json(normalize_output_data(payload))
        return 0
    print_key_values(
        "status",
        [
            ("config_file", payload["config_file"]),
            ("config_exists", payload["config_exists"]),
            ("data_root", payload["data_root"]),
            ("data_root_exists", payload["data_root_exists"]),
            ("latest_data_version", payload["latest_data_version"]),
            ("latest_trade_date", payload["latest_trade_date"]),
            ("latest_run_status", payload["latest_run_status"]),
            ("latest_daily_report", payload["latest_daily_report"]),
            ("latest_portfolio_report", payload["latest_portfolio_report"]),
            ("warnings", payload["warnings"]),
            ("errors", payload["errors"]),
        ],
    )
    return 0


def _load_optional_config(path: Path | None) -> AppConfig:
    if path is not None and path.exists():
        return load_config(path)
    return AppConfig()


def _build_status_payload(config: AppConfig, *, config_path: Path) -> dict[str, object]:
    data_root = config.paths.data_root
    latest_data = None
    latest_trade_date = None
    try:
        latest_data = load_latest_manifest(data_root)
        latest_trade_date = latest_data.get("summary", {}).get("trade_date")
    except FileNotFoundError:
        latest_data = None
    latest_run = load_latest_run_report(data_root)
    latest_daily = load_latest_daily_report(data_root)
    latest_portfolio = load_latest_portfolio_report(data_root)
    return {
        "config_file": config_path.as_posix(),
        "config_exists": config_path.exists(),
        "data_root": data_root.as_posix(),
        "data_root_exists": data_root.exists(),
        "latest_data_version": latest_data.get("run_id") if latest_data else None,
        "latest_trade_date": latest_trade_date,
        "latest_run_status": latest_run.get("status") if latest_run else None,
        "latest_run_report": (data_root / "report_payloads" / "latest_run.json").as_posix(),
        "latest_daily_report": (data_root / "reports" / f"daily_{latest_daily.get('as_of')}.md").as_posix() if latest_daily else None,
        "latest_portfolio_report": (data_root / "report_payloads" / "portfolios" / "latest.json").as_posix() if latest_portfolio else None,
        "warnings": len((latest_run or {}).get("warnings") or []),
        "errors": len((latest_run or {}).get("errors") or []),
    }
