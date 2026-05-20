from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..config import load_config
from ..console import print_json, print_key_values
from ..strategies.registry import get_strategy, list_strategies
from ..query import (
    TABLES,
    build_select_sql,
    build_stock_sql,
    ensure_read_only_sql,
    export_query_csv,
    fetch_dicts,
    normalize_output_data,
    open_query_context,
    parquet_glob,
    print_rows,
    sql_literal,
    table_columns,
    table_summary,
)
from ..console import print_notice
from .common import add_config_arg, add_output_arg, add_query_args, add_stock_args
from .common import validate_output_alias
from .output import write_rows


DEFAULT_STOCK_COLUMNS: tuple[str, ...] = (
    "market",
    "symbol",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "adj_close",
    "adj_factor",
    "pct_chg",
    "ret_5",
    "ma20",
)


def register_query_group(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
    hidden: bool = False,
) -> None:
    query_parser = subparsers.add_parser(
        "query",
        help=argparse.SUPPRESS if hidden else "Read-only inspection and query commands.",
        description="Commands that inspect the latest versioned dataset.",
    )
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)

    stock_parser = query_subparsers.add_parser(
        "stock",
        help="Show merged daily rows and factors for one stock code.",
    )
    add_config_arg(stock_parser)
    add_stock_args(stock_parser)
    stock_parser.add_argument("--columns", help="Comma-separated output columns.")
    stock_parser.add_argument("--full", action="store_true")
    stock_parser.add_argument("--format", choices=("table", "json", "csv"), default="table")
    add_output_arg(stock_parser)
    stock_parser.set_defaults(func=cmd_stock)

    table_parser = query_subparsers.add_parser("table", help="Show rows from a latest table.")
    add_config_arg(table_parser)
    add_query_args(table_parser, default_limit=20)
    table_parser.set_defaults(func=cmd_head)

    tables_parser = query_subparsers.add_parser("tables", help="Show latest table summaries.")
    add_config_arg(tables_parser)
    tables_parser.add_argument("--json", action="store_true")
    tables_parser.set_defaults(func=cmd_tables)

    schema_parser = query_subparsers.add_parser("schema", help="Show a table schema.")
    add_config_arg(schema_parser)
    schema_parser.add_argument("table", nargs="?", default="factor_full", choices=TABLES)
    schema_parser.add_argument("--json", action="store_true")
    schema_parser.set_defaults(func=cmd_schema)

    sql_parser = query_subparsers.add_parser("sql", help="Run SQL against latest table views.")
    add_config_arg(sql_parser)
    sql_parser.add_argument("sql")
    sql_parser.add_argument("--limit", type=int, default=100)
    sql_parser.add_argument(
        "--unsafe-sql",
        action="store_true",
        help="Allow arbitrary SQL. Disabled by default because DuckDB can expose file and function access.",
    )
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    export_parser = query_subparsers.add_parser("export", help="Export a filtered table query to CSV.")
    add_config_arg(export_parser)
    add_query_args(export_parser, default_limit=1000)
    add_output_arg(export_parser, required=True)
    export_parser.add_argument("--no-limit", action="store_true")
    export_parser.set_defaults(func=cmd_export)

    factors_parser = query_subparsers.add_parser("factors", help="List available factors.")
    factors_parser.add_argument("--json", action="store_true")
    factors_parser.set_defaults(func=cmd_factors)

    factor_parser = query_subparsers.add_parser("factor", help="Describe one factor.")
    factor_parser.add_argument("factor")
    factor_parser.add_argument("legacy_args", nargs="*")
    factor_parser.add_argument("--json", action="store_true")
    factor_parser.set_defaults(func=cmd_factor)

    rank_parser = query_subparsers.add_parser("rank", help="Rank one factor on a chosen date.")
    add_config_arg(rank_parser)
    rank_parser.add_argument("factor")
    rank_parser.add_argument("--as-of", default="latest")
    rank_parser.add_argument("--limit", type=int, default=50)
    rank_parser.add_argument("--market", choices=("sh", "sz", "bj"))
    rank_parser.add_argument("--json", action="store_true")
    rank_parser.set_defaults(func=cmd_rank)

    strategies_parser = query_subparsers.add_parser("strategies", help="List available strategies.")
    strategies_parser.add_argument("--json", action="store_true")
    strategies_parser.add_argument("--grouped", action="store_true")
    strategies_parser.set_defaults(func=cmd_query_strategies)

    strategy_parser = query_subparsers.add_parser("strategy", help="Inspect one strategy.")
    add_config_arg(strategy_parser)
    strategy_parser.add_argument("strategy")
    strategy_parser.add_argument("--json", action="store_true")
    strategy_parser.add_argument("--symbol")
    strategy_parser.add_argument("--explain", action="store_true")
    strategy_parser.add_argument("--as-of", default="latest")
    strategy_parser.add_argument("--limit", type=int, default=20)
    strategy_parser.add_argument("--min-score", type=float, default=60.0)
    strategy_parser.add_argument("--min-amount-ma20", type=float, default=50_000_000.0)
    strategy_parser.add_argument("--candidate-type")
    strategy_parser.add_argument("--include-excluded", action="store_true")
    strategy_parser.add_argument("--show-excluded-limit", type=int, default=20)
    strategy_parser.set_defaults(func=cmd_query_strategy)


def parse_columns(value: str | None) -> list[str] | None:
    if value is None:
        return None
    columns = [column.strip() for column in value.split(",")]
    return [column for column in columns if column]


def summarize_cached_table(con, root: Path, date_column: str) -> dict[str, object]:
    files = sorted(root.rglob("*.parquet")) if root.exists() else []
    summary: dict[str, object] = {
        "exists": bool(files),
        "parquet_files": len(files),
        "rows": 0,
        "symbols": 0,
        "min_date": None,
        "max_date": None,
        "cache_path": root.as_posix(),
    }
    if not files:
        return summary

    source = f"read_parquet('{sql_literal(parquet_glob(root))}', hive_partitioning=true)"
    row = con.execute(
        f"""
        SELECT
            count(*) AS rows,
            count(DISTINCT market || ':' || symbol) AS symbols,
            min({date_column}) AS min_date,
            max({date_column}) AS max_date
        FROM {source}
        """
    ).fetchone()
    summary.update(
        {
            "rows": row[0],
            "symbols": row[1],
            "min_date": str(row[2]) if row[2] is not None else None,
            "max_date": str(row[3]) if row[3] is not None else None,
        }
    )
    return summary


def _is_select_like(sql: str) -> bool:
    stripped = sql.lstrip().lower()
    return stripped.startswith(("select", "with"))


def _sql_has_top_level_keyword(sql: str, keyword: str) -> bool:
    target = keyword.lower()
    depth = 0
    in_single = False
    in_double = False
    index = 0
    while index < len(sql):
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < len(sql) else ""
        if in_single:
            if char == "'" and nxt == "'":
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            if char == '"':
                in_double = False
            index += 1
            continue
        if char == "-" and nxt == "-":
            newline = sql.find("\n", index + 2)
            if newline == -1:
                return False
            index = newline + 1
            continue
        if char == "/" and nxt == "*":
            end = sql.find("*/", index + 2)
            if end == -1:
                return False
            index = end + 2
            continue
        if char == "'":
            in_single = True
            index += 1
            continue
        if char == '"':
            in_double = True
            index += 1
            continue
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")" and depth > 0:
            depth -= 1
            index += 1
            continue
        if depth == 0 and (char.isalpha() or char == "_"):
            start = index
            index += 1
            while index < len(sql) and (sql[index].isalnum() or sql[index] == "_"):
                index += 1
            if sql[start:index].lower() == target:
                return True
            continue
        index += 1
    return False


def cmd_tables(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [table_summary(ctx.con, ctx.manifest, table) for table in TABLES]
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(["table", "rows", "symbols", "min_date", "max_date", "disk", "path"], rows)
    finally:
        ctx.close()
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        rows = [{"column": name, "type": type_} for name, type_ in table_columns(ctx.con, args.table)]
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(["column", "type"], rows)
    finally:
        ctx.close()
    return 0


def cmd_head(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_select_sql(
            ctx.con,
            args.table,
            columns=parse_columns(args.columns),
            symbol=args.symbol,
            market=args.market,
            from_date=args.from_date,
            to_date=args.to_date,
            where=args.where,
            order_by=args.order_by,
            desc=args.desc,
            limit=args.limit,
        )
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_sql(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        if not getattr(args, "unsafe_sql", False):
            raise ValueError("query sql is disabled by default; pass --unsafe-sql to run arbitrary SQL")
        sql = ensure_read_only_sql(args.sql)
        if args.limit and _is_select_like(sql) and not _sql_has_top_level_keyword(sql, "limit"):
            sql = f"{sql.rstrip().rstrip(';')}\nLIMIT {args.limit}"
        columns, rows = fetch_dicts(ctx.con, sql)
        if args.json:
            print_json(normalize_output_data(rows))
        else:
            print_rows(columns, rows)
    finally:
        ctx.close()
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    validate_output_alias(args)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_select_sql(
            ctx.con,
            args.table,
            columns=parse_columns(args.columns),
            symbol=args.symbol,
            market=args.market,
            from_date=args.from_date,
            to_date=args.to_date,
            where=args.where,
            order_by=args.order_by,
            desc=args.desc,
            limit=None if args.no_limit else args.limit,
        )
        count = export_query_csv(ctx.con, sql, args.output)
        if getattr(args, "json", False):
            print_json({"exported_rows": count, "path": args.output.as_posix()})
        else:
            print(f"exported rows={count} path={args.output}")
    finally:
        ctx.close()
    return 0


def cmd_stock(args: argparse.Namespace) -> int:
    if getattr(args, "json", False) and getattr(args, "format", "table") != "table":
        raise ValueError("use either --json or --format, not both")
    format_name = "json" if getattr(args, "json", False) else getattr(args, "format", "table")
    output_path = getattr(args, "output", None) or getattr(args, "to", None)
    config = load_config(args.config)
    ctx = open_query_context(config)
    try:
        sql = build_stock_sql(
            ctx.con,
            args.symbol,
            from_date=args.from_date,
            to_date=args.to_date,
            desc=args.desc,
            limit=None if args.no_limit else args.limit,
            adjust=args.adjust,
        )
        columns, rows = fetch_dicts(ctx.con, sql)
        selected_columns = _select_stock_columns(columns, getattr(args, "columns", None), getattr(args, "full", False))
        selected_rows = [{column: row.get(column) for column in selected_columns} for row in rows]
        if getattr(args, "full", False):
            print_notice("建议使用 --columns 控制列数，或使用 --format csv --output 导出全字段。")
        write_rows(selected_rows, columns=selected_columns, format_name=format_name, to=output_path)
    finally:
        ctx.close()
    return 0


def cmd_factors(args: argparse.Namespace) -> int:
    from .factors import cmd_factors_list as _cmd_factors_list

    return _cmd_factors_list(args)


def cmd_factor(args: argparse.Namespace) -> int:
    if args.factor in {"list", "describe", "schema", "rank"} or getattr(args, "legacy_args", []):
        raise ValueError(
            "legacy query factor subcommands are no longer supported; use "
            "'tdx-stocks query factors', 'tdx-stocks query factor <name>', "
            "'tdx-stocks query schema factor_full', or 'tdx-stocks query rank <name>'"
        )
    from .factors import cmd_factors_describe as _cmd_factors_describe

    try:
        return _cmd_factors_describe(args)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def cmd_rank(args: argparse.Namespace) -> int:
    if args.factor in {"list", "describe", "schema", "rank"} or getattr(args, "legacy_args", []):
        raise ValueError(
            "legacy query factor subcommands are no longer supported; use "
            "'tdx-stocks query factors', 'tdx-stocks query factor <name>', "
            "'tdx-stocks query schema factor_full', or 'tdx-stocks query rank <name>'"
        )
    from .factors import cmd_factors_rank as _cmd_factors_rank

    try:
        return _cmd_factors_rank(args)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc


def cmd_query_strategies(args: argparse.Namespace) -> int:
    rows = [
        {
            "name": definition.name,
            "display_name": definition.display_name or definition.name,
            "group": definition.group,
            "style": definition.style,
            "description": definition.description,
            "candidate_types": ", ".join(definition.candidate_types) or "无",
            "risk_tags": ", ".join(definition.risk_tags) or "无",
            "aliases": ", ".join(definition.aliases) or "无",
        }
        for definition in list_strategies()
    ]
    if getattr(args, "grouped", False):
        grouped: dict[str, dict[str, object]] = {}
        for row in rows:
            group = str(row["group"])
            item = grouped.setdefault(
                group,
                {
                    "group": group,
                    "strategy_count": 0,
                    "strategies": [],
                },
            )
            item["strategy_count"] = int(item["strategy_count"]) + 1
            item["strategies"].append(str(row["name"]))
        output = sorted(
            (
                {
                    "group": group,
                    "strategy_count": item["strategy_count"],
                    "strategies": ", ".join(sorted(item["strategies"])),
                }
                for group, item in grouped.items()
            ),
            key=lambda item: item["group"],
        )
        if getattr(args, "json", False):
            print_json(normalize_output_data(output))
        else:
            print_rows(["group", "strategy_count", "strategies"], output)
        return 0
    if getattr(args, "json", False):
        print_json(normalize_output_data(rows))
    else:
        print_rows(["name", "display_name", "group", "style", "aliases", "description"], rows)
    return 0


def cmd_query_strategy(args: argparse.Namespace) -> int:
    try:
        definition = get_strategy(args.strategy)
    except KeyError as exc:
        raise ValueError(str(exc)) from exc
    if bool(args.symbol) != bool(args.explain):
        raise ValueError("--symbol and --explain must be used together")
    if args.explain:
        from .strategy import cmd_strategy_explain as _cmd_strategy_explain

        explain_args = argparse.Namespace(
            config=getattr(args, "config", None),
            strategy=args.strategy,
            symbol=args.symbol,
            as_of=args.as_of,
            json=args.json,
            output=getattr(args, "output", None),
            to=getattr(args, "to", None),
            market=None,
            limit=args.limit,
            min_score=args.min_score,
            min_amount_ma20=args.min_amount_ma20,
            candidate_type=args.candidate_type,
            include_excluded=args.include_excluded,
            show_excluded_limit=args.show_excluded_limit,
            explain_symbol=args.symbol,
        )
        return _cmd_strategy_explain(explain_args)

    payload = {
        "name": definition.name,
        "display_name": definition.display_name or definition.name,
        "description": definition.description,
        "group": definition.group,
        "style": definition.style,
        "required_fields": list(definition.required_fields),
        "optional_fields": list(definition.optional_fields),
        "default_params": definition.default_params.to_dict(),
        "param_schema": definition.param_schema,
        "candidate_types": list(definition.candidate_types),
        "risk_tags": list(definition.risk_tags),
        "introduced_in": definition.introduced_in,
        "aliases": list(definition.aliases),
        "supported_research_capabilities": list(definition.research_capabilities()),
    }
    if getattr(args, "json", False):
        print_json(normalize_output_data(payload))
    else:
        print_key_values(
            f"strategy: {definition.name}",
            [
                ("策略名称", payload["display_name"]),
                ("策略分组", payload["group"]),
                ("策略风格", payload["style"]),
                ("策略说明", payload["description"]),
                ("依赖因子", ", ".join(payload["required_fields"]) or "无"),
                ("可选因子", ", ".join(payload["optional_fields"]) or "无"),
                ("默认参数", json.dumps(payload["default_params"], ensure_ascii=False, default=str)),
                ("参数模式", json.dumps(payload["param_schema"], ensure_ascii=False, default=str)),
                ("候选类型", ", ".join(payload["candidate_types"]) or "无"),
                ("风险标签", ", ".join(payload["risk_tags"]) or "无"),
                ("支持能力", ", ".join(payload["supported_research_capabilities"]) or "无"),
                ("别名", ", ".join(payload["aliases"]) or "无"),
                ("首次引入", payload["introduced_in"]),
            ],
        )
    return 0


def _select_stock_columns(
    available_columns: list[str],
    columns_value: str | None,
    full: bool,
) -> list[str]:
    if full:
        return list(available_columns)
    if columns_value:
        selected = parse_columns(columns_value) or []
        unknown = [column for column in selected if column not in available_columns]
        if unknown:
            raise ValueError(f"unknown stock columns: {', '.join(unknown)}")
        return selected
    default_columns = [column for column in DEFAULT_STOCK_COLUMNS if column in available_columns]
    return default_columns or list(available_columns)
