from __future__ import annotations

import argparse
import os
import re
import sys
import traceback
from pathlib import Path

from .commands.doctor import register_doctor_command
from .commands.help import register_help_command
from .commands.init import register_init_command
from .commands.query import register_query_group
from .commands.report import register_report_command
from .commands.run import register_run_command
from .commands.status import register_status_command
from .commands.sync import register_sync_group
from .commands.ui import register_ui_command
from .config import AppConfig, load_config
from .exit_codes import CliError, ExitCode, UsageError
from .strategies.registry import load_plugins


class TdxArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # noqa: D401
        raise UsageError(message)

    def format_help(self) -> str:
        text = super().format_help()
        visible = self._visible_subcommands()
        if visible:
            text = self._rewrite_usage_subcommands(text, visible)
        lines = [line for line in text.splitlines() if "==SUPPRESS==" not in line]
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    def _visible_subcommands(self) -> list[str]:
        for action in self._actions:
            if isinstance(action, argparse._SubParsersAction):
                return [choice.dest for choice in action._choices_actions if choice.help != argparse.SUPPRESS]
        return []

    @staticmethod
    def _rewrite_usage_subcommands(text: str, visible: list[str]) -> str:
        if not visible:
            return text
        lines = text.splitlines()
        if not lines:
            return text
        replacement = "{" + ",".join(visible) + "}"
        for index, line in enumerate(lines):
            if "{" in line and "}" in line:
                lines[index] = re.sub(r"\{[^}]+\}", replacement, line, count=1)
        return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    enable_plugins = _should_enable_plugins(argv)
    argv = _strip_enable_plugins(argv)
    try:
        if enable_plugins:
            _load_plugins_for_argv(argv)
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        _print_cli_error(f"failed to load plugins: {exc}", debug=_should_debug(argv), exc=exc)
        return int(ExitCode.UNKNOWN_ERROR)
    parser = build_parser(load_default_plugins=False)
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(exc.code)

    try:
        result = args.func(args)
    except KeyboardInterrupt:
        print("error: interrupted", file=sys.stderr)
        return int(ExitCode.INTERRUPTED)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(exc.code)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.INPUT_MISSING)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE_ERROR)
    except RuntimeError as exc:
        _print_cli_error(str(exc), debug=getattr(args, "debug", False), exc=exc)
        return int(ExitCode.UNKNOWN_ERROR)
    except Exception as exc:  # noqa: BLE001
        _print_cli_error(str(exc), debug=getattr(args, "debug", False), exc=exc)
        return int(ExitCode.UNKNOWN_ERROR)
    return int(result)


def build_parser(*, load_default_plugins: bool = False) -> argparse.ArgumentParser:
    if load_default_plugins:
        load_plugins(AppConfig().paths.plugin_dir)
    parser = TdxArgumentParser(
        prog="tdx-stocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="TDX Stocks - local stock research workflow",
        epilog=(
            "Common commands:\n"
            "  tdx-stocks init\n"
            "  tdx-stocks sync\n"
            "  tdx-stocks run daily\n"
            "  tdx-stocks query stock 600519.SH\n"
            "  tdx-stocks query factors\n"
            "  tdx-stocks query strategy trend-strength --symbol 600519.SH --explain\n"
            "  tdx-stocks report\n"
            "  tdx-stocks status\n"
            "  tdx-stocks ui\n"
            "  tdx-stocks doctor\n"
            "  tdx-stocks help run\n\n"
            "Common workflow:\n"
            "  tdx-stocks init\n"
            "  tdx-stocks sync\n"
            "  tdx-stocks run daily --explain\n"
            "  tdx-stocks report\n\n"
            "Tip: use `tdx-stocks help <topic>` for built-in guidance."
        ),
    )
    parser.add_argument(
        "--enable-plugins",
        action="store_true",
        help="Load strategy plugins from the configured plugin directory.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print full tracebacks for unexpected errors.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_init_command(subparsers)
    register_doctor_command(subparsers)
    register_sync_group(subparsers)
    register_run_command(subparsers)
    register_report_command(subparsers)
    register_query_group(subparsers)
    register_status_command(subparsers)
    register_ui_command(subparsers)
    register_help_command(subparsers)
    return parser


def _load_plugins_for_argv(argv: list[str]) -> None:
    config_path = _find_config_arg(argv)
    config = load_config(config_path) if config_path is not None else AppConfig()
    load_plugins(config.paths.plugin_dir)


def _should_enable_plugins(argv: list[str]) -> bool:
    env_value = os.getenv("TDX_STOCKS_ENABLE_PLUGINS", "").strip().lower()
    if env_value in {"1", "true", "yes", "on"}:
        return True
    return "--enable-plugins" in argv


def _strip_enable_plugins(argv: list[str]) -> list[str]:
    return [item for item in argv if item != "--enable-plugins"]


def _should_debug(argv: list[str]) -> bool:
    return "--debug" in argv


def _find_config_arg(argv: list[str]) -> Path | None:
    for index, item in enumerate(argv):
        if item in {"--config", "-c"} and index + 1 < len(argv):
            return Path(argv[index + 1])
        if item.startswith("--config="):
            return Path(item.split("=", 1)[1])
    return None


def _print_cli_error(message: str, *, debug: bool, exc: Exception | None = None) -> None:
    if exc is None:
        rendered = message
    else:
        rendered = f"{exc.__class__.__name__}: {message}"
    print(f"error: {rendered}", file=sys.stderr)
    if debug and exc is not None:
        traceback.print_exception(type(exc), exc, exc.__traceback__, file=sys.stderr)
if __name__ == "__main__":
    raise SystemExit(main())
