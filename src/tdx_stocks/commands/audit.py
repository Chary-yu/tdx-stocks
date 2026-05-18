from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable

from .common import add_config_arg


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
