from __future__ import annotations

import argparse
from pathlib import Path


def render_markdown(parser: argparse.ArgumentParser) -> str:
    lines: list[str] = []
    lines.append("# tdx-stocks CLI 摘要")
    lines.append("")
    if parser.description:
        lines.append(parser.description)
        lines.append("")

    visible, advanced, hidden = _collect_subcommands(parser)
    primary_names = {"data", "init", "run", "ui", "examples", "doctor", "status", "report"}
    primary = [item for item in visible if item[0] in primary_names]
    primary.sort(key=lambda item: item[0])
    advanced.sort(key=lambda item: item[0])
    lines.append("## 支持命令")
    lines.append("")
    lines.append("| 命令 | 功能 |")
    lines.append("| --- | --- |")
    for command_name, command_parser, help_text in primary:
        lines.append(f"| `{command_name}` | {help_text} |")

    if advanced:
        lines.append("")
        lines.append("## Advanced commands")
        lines.append("")
        lines.append("| 命令 | 功能 |")
        lines.append("| --- | --- |")
        for command_name, _command_parser, help_text in advanced:
            lines.append(f"| `{command_name}` | {help_text} |")

    if hidden:
        lines.append("")
        lines.append("## 兼容别名")
        lines.append("")
        lines.append("| 命令 | 替代 |")
        lines.append("| --- | --- |")
        for command_name, _command_parser, replacement in hidden:
            lines.append(f"| `{command_name}` | `{replacement}` |")

    lines.append("")
    lines.append("## 命令参数")
    lines.append("")
    _render_command_tree(parser, lines, path=(), level=3)
    return "\n".join(lines).rstrip() + "\n"


def _collect_subcommands(
    parser: argparse.ArgumentParser,
) -> tuple[
    list[tuple[str, argparse.ArgumentParser, str]],
    list[tuple[str, argparse.ArgumentParser, str]],
    list[tuple[str, argparse.ArgumentParser, str]],
]:
    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    visible: list[tuple[str, argparse.ArgumentParser, str]] = []
    advanced: list[tuple[str, argparse.ArgumentParser, str]] = []
    hidden: list[tuple[str, argparse.ArgumentParser, str]] = []
    advanced_names = {"strategy", "portfolio", "factors", "query", "audit", "daily", "sync", "help-summary"}
    for choice_action in subparsers_action._choices_actions:
        command_name = choice_action.dest
        command_parser = subparsers_action.choices[command_name]
        if choice_action.help == argparse.SUPPRESS:
            if command_name in advanced_names:
                help_text = command_parser.description or ""
                advanced.append((command_name, command_parser, help_text))
            else:
                replacement = getattr(command_parser, "_legacy_target", command_name)
                hidden.append((command_name, command_parser, str(replacement)))
        else:
            help_text = choice_action.help or ""
            visible.append((command_name, command_parser, help_text))
    return visible, advanced, hidden


def _render_command_tree(
    parser: argparse.ArgumentParser,
    lines: list[str],
    *,
    path: tuple[str, ...],
    level: int,
) -> None:
    if path:
        lines.append(f"{'#' * level} `{ ' '.join(path) }`")
        lines.append("")
        lines.extend(render_actions(parser))
        lines.append("")

    visible, _advanced, _hidden = _collect_subcommands(parser) if _has_subcommands(parser) else ([], [], [])
    if visible:
        lines.append(f"{'#' * level} 子命令")
        lines.append("")
        lines.append("| 命令 | 功能 |")
        lines.append("| --- | --- |")
        for command_name, command_parser, help_text in visible:
            lines.append(f"| `{command_name}` | {help_text} |")
        lines.append("")
        for command_name, command_parser, _help_text in visible:
            _render_command_tree(command_parser, lines, path=path + (command_name,), level=level + 1)


def _has_subcommands(parser: argparse.ArgumentParser) -> bool:
    return any(isinstance(action, argparse._SubParsersAction) for action in parser._actions)


def render_actions(parser: argparse.ArgumentParser) -> list[str]:
    lines: list[str] = []
    lines.append("| 参数 | 说明 |")
    lines.append("| --- | --- |")
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            continue
        label = render_action_label(action)
        if not label:
            continue
        help_text = action.help or ""
        if action.default not in (None, argparse.SUPPRESS, False) and action.option_strings:
            help_text = f"{help_text} (default: {action.default})".strip()
        lines.append(f"| `{label}` | {help_text} |")
    return lines


def render_action_label(action: argparse.Action) -> str:
    if action.option_strings:
        return ", ".join(action.option_strings)
    if action.nargs == 0:
        return action.dest
    return action.metavar or action.dest


def write_markdown(parser: argparse.ArgumentParser, output: Path | str) -> Path | None:
    markdown = render_markdown(parser)
    if str(output) == "-":
        print(markdown, end="")
        return None
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path
