from __future__ import annotations

import argparse
from pathlib import Path

from tdx_stocks.cli import build_parser
from tdx_stocks.help_summary import write_markdown


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

    result = write_markdown(build_parser(), args.output)
    if result is not None:
        print(f"wrote {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
