from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date

from ..config import load_config
from ..console import print_json, print_table
from ..pipeline import parse_iso_date
from ..query import normalize_output_data, open_query_context, table_columns, table_column_names
from ..factors.registry import get_factor_definition, list_factor_definitions_by_name
from .common import add_config_arg


def register_factors_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    *,
    cmd_factors_list: Callable[[argparse.Namespace], int],
    cmd_factors_describe: Callable[[argparse.Namespace], int],
    cmd_factors_schema: Callable[[argparse.Namespace], int],
    cmd_factors_rank: Callable[[argparse.Namespace], int],
) -> None:
    factors_parser = subparsers.add_parser(
        "factors",
        help="Factor catalog and research commands.",
        description="Commands for factor catalog, schema inspection, and cross-sectional ranking.",
    )
    factors_subparsers = factors_parser.add_subparsers(dest="factors_command", required=True)

    list_parser = factors_subparsers.add_parser("list", help="List available factors.")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=cmd_factors_list)

    describe_parser = factors_subparsers.add_parser("describe", help="Describe one factor.")
    describe_parser.add_argument("factor")
    describe_parser.add_argument("--json", action="store_true")
    describe_parser.set_defaults(func=cmd_factors_describe)

    schema_parser = factors_subparsers.add_parser("schema", help="Show factor table schema.")
    add_config_arg(schema_parser)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=cmd_factors_schema)

    rank_parser = factors_subparsers.add_parser("rank", help="Rank one factor on a chosen date.")
    add_config_arg(rank_parser)
    rank_parser.add_argument("factor")
    rank_parser.add_argument("--as-of", default="latest")
    rank_parser.add_argument("--limit", type=int, default=50)
    rank_parser.add_argument("--market", choices=("sh", "sz", "bj"))
    rank_parser.add_argument("--json", action="store_true")
    rank_parser.set_defaults(func=cmd_factors_rank)


def cmd_factors_list(args: argparse.Namespace) -> int:
    rows = [definition.to_dict() for definition in list_factor_definitions_by_name()]
    if getattr(args, "json", False):
        print_json(normalize_output_data(rows))
    else:
        print_table(["name", "group", "description", "depends_on", "strategies"], rows)
    return 0


def cmd_factors_describe(args: argparse.Namespace) -> int:
    definition = get_factor_definition(args.factor)
    payload = definition.to_dict()
    if getattr(args, "json", False):
        print_json(normalize_output_data(payload))
    else:
        print_table(
            ["name", "group", "description", "depends_on", "strategies"],
            [payload],
        )
    return 0


def cmd_factors_schema(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        tables = [table for table in ("factors", "factors_xsec", "factors_quality", "factor_full") if _table_exists(ctx, table)]
        rows = [
            {
                "table": table,
                "columns": [name for name, _type in table_columns(ctx.con, table)],
            }
            for table in tables
        ]
    finally:
        ctx.close()
    if getattr(args, "json", False):
        print_json(normalize_output_data(rows))
    else:
        print_table(["table", "columns"], rows)
    return 0


def cmd_factors_rank(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    definition = get_factor_definition(args.factor)
    ctx = open_query_context(config)
    try:
        table = "factor_full" if _table_exists(ctx, "factor_full") else "factors"
        if args.factor not in table_column_names(ctx.con, table):
            raise ValueError(f"{table} has no factor column: {args.factor}")
        if args.as_of == "latest":
            row = ctx.con.execute(f"SELECT max(trade_date) FROM {table}").fetchone()
            resolved_date = row[0]
        else:
            resolved_date = parse_iso_date(args.as_of) if isinstance(args.as_of, str) else args.as_of
        if resolved_date is None:
            raise ValueError(f"no rows found in {table}")
        if not isinstance(resolved_date, date):
            raise ValueError(f"invalid as-of date: {args.as_of!r}")
        market_clause = f"AND market = '{args.market}'" if args.market else ""
        rows = ctx.con.execute(
            f"""
            SELECT
                market,
                symbol,
                trade_date,
                {definition.name} AS factor_value,
                rank() OVER (PARTITION BY trade_date ORDER BY {definition.name} DESC NULLS LAST, market, symbol) AS factor_rank
            FROM {table}
            WHERE trade_date = DATE '{resolved_date.isoformat()}'
                {market_clause}
            ORDER BY factor_value DESC NULLS LAST, market, symbol
            LIMIT {int(args.limit)}
            """
        ).fetchall()
        columns = ["market", "symbol", "trade_date", "factor_value", "factor_rank"]
        payload = [dict(zip(columns, row, strict=True)) for row in rows]
    finally:
        ctx.close()
    if getattr(args, "json", False):
        print_json(normalize_output_data(payload))
    else:
        print_table(["market", "symbol", "trade_date", "factor_value", "factor_rank"], payload)
    return 0


def _table_exists(ctx, table: str) -> bool:
    try:
        table_columns(ctx.con, table)
    except Exception:
        return False
    return True
