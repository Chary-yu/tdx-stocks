from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path

from ..config.loader import RUNNABLE_TASKS, load_config_bundle, resolve_task_config_path
from ..console import print_json
from ..runner.schema import validate_run_config


def register_config_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("config", help="Validate and inspect run config bundles.")
    config_subparsers = parser.add_subparsers(dest="config_command", required=True)

    validate_parser = config_subparsers.add_parser("validate", help="Validate config bundle(s).")
    validate_parser.add_argument("target", nargs="?", default="daily", help="Preset/task config path, or 'all'.")
    validate_parser.add_argument("--json", action="store_true")
    validate_parser.set_defaults(func=cmd_config_validate)

    inspect_parser = config_subparsers.add_parser("inspect", help="Inspect merged config for a runnable task.")
    inspect_parser.add_argument("target", help="Runnable task preset or TOML path, e.g. daily.")
    inspect_parser.add_argument("--json", action="store_true")
    inspect_parser.set_defaults(func=cmd_config_inspect)


def cmd_config_validate(args: argparse.Namespace) -> int:
    targets = _resolve_validate_targets(str(args.target))
    rows: list[dict[str, object]] = []
    has_error = False
    for target in targets:
        try:
            path = resolve_task_config_path(target)
            bundle = load_config_bundle(path)
            task_type, task_name, warnings = validate_run_config(bundle.merged_config)
            rows.append(
                {
                    "target": target,
                    "path": bundle.task_path.as_posix(),
                    "status": "ok",
                    "task_type": task_type,
                    "task_name": task_name,
                    "warnings": list(bundle.warnings) + list(warnings),
                    "issues": _classify_issues(list(bundle.warnings) + list(warnings)),
                }
            )
        except Exception as exc:  # noqa: BLE001
            has_error = True
            rows.append({"target": target, "status": "error", "error": str(exc)})
    if args.json:
        print_json({"results": rows, "ok": not has_error})
    else:
        for row in rows:
            if row["status"] == "ok":
                print(f"[ok] {row['target']}: {row['path']} ({row['task_type']})")
            else:
                print(f"[error] {row['target']}: {row['error']}")
    return 1 if has_error else 0


def cmd_config_inspect(args: argparse.Namespace) -> int:
    path = resolve_task_config_path(args.target)
    bundle = load_config_bundle(path)
    task_type, task_name, warnings = validate_run_config(bundle.merged_config)
    payload = {
        "task_path": bundle.task_path.as_posix(),
        "task_type": task_type,
        "task_name": task_name,
        "auxiliary_sources": {name: source.as_posix() for name, source in bundle.auxiliary_sources.items()},
        "warnings": list(bundle.warnings) + list(warnings),
        "merged_config": bundle.merged_config,
    }
    if args.json:
        print_json(payload)
    else:
        print(f"Task: {task_type}")
        print(f"Name: {task_name}")
        print(f"Config: {bundle.task_path.as_posix()}")
        print("Merged Aux Paths:")
        for key in ("macro_filter", "event_calendar", "risk_management", "pre_filter", "stop_loss", "order_execution", "alerts", "logging", "risk_scenario"):
            node = bundle.merged_config.get(key)
            if isinstance(node, Mapping):
                for dotted in _flatten_dotted(key, node):
                    print(f"  {dotted}")
        if bundle.auxiliary_sources:
            print("Auxiliary:")
            for name, source in sorted(bundle.auxiliary_sources.items()):
                print(f"  {name}: {source.as_posix()}")
        else:
            print("Auxiliary: (none)")
    return 0


def _resolve_validate_targets(target: str) -> list[str]:
    if target != "all":
        return [target]
    return list(RUNNABLE_TASKS)


def _classify_issues(messages: list[str]) -> dict[str, list[str]]:
    grouped = {"warning": [], "unsupported_feature": []}
    for message in messages:
        if message.startswith("unsupported_feature:"):
            grouped["unsupported_feature"].append(message)
        else:
            grouped["warning"].append(message)
    return grouped


def _flatten_dotted(prefix: str, value: Mapping[str, object]) -> list[str]:
    rows: list[str] = []
    for key, child in sorted(value.items()):
        dotted = f"{prefix}.{key}"
        rows.append(dotted)
        if isinstance(child, Mapping):
            rows.extend(_flatten_dotted(dotted, child))
    return rows
