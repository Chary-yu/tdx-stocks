from __future__ import annotations

import argparse
import os
from pathlib import Path

from ..config.loader import resolve_task_config_path
from ..console import print_json
from ..progress import RunProgress
from ..io_utils import write_json_atomic, write_text_atomic
from ..logging_config import configure_event_logging
from ..reports.opening import open_report_if_needed, print_report_path
from ..runner.outputs import ensure_run_report_markdown, main_report_path
from ..runner import (
    build_latest_run_report,
    build_run_plan,
    dispatch_run,
    load_run_config,
    render_run_plan,
    save_latest_run_report,
)


RUN_CONFIG_PRESETS: dict[str, Path] = {
    "daily": Path("experiments/daily.toml"),
    "signal": Path("experiments/signal.toml"),
    "portfolio": Path("experiments/portfolio.toml"),
    "rebalance": Path("experiments/rebalance.toml"),
    "backtest": Path("experiments/backtest.toml"),
    "grid": Path("experiments/grid_search.toml"),
}


def cmd_run(args: argparse.Namespace) -> int:
    config_path = _resolve_run_config(args.config)
    project_root = _discover_project_root(config_path)
    previous_cwd = Path.cwd()
    try:
        if project_root.exists():
            os.chdir(project_root)
        configure_event_logging()
        run_config = load_run_config(config_path)
        plan = build_run_plan(run_config)
        if args.explain or args.dry_run:
            if args.json:
                print_json(plan)
            else:
                print(render_run_plan(plan))
            return 0
        progress = None if args.json or args.no_progress else RunProgress(run_config.task_type)
        if progress is not None:
            progress.start()
        result = dispatch_run(run_config, dry_run=args.dry_run, progress=progress)
        if progress is not None:
            progress.finish(result.status)
        if args.output is not None:
            if args.json:
                write_json_atomic(args.output, result.to_dict())
            else:
                write_text_atomic(args.output, f"{result.task_type}: {result.status}\n")
        save_latest_run_report(run_config.app_config.paths.data_root, build_latest_run_report(run_config, result))
        if args.json:
            print_json(result.to_dict())
        else:
            report_path = main_report_path(result.outputs)
            if report_path is not None:
                if report_path.suffix.lower() == ".md" and result.task_type != "daily":
                    ensure_run_report_markdown(report_path, result, app_config=run_config.app_config)
                print_report_path(report_path, json_mode=False)
                open_report_if_needed(args, report_path, json_mode=False)
            else:
                print(f"{result.task_type}: {result.status}")
        return 0
    finally:
        try:
            os.chdir(previous_cwd)
        except FileNotFoundError:
            # Test suites and temporary workspaces may delete the original cwd.
            os.chdir(Path(__file__).resolve().parents[3])


def register_run_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "run",
        help="Run a preset name or TOML experiment config.",
        description="Run one of the built-in presets or a custom .toml config file.",
        epilog="Built-in presets: daily, signal, portfolio, rebalance, backtest, grid.",
    )
    parser.add_argument("config", help="Preset name or path to a TOML experiment config.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--explain", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress messages while the run task is executing.")
    parser.set_defaults(func=cmd_run)


def _resolve_run_config(value: str | Path) -> Path:
    return resolve_task_config_path(value)


def _discover_project_root(config_path: Path) -> Path:
    path = config_path if config_path.is_absolute() else (Path.cwd() / config_path)
    for candidate in (path.parent, *path.parents):
        if (candidate / "experiments").exists():
            return candidate
    return path.parent
