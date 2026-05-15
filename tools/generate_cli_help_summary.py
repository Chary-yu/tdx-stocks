from __future__ import annotations

import argparse
from pathlib import Path

from tdx_stocks.cli import build_parser


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a markdown summary of the tdx-stocks CLI."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/cli_help_summary.md"),
        help="Output markdown path, or - for stdout.",
    )
    args = parser.parse_args()

    markdown = render_markdown(build_parser())
    if str(args.output) == "-":
        print(markdown)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
        print(f"wrote {args.output}")
    return 0


def render_markdown(parser: argparse.ArgumentParser) -> str:
    lines: list[str] = []
    lines.append("# tdx-stocks CLI 摘要")
    lines.append("")
    if parser.description:
        lines.append(parser.description)
        lines.append("")
    lines.append("## 支持命令")
    lines.append("")
    lines.append("| 命令 | 功能 |")
    lines.append("| --- | --- |")

    subparsers_action = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )
    command_help = {item.dest: item.help or "" for item in subparsers_action._choices_actions}
    for command_name, _command_parser in subparsers_action.choices.items():
        lines.append(f"| `{command_name}` | {command_help.get(command_name, '')} |")

    lines.append("")
    lines.append("## 命令参数")
    lines.append("")
    for command_name, command_parser in subparsers_action.choices.items():
        lines.append(f"### `{command_name}`")
        lines.append("")
        lines.extend(render_actions(command_parser))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


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


if __name__ == "__main__":
    raise SystemExit(main())
