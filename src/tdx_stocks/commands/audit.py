from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from ..adjustment_verify import build_adjustment_verification_report
from ..config import load_config
from ..console import print_json, print_key_values
from ..exit_codes import ExitCode, VerificationFailedError
from ..query import normalize_output_data
from ..tdx_day import iter_day_files
from .common import add_config_arg
from .common import legacy_notice as _legacy_notice


def _required_path_error(label: str, path: Path, env_name: str) -> str | None:
    if path == Path("."):
        return f"{label} is not configured; set [paths].{label} or {env_name}"
    if not path.exists():
        return f"{label} does not exist: {path}"
    return None


def cmd_doctor(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    errors: list[str] = []
    items: list[tuple[str, object]] = [
        ("tdx_vipdoc", config.paths.tdx_vipdoc),
        ("tdx_export", config.paths.tdx_export),
        ("data_root", config.paths.data_root),
    ]
    for label, path, env_name in (
        ("tdx_vipdoc", config.paths.tdx_vipdoc, "TDX_STOCKS_TDX_VIPDOC"),
        ("tdx_export", config.paths.tdx_export, "TDX_STOCKS_TDX_EXPORT"),
        ("data_root", config.paths.data_root, "TDX_STOCKS_DATA_ROOT"),
    ):
        error = _required_path_error(label, path, env_name)
        items.append((f"{label}_exists", error is None and path.exists()))
        if error is not None:
            errors.append(error)

    if not errors:
        files = list(
            iter_day_files(
                config.paths.tdx_vipdoc,
                markets=config.build.markets,
                universe=config.build.universe,
            )
        )
        items.append(("day_files", len(files)))
        for index, path in enumerate(files[:5], start=1):
            items.append((f"sample_{index}", path))
    else:
        items.append(("day_files", 0))

    for module in ("duckdb", "pyarrow"):
        try:
            imported = __import__(module)
        except ModuleNotFoundError:
            items.append((module, "missing"))
        else:
            items.append((module, getattr(imported, "__version__", "installed")))

    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
    print_key_values("doctor", items)
    return 0 if not errors else int(ExitCode.USAGE_ERROR)


def cmd_verify_adjustment(args: argparse.Namespace) -> int:
    _legacy_notice(args)
    config = load_config(args.config)
    report = build_adjustment_verification_report(
        config,
        args.symbol,
        input_path=args.input,
        from_date=args.from_date,
        to_date=args.to_date,
        threshold=args.threshold,
    )
    if args.json:
        print_json(normalize_output_data(report))
    else:
        print_key_values(
            "verify adjustment",
            [
                ("symbol", report["symbol"]),
                ("export_path", report["export_path"]),
                ("threshold", report["threshold"]),
                ("export_rows", report["export_rows"]),
                ("adj_rows", report["adj_rows"]),
                ("common_rows", report["common_rows"]),
                ("export_only_rows", report["export_only_rows"]),
                ("adj_only_rows", report["adj_only_rows"]),
                ("max_abs_error", report["max_abs_error"]),
                ("max_abs_error_date", report["max_abs_error_date"]),
                ("mean_abs_error", report["mean_abs_error"]),
                ("mismatch_count", report["mismatch_count"]),
                ("ok", report["ok"]),
            ],
        )
        if report["mismatch_samples"]:
            print("mismatch_samples:")
            for item in report["mismatch_samples"][:10]:
                print(
                    f"- {item['trade_date']}: export={item['export_close']} adj={item['adj_close']} "
                    f"abs_error={item['abs_error']}"
                )
        if report["export_only_dates"]:
            print(f"export_only_dates={', '.join(report['export_only_dates'][:10])}")
        if report["adj_only_dates"]:
            print(f"adj_only_dates={', '.join(report['adj_only_dates'][:10])}")
    return 0 if report["ok"] else int(VerificationFailedError.code)


def register_legacy_audit_aliases(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_doctor: Callable[[argparse.Namespace], int],
    cmd_verify_adjustment: Callable[[argparse.Namespace], int],
) -> None:
    verify_parser = subparsers.add_parser("verify-adjustment", help=argparse.SUPPRESS)
    verify_parser._legacy_target = "audit verify"
    add_config_arg(verify_parser)
    verify_parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    verify_parser.add_argument("--input", type=Path, help="Optional export file or directory override.")
    verify_parser.add_argument("--from-date", dest="from_date")
    verify_parser.add_argument("--to-date", dest="to_date")
    verify_parser.add_argument("--threshold", type=float, default=0.01)
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(func=cmd_verify_adjustment)

    doctor_parser = subparsers.add_parser("doctor", help=argparse.SUPPRESS)
    doctor_parser._legacy_target = "audit doctor"
    add_config_arg(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)


def register_audit_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_doctor: Callable[[argparse.Namespace], int],
    cmd_verify_adjustment: Callable[[argparse.Namespace], int],
) -> None:
    audit_parser = subparsers.add_parser(
        "audit",
        help="Audit and diagnostics commands.",
        description="Commands for environment checks and adjustment verification.",
    )
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command", required=True)

    doctor_parser = audit_subparsers.add_parser("doctor", help="Check paths and dependency imports.")
    add_config_arg(doctor_parser)
    doctor_parser.set_defaults(func=cmd_doctor)

    verify_parser = audit_subparsers.add_parser(
        "verify",
        help="Compare adj_daily against TDX export front-adjusted text.",
    )
    add_config_arg(verify_parser)
    verify_parser.add_argument("symbol", help="Stock code such as 600519.SH or sh600519.")
    verify_parser.add_argument("--input", type=Path, help="Optional export file or directory override.")
    verify_parser.add_argument("--from-date", dest="from_date")
    verify_parser.add_argument("--to-date", dest="to_date")
    verify_parser.add_argument("--threshold", type=float, default=0.01)
    verify_parser.add_argument("--json", action="store_true")
    verify_parser.set_defaults(func=cmd_verify_adjustment)
