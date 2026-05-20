from __future__ import annotations

import argparse


_EXAMPLES: dict[str, list[str]] = {
    "daily": [
        "tdx-stocks init",
        "tdx-stocks sync",
        "tdx-stocks run daily",
        "tdx-stocks report",
    ],
    "backtest": [
        "tdx-stocks init",
        "tdx-stocks sync",
        "tdx-stocks run backtest",
    ],
    "portfolio": [
        "tdx-stocks init",
        "tdx-stocks sync",
        "tdx-stocks run portfolio",
        "tdx-stocks ui",
    ],
}


def register_examples_command(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("examples", help="Show common command examples.")
    parser.add_argument("topic", nargs="?", choices=tuple(_EXAMPLES))
    parser.set_defaults(func=cmd_examples)


def cmd_examples(args: argparse.Namespace) -> int:
    topics = [args.topic] if args.topic else ["daily", "backtest", "portfolio"]
    print("Common commands:")
    for topic in topics:
        print("")
        print(f"{topic}:")
        for line in _EXAMPLES[topic]:
            print(f"  {line}")
    return 0
