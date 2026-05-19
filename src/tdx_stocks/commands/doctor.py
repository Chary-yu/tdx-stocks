from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

from ..config import AppConfig, load_config
from ..console import print_key_values
from ..query import load_latest_manifest
from .common import add_config_arg


def register_doctor_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("doctor", help="Diagnose setup issues.")
    add_config_arg(parser)
    parser.set_defaults(func=cmd_doctor)


def cmd_doctor(args: argparse.Namespace) -> int:
    config = _load_optional_config(args.config)
    config_path = args.config or Path("tdx_stocks.toml")
    errors: list[str] = []
    rows: list[tuple[str, object]] = []

    rows.append(("config_file", config_path.as_posix()))
    rows.append(("config_exists", config_path.exists()))
    if not config_path.exists():
        errors.append(f"config file not found: {config_path}")

    rows.append(("data_root", config.paths.data_root.as_posix()))
    rows.append(("data_root_exists", config.paths.data_root.exists()))
    if not config.paths.data_root.exists():
        errors.append(f"data_root not found: {config.paths.data_root}")

    for label, path in (
        ("tdx_vipdoc", config.paths.tdx_vipdoc),
        ("tdx_export", config.paths.tdx_export),
    ):
        exists = path != Path(".") and path.exists()
        rows.append((f"{label}_exists", exists))
        if path == Path(".") or not exists:
            errors.append(f"{label} is not configured or missing: {path}")

    latest_dataset = config.paths.data_root / "latest.json"
    rows.append(("latest_dataset_exists", latest_dataset.exists()))
    if not latest_dataset.exists():
        errors.append(f"latest dataset not found: {latest_dataset}")
    else:
        try:
            manifest = load_latest_manifest(config.paths.data_root)
            rows.append(("latest_data_version", manifest.get("run_id")))
            rows.append(("latest_trade_date", manifest.get("summary", {}).get("trade_date")))
        except FileNotFoundError:
            errors.append(f"latest dataset manifest not found: {latest_dataset}")

    reports_root = config.paths.data_root / "reports"
    rows.append(("reports_dir_exists", reports_root.exists()))
    if not reports_root.exists():
        errors.append(f"reports directory not found: {reports_root}")

    for module in ("duckdb", "pyarrow", "streamlit"):
        spec = importlib.util.find_spec(module)
        rows.append((f"{module}_installed", spec is not None))
        if spec is None:
            if module == "streamlit":
                errors.append(
                    "Streamlit is required for UI.\n"
                    "Install:\n  python -m pip install -e \".[web]\""
                )
            else:
                errors.append(f"missing dependency: {module}")

    if errors:
        for message in errors:
            print(f"error: {message}", file=sys.stderr)
    print_key_values("doctor", rows)
    return 0 if not errors else 1


def _load_optional_config(path: Path | None) -> AppConfig:
    if path is not None and path.exists():
        return load_config(path)
    return AppConfig()
