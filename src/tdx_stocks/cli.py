from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .commands.audit import (
    cmd_doctor as _audit_cmd_doctor,
    cmd_verify_adjustment as _audit_cmd_verify_adjustment,
    register_audit_group,
    register_legacy_audit_aliases,
)
from .commands.data import (
    cmd_actions_status as _data_cmd_actions_status,
    cmd_build as _data_cmd_build,
    cmd_quality_report as _data_cmd_quality_report,
    cmd_rebuild as _data_cmd_rebuild,
    cmd_update_actions as _data_cmd_update_actions,
    register_data_group,
    register_legacy_data_aliases,
)
from .commands.query import (
    cmd_export as _query_cmd_export,
    cmd_head as _query_cmd_head,
    cmd_schema as _query_cmd_schema,
    cmd_sql as _query_cmd_sql,
    cmd_stock as _query_cmd_stock,
    cmd_status as _query_cmd_status,
    cmd_tables as _query_cmd_tables,
    register_legacy_query_aliases,
    register_query_group,
)
from .commands.strategy import (
    cmd_strategy_list as _strategy_cmd_strategy_list,
    cmd_strategy_run as _strategy_cmd_strategy_run,
    cmd_strategy_run_trend_strength as _strategy_cmd_strategy_run_trend_strength,
    register_strategy_group,
)
from .commands.portfolio import register_portfolio_group
from .commands.factors import (
    cmd_factors_describe as _factors_cmd_describe,
    cmd_factors_list as _factors_cmd_list,
    cmd_factors_rank as _factors_cmd_rank,
    cmd_factors_schema as _factors_cmd_schema,
    register_factors_group,
)
from .commands.sync import cmd_sync as _sync_cmd_sync, register_sync_group
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


def main(argv: list[str] | None = None) -> int:
    try:
        _load_plugins_for_argv(sys.argv[1:] if argv is None else argv)
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
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


def build_parser(*, load_default_plugins: bool = True) -> argparse.ArgumentParser:
    if load_default_plugins:
        load_plugins(AppConfig().paths.plugin_dir)
    parser = TdxArgumentParser(
        prog="tdx-stocks",
        epilog="Tip: use `tdx-stocks help-summary` to generate the markdown CLI manual.",
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
    register_audit_group(
        subparsers,
        cmd_doctor=cmd_doctor,
        cmd_verify_adjustment=cmd_verify_adjustment,
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
    )
    register_strategy_group(
        subparsers,
        cmd_strategy_list=cmd_strategy_list,
        cmd_strategy_run=cmd_strategy_run,
    )
    register_portfolio_group(subparsers)
    register_factors_group(
        subparsers,
        cmd_factors_list=cmd_factors_list,
        cmd_factors_describe=cmd_factors_describe,
        cmd_factors_schema=cmd_factors_schema,
        cmd_factors_rank=cmd_factors_rank,
    )
    init_parser = subparsers.add_parser("init-config", help="Write a default TOML config.")
    init_parser.add_argument("--path", type=Path, default=Path("tdx_stocks.toml"))
    init_parser.set_defaults(func=cmd_init_config)

    register_sync_group(subparsers)

    help_summary_parser = subparsers.add_parser(
        "help-summary",
        help="Generate a markdown summary of the CLI.",
    )
    help_summary_parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/cli_help_summary.md"),
        help="Output markdown path, or - for stdout.",
    )
    help_summary_parser.set_defaults(func=cmd_help_summary)
    _register_legacy_aliases(subparsers)
    return parser


def _load_plugins_for_argv(argv: list[str]) -> None:
    config_path = _find_config_arg(argv)
    config = load_config(config_path) if config_path is not None else AppConfig()
    load_plugins(config.paths.plugin_dir)


def _find_config_arg(argv: list[str]) -> Path | None:
    for index, item in enumerate(argv):
        if item in {"--config", "-c"} and index + 1 < len(argv):
            return Path(argv[index + 1])
        if item.startswith("--config="):
            return Path(item.split("=", 1)[1])
    return None


def _register_legacy_aliases(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    register_legacy_data_aliases(
        subparsers,
        cmd_build=cmd_build,
        cmd_rebuild=cmd_rebuild,
        cmd_update_actions=cmd_update_actions,
        cmd_actions_status=cmd_actions_status,
    )
    register_legacy_audit_aliases(
        subparsers,
        cmd_doctor=cmd_doctor,
        cmd_verify_adjustment=cmd_verify_adjustment,
    )
    register_legacy_query_aliases(
        subparsers,
        tables=tuple(TABLES),
        cmd_status=_query_cmd_status,
        cmd_tables=_query_cmd_tables,
        cmd_schema=_query_cmd_schema,
        cmd_head=_query_cmd_head,
        cmd_stock=_query_cmd_stock,
        cmd_sql=_query_cmd_sql,
        cmd_export=_query_cmd_export,
    )


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [column.strip() for column in value.split(",")]
    return [column for column in columns if column]


def cmd_init_config(args: argparse.Namespace) -> int:
    write_default_config(args.path)
    print(f"wrote {args.path}")
    return 0


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
