from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..config import AppConfig
from ..io_utils import write_text_atomic
from .stock_names import build_stock_name_map, collect_stock_keys, stock_code, stock_display

MAX_TABLE_ROWS = 50
MAX_LIST_ITEMS = 20

FIELD_LABELS: dict[str, str] = {
    "name": "报告名称",
    "status": "运行状态",
    "task_type": "任务类型",
    "as_of": "数据日期",
    "generated_at": "生成时间",
    "data_run_id": "数据批次",
    "source": "来源",
    "strategy": "策略",
    "strategy_name": "策略名称",
    "strategy_count": "策略数量",
    "consensus_count": "共振数量",
    "overlap_count": "重叠数量",
    "min_hit": "最小命中数",
    "candidate_count": "候选数量",
    "selected_count": "入选数量",
    "excluded_count": "剔除数量",
    "holding_count": "持仓数量",
    "current_holding_count": "当前持仓数",
    "target_holding_count": "目标持仓数",
    "weighting": "权重方式",
    "max_weight": "单票权重上限",
    "min_weight": "单票权重下限",
    "max_risk_score": "最大风险分",
    "exclude_risk_tags": "剔除风险标签",
    "market": "市场",
    "top": "最多持仓数",
    "passed": "是否通过",
    "violations": "违规项",
    "warnings": "警告",
    "summary": "摘要",
    "turnover": "换手率",
    "buy_count": "买入数量",
    "sell_count": "卖出数量",
    "increase_count": "增持数量",
    "reduce_count": "减持数量",
    "hold_count": "继续持有数量",
    "weight_change_count": "权重变化数量",
    "total_return": "总收益",
    "annual_return": "年化收益",
    "max_drawdown": "最大回撤",
    "win_rate": "胜率",
    "avg_period_return": "平均周期收益",
    "turnover": "换手率",
    "trade_count": "交易数量",
    "period_count": "周期数量",
    "empty_period_count": "空仓周期数量",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "result_count": "参数组合数量",
    "best_min_score": "最优最低分",
    "best_top": "最优持仓数",
    "best_hold_days": "最优持有天数",
    "best_research_score": "最优研究分",
    "best_annual_return": "最优年化收益",
    "best_max_drawdown": "最优最大回撤",
    "schema_version": "报告版本",
    "app_version": "程序版本",
    "weight_sum": "权重合计",
    "high_risk_stock_count": "高风险股票数",
    "low_liquidity_stock_count": "低流动性股票数",
    "avg_risk_score": "平均风险分",
    "max_single_weight": "最大单票权重",
    "row_count": "行数",
    "signal_markdown": "信号报告 Markdown",
    "signal_json": "信号报告 JSON",
    "signal_latest_markdown": "最新信号报告 Markdown",
    "signal_latest_json": "最新信号报告 JSON",
    "portfolio_markdown": "组合报告 Markdown",
    "portfolio_json": "组合报告 JSON",
    "portfolio_latest_markdown": "最新组合报告 Markdown",
    "portfolio_latest_json": "最新组合报告 JSON",
    "rebalance_markdown": "调仓报告 Markdown",
    "rebalance_json": "调仓报告 JSON",
    "rebalance_latest_markdown": "最新调仓报告 Markdown",
    "rebalance_latest_json": "最新调仓报告 JSON",
    "backtest_markdown": "回测报告 Markdown",
    "backtest_json": "回测报告 JSON",
    "backtest_latest_markdown": "最新回测报告 Markdown",
    "backtest_latest_json": "最新回测报告 JSON",
    "grid_markdown": "参数搜索报告 Markdown",
    "grid_json": "参数搜索报告 JSON",
    "grid_latest_markdown": "最新参数搜索报告 Markdown",
    "grid_latest_json": "最新参数搜索报告 JSON",
    "daily_json": "每日综合报告 JSON",
    "daily_md": "每日综合报告 Markdown",
    "archive_markdown": "按日期归档报告 Markdown",
    "archive_json": "按日期归档报告 JSON",
    "latest_markdown": "最新报告 Markdown",
    "latest_json": "最新报告 JSON",
    "latest_md": "最新报告 Markdown",
    "manifest": "报告清单 JSON",
    "compare_json": "策略对比 JSON",
    "consensus_json": "共振股票 JSON",
    "raw_daily": "原始日线",
    "adjustment_factors": "复权因子",
    "adj_daily": "前复权日线",
    "hfq_daily": "后复权日线",
    "factors": "因子数据",
}

VALUE_LABELS: dict[str, str] = {
    "success": "成功",
    "failed": "失败",
    "skipped": "已跳过",
    "running": "运行中",
    "yes": "是",
    "no": "否",
    "true": "是",
    "false": "否",
    "equal": "等权",
    "consensus": "策略共振",
    "signal": "信号",
    "portfolio": "组合",
    "rebalance": "调仓",
    "backtest": "回测",
    "grid_search": "参数搜索",
    "daily": "每日综合",
    "relative-strength": "相对强度",
    "trend-strength": "趋势强度",
    "volume-breakout": "放量突破",
    "low-vol-breakout": "低波突破",
    "multi-factor": "多因子",
    "strong_trend": "强趋势",
    "breakout_watch": "突破观察",
    "buy": "买入",
    "sell": "卖出",
    "increase": "增持",
    "reduce": "减持",
    "hold": "继续持有",
    "rebalance plan skipped by --skip-rebalance": "调仓计划已跳过：运行时使用了 --skip-rebalance",
    "portfolio skipped because strategies were skipped": "策略已跳过，因此组合构建也已跳过",
    "latest": "最新",
    "high_volatility": "高波动",
    "low_liquidity": "低流动性",
}

TAG_GLOSSARY: dict[str, tuple[str, str]] = {
    "near_20d_high": ("接近20日高点", "避免追高，等待回踩或突破确认"),
    "mild_volatility": ("波动偏高", "控制仓位"),
    "ret_5_strong": ("近5日涨幅较强", "注意短线过热"),
    "rsi_high": ("RSI偏高", "谨慎追涨"),
    "breakout_watch": ("突破观察", "关注突破确认"),
    "strong_trend": ("强趋势", "可优先观察"),
    "volume_breakout": ("放量突破", "关注量能持续性"),
    "ma_bullish": ("均线多头", "趋势结构较好"),
    "relative_strength": ("相对强势", "表现强于市场或样本池"),
    "trend_strong": ("趋势较强", "趋势延续性较好"),
    "low_volatility": ("低波动", "波动收敛，关注方向选择"),
    "active_amount": ("成交额活跃", "流动性较好"),
    "volume_expansion": ("量能放大", "关注量能是否持续"),
    "low_liquidity": ("流动性不足", "谨慎参与"),
    "high_volatility": ("高波动", "降低仓位或过滤"),
}

TYPE_LABELS = {key: value[0] for key, value in TAG_GLOSSARY.items()} | VALUE_LABELS

REPORT_TITLES = {
    "信号报告": "TDX 股票信号报告",
    "组合报告": "TDX 股票组合报告",
    "调仓报告": "TDX 股票调仓报告",
    "回测报告": "TDX 股票回测报告",
    "参数搜索报告": "TDX 股票参数搜索报告",
    "每日综合报告": "TDX 股票每日综合报告",
    "运行报告": "TDX 股票运行报告",
}

SPECIAL_FIELD_LABELS = {
    "summary.market_exposure.sh": "沪市暴露",
    "summary.market_exposure.sz": "深市暴露",
    "summary.market_exposure.bj": "北交所暴露",
    "summary.risk_tag_distribution.near_20d_high": "接近20日高点股票数",
    "summary.risk_tag_distribution.ret_5_strong": "近5日涨幅较强股票数",
    "summary.risk_tag_distribution.mild_volatility": "波动偏高股票数",
    "summary.risk_tag_distribution.rsi_high": "RSI偏高股票数",
    "market_exposure.sh": "沪市暴露",
    "market_exposure.sz": "深市暴露",
    "market_exposure.bj": "北交所暴露",
    "risk_tag_distribution.near_20d_high": "接近20日高点股票数",
    "risk_tag_distribution.ret_5_strong": "近5日涨幅较强股票数",
    "risk_tag_distribution.mild_volatility": "波动偏高股票数",
    "risk_tag_distribution.rsi_high": "RSI偏高股票数",
}


def render_run_result_markdown(result: Any, *, app_config: AppConfig | None = None) -> str:
    payload = _payload_from_result(result)
    stock_names = _load_stock_names(app_config, payload)
    task_type = str(payload.get("task_type") or "run")
    if task_type == "signal":
        return _render_signal(payload, stock_names)
    if task_type == "portfolio":
        return _render_portfolio(payload, stock_names)
    if task_type == "rebalance":
        return _render_rebalance(payload, stock_names)
    if task_type == "backtest":
        return _render_backtest(payload, stock_names)
    if task_type == "grid_search":
        return _render_grid(payload)
    if task_type == "daily":
        return _render_daily_wrapper(payload, stock_names)
    return _render_generic(payload, stock_names)


def save_run_result_markdown(path: Path, result: Any, *, app_config: AppConfig | None = None) -> Path:
    return write_text_atomic(path, render_run_result_markdown(result, app_config=app_config))


def _render_signal(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    summary = _as_dict(payload.get("summary"))
    compare = _as_dict(summary.get("compare"))
    consensus = _as_dict(summary.get("consensus"))
    strategies = _as_list(compare.get("strategies") or compare.get("rows"))
    overlaps = _as_list(compare.get("overlaps"))
    rows = _as_list(consensus.get("rows"))
    lines = _title(payload, "信号报告")
    lines.extend(_current_strategy_section(payload, "signal"))
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("任务类型", payload.get("task_type")),
        ("数据日期", compare.get("as_of") or consensus.get("as_of")),
        ("最小命中数", consensus.get("min_hit")),
        ("策略数量", len(strategies)),
        ("共振股票数", len(rows)),
        ("策略重叠股票数", sum(int(item.get("overlap_count") or 0) for item in overlaps if isinstance(item, dict))),
    ]))
    lines.extend(_strategy_compare(strategies, stock_names))
    lines.extend(_overlap_section(overlaps, stock_names))
    lines.extend(_consensus_section(rows, stock_names))
    lines.extend(_consensus_details(rows, stock_names))
    lines.extend(_unique_stocks(compare.get("unique_stocks"), stock_names))
    lines.extend(_label_glossary(payload))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_portfolio(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    summary = _as_dict(payload.get("summary"))
    holdings = _as_list(summary.get("holdings"))
    lines = _title(payload, "组合报告")
    lines.extend(_current_strategy_section(payload, "portfolio"))
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("任务类型", payload.get("task_type")),
        ("组合来源", summary.get("source")),
        ("数据日期", summary.get("as_of")),
        ("生成时间", summary.get("generated_at")),
        ("数据批次", summary.get("data_run_id")),
        ("持仓数量", len(holdings)),
    ]))
    lines.extend(_dict_section("运行参数", summary.get("params")))
    lines.extend(_dict_section("组合摘要", summary.get("summary")))
    lines.extend(_risk_highlights(_as_dict(summary.get("risk_summary"))))
    lines.extend(_exposure_summary(_as_dict(summary.get("risk_summary"))))
    lines.extend(_holdings_section("目标持仓", holdings, stock_names))
    lines.extend(_holding_details(holdings, stock_names))
    lines.extend(_label_glossary(payload))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_rebalance(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    summary = _as_dict(payload.get("summary"))
    changes = _as_list(summary.get("weight_changes") or summary.get("changes"))
    target = _as_list(summary.get("target_holdings"))
    lines = _title(payload, "调仓报告")
    lines.extend(_current_strategy_section(payload, "rebalance"))
    if summary.get("summary") == "skipped" or summary.get("status") == "skipped":
        lines.extend([
            "## 调仓摘要", "",
            "本次调仓计划已跳过。若需要生成调仓计划，请确认运行配置中启用 rebalance，并提供当前持仓文件。", "",
        ])
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("任务类型", payload.get("task_type")),
        ("数据日期", summary.get("as_of")),
        ("换手率", _pct(summary.get("turnover"))),
        ("当前持仓数", len(_as_list(summary.get("current_holdings")))),
        ("目标持仓数", len(target)),
        ("买入数量", len(_as_list(summary.get("buy")))),
        ("卖出数量", len(_as_list(summary.get("sell")))),
        ("增持数量", len(_as_list(summary.get("increase")))),
        ("减持数量", len(_as_list(summary.get("reduce")))),
        ("继续持有数量", len(_as_list(summary.get("hold")))),
    ]))
    lines.extend(_rebalance_actions(changes, stock_names))
    lines.extend(_holdings_section("目标持仓", target, stock_names))
    lines.extend(_label_glossary(payload))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_backtest(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    summary = _as_dict(payload.get("summary"))
    lines = _title(payload, "回测报告")
    lines.extend(_current_strategy_section(payload, "backtest"))
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("策略名称", summary.get("strategy_name")),
        ("开始日期", summary.get("start_date")),
        ("结束日期", summary.get("end_date")),
        ("交易数量", summary.get("trade_count")),
        ("周期数量", summary.get("period_count")),
        ("空仓周期数量", summary.get("empty_period_count")),
    ]))
    lines.extend(_kv_section("收益表现", [
        ("总收益", _pct(summary.get("total_return"))),
        ("年化收益", _pct(summary.get("annual_return"))),
        ("最大回撤", _pct(summary.get("max_drawdown"))),
        ("胜率", _pct(summary.get("win_rate"))),
        ("平均周期收益", _pct(summary.get("avg_period_return"))),
        ("换手率", _pct(summary.get("turnover"))),
    ]))
    lines.extend(_dict_section("运行参数", summary.get("params")))
    lines.extend(_backtest_periods(_as_list(summary.get("periods")), stock_names))
    lines.extend(_backtest_trades(_as_list(summary.get("trades")), stock_names))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_grid(payload: dict[str, Any]) -> str:
    summary = _as_dict(payload.get("summary"))
    rows = _as_list(summary.get("rows"))
    best = _as_dict(rows[0]) if rows and isinstance(rows[0], dict) else {}
    lines = _title(payload, "参数搜索报告")
    lines.extend(_current_strategy_section(payload, "grid_search"))
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("策略名称", summary.get("strategy_name")),
        ("参数组合数量", len(rows)),
    ]))
    if best:
        lines.extend(_kv_section("最优参数", [
            ("最低分", best.get("min_score")),
            ("持仓数量", best.get("top")),
            ("持有天数", best.get("hold_days")),
            ("研究分", best.get("research_score")),
            ("年化收益", _pct(best.get("annual_return"))),
            ("最大回撤", _pct(best.get("max_drawdown"))),
            ("胜率", _pct(best.get("win_rate"))),
        ]))
    lines.extend(_grid_rows(rows))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_daily_wrapper(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    summary = _as_dict(payload.get("summary"))
    daily = _as_dict(summary.get("daily"))
    lines = _title(payload, "每日综合报告")
    lines.extend(_current_strategy_section(payload, "daily"))
    lines.extend(_kv_section("运行摘要", [(key, value) for key, value in daily.items()]))
    lines.extend(_footer(payload))
    return _join(lines)


def _render_generic(payload: dict[str, Any], stock_names: dict[tuple[str, str], str]) -> str:
    lines = _title(payload, "运行报告")
    lines.extend(_current_strategy_section(payload, str(payload.get("task_type") or "run")))
    lines.extend(_kv_section("报告概览", [
        ("报告名称", payload.get("name")),
        ("运行状态", payload.get("status")),
        ("任务类型", payload.get("task_type")),
    ]))
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key, value in summary.items():
            lines.extend(_named_value_section(_label(key), value, stock_names))
    lines.extend(_footer(payload))
    return _join(lines)


def _current_strategy_section(payload: dict[str, Any], task_type: str) -> list[str]:
    summary = _as_dict(payload.get("summary"))
    command_task = "grid" if task_type == "grid_search" else task_type
    command_row: tuple[object, object] = ("运行命令", f"tdx-stocks run {command_task}")
    rows: list[tuple[object, object]] = []
    if task_type == "signal":
        compare = _as_dict(summary.get("compare"))
        consensus = _as_dict(summary.get("consensus"))
        strategies = _as_list(compare.get("strategies") or compare.get("rows"))
        strategy_names = [row.get("strategy_name") for row in strategies if isinstance(row, dict)]
        rows = [
            command_row,
            ("策略", _format_tokens(strategy_names)),
            ("共振规则", f"至少 {_int(consensus.get('min_hit'))} 个策略同时命中" if consensus.get("min_hit") is not None else None),
            ("数据日期", compare.get("as_of") or consensus.get("as_of")),
            ("技术面细节", _strategy_technical_text(strategy_names)),
            ("风险检查", "重点观察接近20日高点、近5日涨幅较强、RSI偏高、波动偏高等短线追高和波动风险"),
        ]
    elif task_type == "portfolio":
        params = _as_dict(summary.get("params"))
        rows = [
            command_row,
            ("组合来源", params.get("source") or summary.get("source")),
            ("最多持仓数", params.get("top")),
            ("权重方式", params.get("weighting")),
            ("单票权重上限", params.get("max_weight")),
            ("剔除风险标签", _format_tokens(params.get("exclude_risk_tags"))),
            ("技术面细节", "组合优先纳入多策略共振、趋势结构健康、成交额活跃、相对强势或放量突破的股票"),
            ("风险检查", "若组合内接近20日高点、近5日涨幅较强或RSI偏高的股票较多，报告会提示追高风险"),
        ]
    elif task_type == "rebalance":
        rows = [
            command_row,
            ("调仓目标", "比较当前持仓与目标组合，生成买入、卖出、增持、减持和继续持有计划"),
            ("数据日期", summary.get("as_of")),
            ("换手率", _pct(summary.get("turnover"))),
            ("技术面细节", "调仓以目标组合的趋势、动量、成交活跃度和风险标签为依据，同时控制换手和单票偏离"),
        ]
    elif task_type == "backtest":
        params = _as_dict(summary.get("params"))
        strategy_name = summary.get("strategy_name")
        rows = [
            command_row,
            ("策略", strategy_name),
            ("回测区间", _range_text(summary.get("start_date"), summary.get("end_date"))),
            ("持仓数量", params.get("top")),
            ("持有天数", params.get("hold_days")),
            ("技术面细节", _strategy_technical_text([strategy_name])),
            ("验证重点", "通过总收益、年化收益、最大回撤、胜率、换手率和空仓周期判断策略稳定性"),
        ]
    elif task_type == "grid_search":
        strategy_name = summary.get("strategy_name")
        rows = [
            command_row,
            ("策略", strategy_name),
            ("搜索目标", "比较多组参数回测结果，寻找收益、回撤和稳定性更均衡的参数区间"),
            ("参数组合数量", len(_as_list(summary.get("rows")))),
            ("技术面细节", _strategy_technical_text([strategy_name])),
            ("参数关注", "重点比较最低分、持仓数量、持有天数对收益、回撤、胜率和研究分的影响"),
        ]
    elif task_type == "daily":
        daily = _as_dict(summary.get("daily"))
        rows = [
            command_row,
            ("运行说明", "每日综合报告汇总策略信号、共振股票、目标组合、风险摘要与调仓状态"),
            ("技术面细节", "先筛选趋势结构健康、动量较强、成交额活跃的股票，再按多策略共振筛选，并检查接近20日高点、近5日涨幅较强、RSI偏高、波动偏高等风险"),
            *daily.items(),
        ]
    else:
        rows = [
            command_row,
            ("运行说明", "本报告由 tdx-stocks run 命令生成，用于展示本次任务的核心结果和输出文件"),
            ("技术面细节", "报告会结合策略参数、候选类型、风险标签和输出结果展示技术面筛选逻辑"),
        ]
    return _kv_section("当前命令与策略技术面", rows)

def _strategy_technical_text(strategies: object) -> str:
    values = strategies if isinstance(strategies, (list, tuple, set)) else [strategies]
    normalized = {str(item or "").strip() for item in values if item not in (None, "")}
    details: list[str] = []
    if {"relative-strength", "相对强度"} & normalized:
        details.append("相对强度关注20日动量较强、60日趋势不弱、表现强于样本池的股票")
    if {"trend-strength", "趋势强度"} & normalized:
        details.append("趋势强度关注均线多头、均线结构健康、趋势向上且成交额活跃的股票")
    if {"volume-breakout", "放量突破"} & normalized:
        details.append("放量突破关注量能放大、接近突破位且价格趋势未被破坏的股票")
    if {"low-vol-breakout", "低波突破"} & normalized:
        details.append("低波突破关注低波收敛后接近突破位、趋势仍保持健康的股票")
    if {"multi-factor", "多因子"} & normalized:
        details.append("多因子综合动量、趋势、成交活跃度和风险标签进行筛选")
    if not details:
        details.append("策略主要从趋势结构、动量强弱、成交活跃度、突破状态和风险标签等技术面维度进行筛选")
    return "；".join(details)


def _range_text(start: object, end: object) -> str:
    if start in (None, "") and end in (None, ""):
        return "无"
    return f"{_value(start)} 至 {_value(end)}"


def _strategy_compare(strategies: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for row in strategies[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        stocks = _as_list(row.get("stocks"))[:10]
        rows.append((
            _value(row.get("strategy_name")),
            _int(row.get("candidate_count")),
            _num(row.get("avg_score")),
            _num(row.get("max_score")),
            _int(row.get("high_score_count")),
            _int(row.get("risk_flag_count")),
            _format_stock_list(stocks, stock_names),
        ))
    return _table_section("策略对比", ("策略", "候选数", "平均分", "最高分", "高分数", "风险数", "前十股票"), rows)


def _overlap_section(overlaps: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for row in overlaps[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        rows.append((
            _value(row.get("left_strategy")),
            _value(row.get("right_strategy")),
            _int(row.get("overlap_count")),
            _format_stock_list(_as_list(row.get("stocks")), stock_names),
        ))
    return _table_section("策略重叠", ("策略A", "策略B", "重叠数量", "股票"), rows)


def _consensus_section(rows_in: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for idx, row in enumerate(rows_in[:MAX_TABLE_ROWS], start=1):
        if not isinstance(row, dict):
            continue
        rows.append((
            idx,
            stock_display(row, stock_names),
            _int(row.get("hit_count")),
            _num(row.get("avg_score")),
            _format_tokens(row.get("candidate_types")),
            _format_tokens(row.get("risk_flags")),
            _action_hint(row.get("risk_flags")),
        ))
    return _table_section("共振股票", ("排名", "股票", "命中数", "平均分", "类型", "风险提示", "操作提示"), rows)


def _consensus_details(rows_in: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not rows_in:
        return []
    lines = ["## 共振详情", ""]
    for idx, row in enumerate(rows_in[:MAX_LIST_ITEMS], start=1):
        if not isinstance(row, dict):
            continue
        lines.extend([
            f"### {idx}. {stock_display(row, stock_names)}", "",
            f"- 股票代码：{stock_code(row)}",
            f"- 命中策略：{_format_tokens(row.get('strategies'))}",
            f"- 候选类型：{_format_tokens(row.get('candidate_types'))}",
            f"- 风险提示：{_format_tokens(row.get('risk_flags'))}",
            "- 入选理由：",
        ])
        reasons = _as_list(row.get("reasons") or row.get("reason"))
        if reasons:
            lines.extend(f"  - {_value(reason)}" for reason in reasons)
        else:
            lines.append("  - 无")
        lines.append("")
    return lines


def _unique_stocks(data: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    lines = ["## 策略独有股票", ""]
    for strategy, values in data.items():
        stocks = _as_list(values)
        shown = stocks[:MAX_LIST_ITEMS]
        suffix = f"（仅显示前 {MAX_LIST_ITEMS} 只，共 {len(stocks)} 只）" if len(stocks) > MAX_LIST_ITEMS else f"（共 {len(stocks)} 只）"
        lines.extend([f"### {_value(strategy)} {suffix}", "", _format_stock_list(shown, stock_names), ""])
    return lines


def _holdings_section(title: str, holdings: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for idx, row in enumerate(holdings[:MAX_TABLE_ROWS], start=1):
        if not isinstance(row, dict):
            continue
        rows.append((
            idx,
            stock_display(row, stock_names),
            _pct(row.get("weight")),
            _num(row.get("score")),
            _format_tokens(row.get("candidate_type")),
            _format_tokens(row.get("risk_flags")),
        ))
    return _table_section(title, ("排名", "股票", "权重", "分数", "候选类型", "风险提示"), rows)


def _holding_details(holdings: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not holdings:
        return []
    lines = ["## 持仓详情", ""]
    for idx, row in enumerate(holdings[:MAX_LIST_ITEMS], start=1):
        if not isinstance(row, dict):
            continue
        lines.extend([
            f"### {idx}. {stock_display(row, stock_names)}", "",
            f"- 股票代码：{stock_code(row)}",
            f"- 权重：{_pct(row.get('weight'))}",
            f"- 分数：{_num(row.get('score'))}",
            f"- 来源策略：{_format_tokens(row.get('source_strategies') or row.get('source_strategy'))}",
            f"- 候选类型：{_format_tokens(row.get('candidate_type'))}",
            f"- 风险提示：{_format_tokens(row.get('risk_flags'))}",
            f"- 标签：{_format_tokens(row.get('tags'), max_items=8)}",
            f"- 入选理由：{_value(row.get('reason'))}",
            "",
        ])
    return lines


def _risk_highlights(risk: dict[str, Any]) -> list[str]:
    if not risk:
        return []
    data = _as_dict(risk.get("summary"))
    rows = [
        ("风险检查", "通过" if risk.get("passed") is True else "未通过" if risk.get("passed") is False else "无"),
        ("警告", _format_tokens(risk.get("warnings"))),
        ("违规项", _format_tokens(risk.get("violations"))),
    ]
    if data:
        rows.extend([
            ("持仓数量", _int(data.get("holding_count"))),
            ("最大单票权重", _pct(data.get("max_single_weight"))),
            ("高风险股票数", _int(data.get("high_risk_stock_count"))),
            ("低流动性股票数", _int(data.get("low_liquidity_stock_count"))),
            ("权重合计", _num(data.get("weight_sum"))),
        ])
        tag_dist = _as_dict(data.get("risk_tag_distribution"))
        for key, value in tag_dist.items():
            rows.append((f"风险标签：{_tag_label(key)}", _int(value)))
    return _kv_section("风险重点", rows)


def _exposure_summary(risk: dict[str, Any]) -> list[str]:
    data = _as_dict(risk.get("summary"))
    exposure = _as_dict(data.get("market_exposure"))
    if not exposure:
        return []
    rows = [(_market_label(key), _pct(value)) for key, value in exposure.items()]
    return _table_section("市场暴露", ("市场", "权重"), rows)


def _rebalance_actions(changes: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for row in changes[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        rows.append((
            _value(row.get("action")),
            stock_display(row, stock_names),
            _pct(row.get("current_weight")),
            _pct(row.get("target_weight")),
            _pct(row.get("delta_weight")),
            _value(row.get("reason")),
        ))
    return _table_section("调仓动作", ("操作", "股票", "当前权重", "目标权重", "权重差", "说明"), rows)


def _backtest_periods(periods: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for row in periods[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        rows.append((
            row.get("entry_date") or row.get("start_date"),
            row.get("exit_date") or row.get("end_date"),
            _pct(row.get("period_return") or row.get("return")),
            _format_stock_list(_as_list(row.get("symbols") or row.get("holdings")), stock_names),
        ))
    return _table_section("周期收益", ("开始", "结束", "收益", "持仓"), rows)


def _backtest_trades(trades: list[Any], stock_names: dict[tuple[str, str], str]) -> list[str]:
    rows = []
    for row in trades[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        rows.append((
            row.get("date") or row.get("buy_date") or row.get("signal_date"),
            _value(row.get("action") or row.get("side")),
            stock_display(row, stock_names),
            _num(row.get("price") or row.get("buy_price")),
            _pct(row.get("net_return") or row.get("gross_return")),
        ))
    return _table_section("交易摘要", ("日期", "操作", "股票", "价格", "收益"), rows)


def _grid_rows(rows_in: list[Any]) -> list[str]:
    rows = []
    for row in rows_in[:MAX_TABLE_ROWS]:
        if not isinstance(row, dict):
            continue
        rows.append((
            row.get("min_score"), row.get("top"), row.get("hold_days"),
            _pct(row.get("annual_return")), _pct(row.get("max_drawdown")),
            _pct(row.get("win_rate")), _num(row.get("research_score"), digits=4),
        ))
    return _table_section("参数结果", ("最低分", "持仓数", "持有天数", "年化收益", "最大回撤", "胜率", "研究分"), rows)


def _dict_section(title: str, value: object) -> list[str]:
    data = _flatten_dict(_as_dict(value))
    if not data:
        return []
    return _kv_section(title, [(_label(key), val) for key, val in data.items()])


def _named_value_section(title: str, value: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if isinstance(value, dict):
        return _dict_section(title, value)
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        normalized = _as_list(value)
        keys: list[str] = []
        for item in normalized:
            for key in item.keys():
                if key not in keys:
                    keys.append(key)
        rows = [tuple(_value(item.get(key)) for key in keys) for item in normalized[:MAX_TABLE_ROWS] if isinstance(item, dict)]
        return _table_section(title, tuple(_label(key) for key in keys), rows)
    if value not in (None, [], {}):
        return [f"## {title}", "", _value(value), ""]
    return []


def _label_glossary(payload: object) -> list[str]:
    seen = sorted(_collect_tokens(payload) & set(TAG_GLOSSARY.keys()))
    if not seen:
        return []
    rows = [(f"`{key}`", TAG_GLOSSARY[key][0], TAG_GLOSSARY[key][1]) for key in seen]
    return _table_section("标签说明", ("标签", "中文含义", "操作建议"), rows)


def _collect_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"tags", "risk_flags", "candidate_types", "candidate_type"}:
                if isinstance(item, list):
                    tokens.update(str(x) for x in item)
                elif item:
                    tokens.add(str(item))
            tokens.update(_collect_tokens(item))
    elif isinstance(value, list):
        for item in value:
            tokens.update(_collect_tokens(item))
    return tokens


def _footer(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.extend(_outputs_section(payload.get("outputs")))
    lines.extend(_list_section("警告", payload.get("warnings")))
    lines.extend(_list_section("错误", payload.get("errors")))
    lines.extend(["## 原始 JSON", "", "调试 JSON 保存在 `Database/report_payloads/`，通常无需日常查看。", ""])
    return lines


def _outputs_section(outputs: object) -> list[str]:
    data = _as_dict(outputs)
    rows = [("本报告", value) for value in data.values() if str(value).endswith(".md")]
    lines = _table_section("输出文件", ("名称", "路径"), rows) if rows else ["## 输出文件", "", "暂无数据", ""]
    if any(str(value).endswith(".json") for value in data.values()):
        lines.extend(["调试 JSON 保存在 `Database/report_payloads/`，通常无需日常查看。", ""])
    return lines


def _list_section(title: str, values: object) -> list[str]:
    if not values:
        return [f"## {title}", "", "暂无数据", ""]
    if isinstance(values, list):
        rows = [(idx, _value(item)) for idx, item in enumerate(values, start=1)]
        return _table_section(title, ("序号", "内容"), rows)
    return [f"## {title}", "", _value(values), ""]


def _title(payload: dict[str, Any], title: str) -> list[str]:
    return [f"# {REPORT_TITLES.get(title, title)}", ""]


def _kv_section(title: str, rows: list[tuple[object, object]]) -> list[str]:
    filtered = [(key, value) for key, value in rows if value not in (None, [], {})]
    if not filtered:
        return []
    return _table_section(title, ("项目", "内容"), filtered)


def _table_section(title: str, headers: tuple[object, ...], rows: list[tuple[object, ...]]) -> list[str]:
    if not rows:
        return [f"## {title}", "", "暂无数据", ""]
    return [f"## {title}", "", _md_table(headers, rows), ""]


def _md_table(headers: tuple[object, ...], rows: list[tuple[object, ...]]) -> str:
    header = "| " + " | ".join(_escape(str(item)) for item in headers) + " |"
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape(_value(item)) for item in row) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten_dict(value, full_key))
        else:
            out[full_key] = value
    return out


def _format_stock_list(values: list[Any], stock_names: dict[tuple[str, str], str]) -> str:
    if not values:
        return "无"
    return "，".join(stock_display(item, stock_names) for item in values)


def _format_tokens(values: object, max_items: int = 5) -> str:
    if values is None or values == []:
        return "无"
    if isinstance(values, str):
        return _tag_label(values)
    if not isinstance(values, (list, tuple, set)):
        return _value(values)
    labels = [_tag_label(str(item)) for item in values if item not in (None, "")]
    if not labels:
        return "无"
    if len(labels) <= max_items:
        return "，".join(labels)
    return "，".join(labels[:max_items]) + f" 等{len(labels)}项"


def _tag_label(value: object) -> str:
    text = str(value)
    return TYPE_LABELS.get(text, text)


def _action_hint(flags: object) -> str:
    values = set(str(item) for item in _as_list(flags))
    if "rsi_high" in values or "ret_5_strong" in values:
        return "短线偏热，谨慎追涨"
    if "near_20d_high" in values:
        return "避免追高，等待回踩"
    if "mild_volatility" in values or "high_volatility" in values:
        return "控制仓位"
    if not values:
        return "优先观察"
    return "结合盘面确认"


def _label(key: object) -> str:
    text = str(key)
    if text in SPECIAL_FIELD_LABELS:
        return SPECIAL_FIELD_LABELS[text]
    if "." in text:
        parts = text.split(".")
        return " - ".join(_label(part) for part in parts)
    return FIELD_LABELS.get(text, TYPE_LABELS.get(text, text))


def _value(value: object) -> str:
    if value is None or value == "":
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple, set)):
        items = [_value(item) for item in value if item not in (None, "")]
        return "，".join(items) if items else "无"
    if isinstance(value, dict):
        flat = _flatten_dict(value)
        return "<br>".join(f"{_label(key)}：{_value(item)}" for key, item in flat.items()) if flat else "无"
    if isinstance(value, float):
        return _num(value)
    text = str(value)
    return VALUE_LABELS.get(text, text)


def _num(value: object, *, digits: int = 2) -> str:
    if value is None:
        return "无"
    try:
        return f"{float(value):,.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return _value(value)


def _int(value: object) -> str:
    if value is None:
        return "无"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _value(value)


def _pct(value: object) -> str:
    if value is None:
        return "无"
    try:
        number = float(value) * 100
        return f"{number:,.2f}".rstrip("0").rstrip(".") + "%"
    except (TypeError, ValueError):
        return _value(value)


def _market_label(value: object) -> str:
    text = str(value).lower()
    return {"sh": "沪市", "sz": "深市", "bj": "北交所"}.get(text, str(value))


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, set):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()] if "," in value else [value]
    return []


def _payload_from_result(result: Any) -> dict[str, Any]:
    if hasattr(result, "to_dict"):
        return dict(result.to_dict())
    return {
        "task_type": getattr(result, "task_type", None),
        "name": getattr(result, "name", None),
        "status": getattr(result, "status", None),
        "summary": getattr(result, "summary", {}),
        "outputs": getattr(result, "outputs", {}),
        "warnings": getattr(result, "warnings", []),
        "errors": getattr(result, "errors", []),
    }


def _load_stock_names(app_config: AppConfig | None, payload: dict[str, Any]) -> dict[tuple[str, str], str]:
    if app_config is None:
        return {}
    export_dir = getattr(getattr(app_config, "paths", None), "tdx_export", None)
    return build_stock_name_map(export_dir, collect_stock_keys(payload))


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")


def _join(lines: list[str]) -> str:
    return "\n".join(lines).rstrip() + "\n"
