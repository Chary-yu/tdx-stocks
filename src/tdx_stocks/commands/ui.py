from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def cmd_ui(args: argparse.Namespace) -> int:
    script = Path(__file__).resolve().parents[1] / "web" / "app.py"
    env = os.environ.copy()
    if args.config is not None:
        env["TDX_STOCKS_CONFIG"] = str(args.config)
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(script),
        "--server.address",
        args.host,
        "--server.port",
        str(args.port),
    ]
    if args.no_browser:
        cmd.extend(["--server.headless", "true"])
    return subprocess.call(cmd, env=env)


def register_ui_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("ui", help="Launch the read-only Web UI.")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--no-browser", action="store_true")
    parser.set_defaults(func=cmd_ui)
