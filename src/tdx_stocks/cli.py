from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from .commands.audit import (
    cmd_doctor as _audit_cmd_doctor,
)
from .commands.audit import (
    cmd_verify_adjustment as _audit_cmd_verify_adjustment,
)
from .commands.audit import (
    register_audit_group,
)
from .commands.daily import register_daily_group
from .commands.data import (
    cmd_actions_status as _data_cmd_actions_status,
)
from .commands.data import (
    cmd_build as _data_cmd_build,
)
from .commands.data import (
    cmd_quality_report as _data_cmd_quality_report,
)
from .commands.data import (
    cmd_rebuild as _data_cmd_rebuild,
)
from .commands.data import (
    cmd_update_actions as _data_cmd_update_actions,
)
from .commands.data import (
    register_data_group,
)
from .commands.doctor import cmd_doctor as _doctor_cmd_doctor
from .commands.doctor import register_doctor_command
from .commands.examples import cmd_examples as _examples_cmd_examples
from .commands.examples import register_examples_command
from .commands.init import cmd_init as _init_cmd_init
from .commands.init import register_init_command
from .commands.factors import (
    cmd_factors_describe as _factors_cmd_describe,
)
from .commands.factors import (
    cmd_factors_list as _factors_cmd_list,
)
from .commands.factors import (
    cmd_factors_rank as _factors_cmd_rank,
)
from .commands.factors import (
    cmd_factors_schema as _factors_cmd_schema,
)
from .commands.factors import (
    register_factors_group,
)
from .commands.portfolio import register_portfolio_group
from .commands.report import cmd_report as _report_cmd_report
from .commands.report import register_report_command
from .commands.run import cmd_run as _run_cmd_run
from .commands.run import register_run_command
from .commands.query import (
    cmd_export as _query_cmd_export,
)
from .commands.query import (
    cmd_head as _query_cmd_head,
)
from .commands.query import (
    cmd_schema as _query_cmd_schema,
)
from .commands.query import (
    cmd_sql as _query_cmd_sql,
)
from .commands.query import (
    cmd_status as _query_cmd_status,
)
from .commands.query import (
    cmd_stock as _query_cmd_stock,
)
from .commands.query import (
    cmd_tables as _query_cmd_tables,
)
from .commands.query import (
    register_query_group,
)
from .commands.strategy import (
    cmd_strategy_list as _strategy_cmd_strategy_list,
)
from .commands.strategy import (
    cmd_strategy_run as _strategy_cmd_strategy_run,
)
from .commands.strategy import (
    cmd_strategy_run_trend_strength as _strategy_cmd_strategy_run_trend_strength,
)
from .commands.strategy import (
    register_strategy_group,
)
from .commands.sync import cmd_sync as _sync_cmd_sync
from .commands.sync import register_sync_group
from .commands.ui import cmd_ui as _ui_cmd_ui
from .commands.ui import register_ui_command
from .commands.status import cmd_status as _status_cmd_status
from .commands.status import register_status_command
from .config import AppConfig, load_config, write_default_config
from .exit_codes import (
    CliError,
    ExitCode,
    UsageError,
)
from .help_summary import write_markdown
from .query import TABLES
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
    argv = _rewrite_legacy_argv(sys.argv[1:] if argv is None else argv)
    enable_plugins = _should_enable_plugins(argv)
    argv = _strip_enable_plugins(argv)
    try:
        if enable_plugins:
            _load_plugins_for_argv(argv)
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"error: failed to load plugins: {exc}", file=sys.stderr)
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
        print(f"error: {exc}", file=sys.stderr)
        return int(ExitCode.UNKNOWN_ERROR)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
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
            "  tdx-stocks data sync\n"
            "  tdx-stocks run <config.toml>\n"
            "  tdx-stocks ui\n"
            "  tdx-stocks examples\n"
            "  tdx-stocks doctor\n"
            "  tdx-stocks status\n"
            "  tdx-stocks report\n\n"
            "Common workflow:\n"
            "  tdx-stocks init\n"
            "  tdx-stocks data sync\n"
            "  tdx-stocks run experiments/daily.toml\n"
            "  tdx-stocks report\n\n"
            "Advanced commands:\n"
            "  strategy\n"
            "  portfolio\n"
            "  factors\n"
            "  query\n"
            "  audit\n"
            "  daily\n"
            "  sync\n"
            "  help-summary\n\n"
            "Tip: use `tdx-stocks help-summary` to generate the markdown CLI manual."
        ),
    )
    parser.add_argument(
        "--enable-plugins",
        action="store_true",
        help="Load strategy plugins from the configured plugin directory.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_data_group(
        subparsers,
        cmd_build=cmd_build,
        cmd_rebuild=cmd_rebuild,
        cmd_update_actions=cmd_update_actions,
        cmd_actions_status=cmd_actions_status,
        cmd_quality_report=cmd_quality_report,
    )
    register_init_command(subparsers)
    register_run_command(subparsers)
    register_ui_command(subparsers)
    register_examples_command(subparsers)
    register_doctor_command(subparsers)
    register_status_command(subparsers)
    register_report_command(subparsers)
    register_audit_group(
        subparsers,
        cmd_doctor=cmd_doctor,
        cmd_verify_adjustment=cmd_verify_adjustment,
        hidden=True,
    )
    register_query_group(
        subparsers,
        tables=tuple(TABLES),
        cmd_status=_query_cmd_status,
        cmd_stock=_query_cmd_stock,
        cmd_head=_query_cmd_head,
        cmd_tables=_query_cmd_tables,
        cmd_schema=_query_cmd_schema,
        cmd_sql=_query_cmd_sql,
        cmd_export=_query_cmd_export,
        hidden=True,
    )
    register_strategy_group(
        subparsers,
        cmd_strategy_list=cmd_strategy_list,
        cmd_strategy_run=cmd_strategy_run,
        hidden=True,
    )
    register_portfolio_group(subparsers, hidden=True)
    register_daily_group(subparsers, hidden=True)
    register_factors_group(
        subparsers,
        cmd_factors_list=cmd_factors_list,
        cmd_factors_describe=cmd_factors_describe,
        cmd_factors_schema=cmd_factors_schema,
        cmd_factors_rank=cmd_factors_rank,
        hidden=True,
    )
    init_parser = subparsers.add_parser("init-config", help=argparse.SUPPRESS)
    init_parser._legacy_target = "init"
    init_parser.add_argument("--path", type=Path, default=Path("tdx_stocks.toml"))
    init_parser.set_defaults(func=cmd_init_config)

    register_sync_group(subparsers, hidden=True)

    help_summary_parser = subparsers.add_parser(
        "help-summary",
        help=argparse.SUPPRESS,
    )
    help_summary_parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/cli_help_summary.md"),
        help="Output markdown path, or - for stdout.",
    )
    help_summary_parser.set_defaults(func=cmd_help_summary)
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


def _find_config_arg(argv: list[str]) -> Path | None:
    for index, item in enumerate(argv):
        if item in {"--config", "-c"} and index + 1 < len(argv):
            return Path(argv[index + 1])
        if item.startswith("--config="):
            return Path(item.split("=", 1)[1])
    return None


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [column.strip() for column in value.split(",")]
    return [column for column in columns if column]


def cmd_init_config(args: argparse.Namespace) -> int:
    write_default_config(args.path)
    print(f"wrote {args.path}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    return _init_cmd_init(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    return _audit_cmd_doctor(args)


def cmd_build(args: argparse.Namespace) -> int:
    return _data_cmd_build(args)


def cmd_rebuild(args: argparse.Namespace) -> int:
    return _data_cmd_rebuild(args)


def cmd_update_actions(args: argparse.Namespace) -> int:
    return _data_cmd_update_actions(args)


def cmd_sync(args: argparse.Namespace) -> int:
    return _sync_cmd_sync(args)


def cmd_run(args: argparse.Namespace) -> int:
    return _run_cmd_run(args)


def cmd_ui(args: argparse.Namespace) -> int:
    return _ui_cmd_ui(args)


def cmd_status(args: argparse.Namespace) -> int:
    return _query_cmd_status(args)


def cmd_actions_status(args: argparse.Namespace) -> int:
    return _data_cmd_actions_status(args)


def cmd_quality_report(args: argparse.Namespace) -> int:
    return _data_cmd_quality_report(args)


def cmd_verify_adjustment(args: argparse.Namespace) -> int:
    return _audit_cmd_verify_adjustment(args)


def cmd_tables(args: argparse.Namespace) -> int:
    return _query_cmd_tables(args)


def cmd_schema(args: argparse.Namespace) -> int:
    return _query_cmd_schema(args)


def cmd_head(args: argparse.Namespace) -> int:
    return _query_cmd_head(args)


def cmd_sql(args: argparse.Namespace) -> int:
    return _query_cmd_sql(args)


def cmd_export(args: argparse.Namespace) -> int:
    return _query_cmd_export(args)


def cmd_help_summary(args: argparse.Namespace) -> int:
    parser = build_parser()
    result = write_markdown(parser, args.output)
    if result is not None:
        print(f"wrote {result}")
    return 0


def cmd_stock(args: argparse.Namespace) -> int:
    return _query_cmd_stock(args)


def _rewrite_legacy_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    legacy_map: dict[str, list[str]] = {
        "build": ["data", "build"],
        "rebuild": ["data", "rebuild"],
        "update-actions": ["data", "update"],
        "actions-status": ["data", "status"],
        "verify-adjustment": ["audit", "verify"],
        "tables": ["query", "tables"],
        "schema": ["query", "schema"],
        "head": ["query", "table"],
        "stock": ["query", "price"],
        "sql": ["query", "sql"],
        "export": ["query", "export"],
        "sync": ["data", "sync"],
    }
    first = argv[0]
    replacement = legacy_map.get(first)
    if replacement is None:
        return argv
    return [*replacement, *argv[1:]]


def cmd_strategy_run(args: argparse.Namespace) -> int:
    return _strategy_cmd_strategy_run(args)


def cmd_strategy_run_trend_strength(args: argparse.Namespace) -> int:
    return _strategy_cmd_strategy_run_trend_strength(args)


def cmd_strategy_list(args: argparse.Namespace) -> int:
    return _strategy_cmd_strategy_list(args)


def cmd_factors_list(args: argparse.Namespace) -> int:
    return _factors_cmd_list(args)


def cmd_factors_describe(args: argparse.Namespace) -> int:
    return _factors_cmd_describe(args)


def cmd_factors_schema(args: argparse.Namespace) -> int:
    return _factors_cmd_schema(args)


def cmd_factors_rank(args: argparse.Namespace) -> int:
    return _factors_cmd_rank(args)

if __name__ == "__main__":
    raise SystemExit(main())
