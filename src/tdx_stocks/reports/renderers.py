from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, Sequence

from .stock_names import stock_code, stock_display

LABELS = {
    "success": "成功",
    "failed": "失败",
    "skipped": "已跳过",
    "yes": "是",
    "no": "否",
    "equal": "等权",
    "liquidity-risk": "流动性/风险加权",
    "liquidity_risk": "流动性/风险加权",
    "consensus": "策略共振",
    "strong_trend": "强趋势",
    "breakout_watch": "突破观察",
    "trend-strength": "趋势强度",
    "relative-strength": "相对强度",
    "volume-breakout": "放量突破",
    "low-vol-breakout": "低波突破",
    "multi-factor": "多因子",
    "latest": "最新",
    "raw_daily": "原始日线",
    "adjustment_factors": "复权因子",
    "adj_daily": "前复权日线",
    "hfq_daily": "后复权日线",
    "factors": "因子数据",
    "high_volatility": "高波动",
    "low_liquidity": "低流动性",
}

FIELD_LABELS = {
    "as_of": "数据日期",
    "status": "运行状态",
    "data_run_id": "数据批次",
    "generated_at": "生成时间",
    "step_count": "步骤数量",
    "warning_count": "警告数量",
    "error_count": "错误数量",
    "strategy_name": "策略名称",
    "display_name": "显示名称",
    "description": "说明",
    "group": "分组",
    "style": "风格",
    "required_fields": "必需字段",
    "optional_fields": "可选字段",
    "candidate_types": "候选类型",
    "risk_tags": "风险标签",
    "aliases": "别名",
    "supported_research_capabilities": "研究能力",
    "source": "来源",
    "strategy": "策略",
    "candidate_count": "候选数量",
    "selected_count": "入选数量",
    "excluded_count": "剔除数量",
    "holding_count": "持仓数量",
    "weighting": "权重方式",
    "max_weight": "单票权重上限",
    "min_weight": "单票权重下限",
    "market_exposure": "市场暴露",
    "risk_tag_distribution": "风险标签分布",
    "high_risk_stock_count": "高风险股票数",
    "low_liquidity_stock_count": "低流动性股票数",
    "weight_sum": "权重合计",
    "passed": "是否通过",
    "warnings": "警告",
    "violations": "违规项",
    "summary": "摘要",
    "top": "最多持仓数",
    "min_score": "最低分",
    "limit": "数量上限",
    "min_hit": "最小命中数",
    "rows": "行数",
    "turnover": "换手率",
    "strategies": "策略",
    "max_risk_score": "最大风险分",
    "market": "市场",
    "max_single_weight": "最大单票权重",
    "avg_risk_score": "平均风险分",
    "source_candidate_count": "来源候选数量",
    "filtered_candidate_count": "过滤后候选数量",
    "row_count": "行数",
    "compare_json": "策略对比 JSON",
    "consensus_json": "共振股票 JSON",
    "archive_markdown": "按日期归档报告 Markdown",
    "archive_json": "按日期归档报告 JSON",
    "latest_markdown": "最新报告 Markdown",
    "latest_json": "最新日报 JSON",
    "latest_md": "最新日报 Markdown",
    "daily_json": "按日期归档日报 JSON",
    "daily_md": "按日期归档日报 Markdown",
    "manifest": "日报清单 JSON",
    "portfolio:portfolio_json": "组合 JSON",
    "latest": "最新策略结果",
    "by_date": "按日期保存的策略结果",
    "by_run_id": "按数据批次保存的策略结果",
    "raw_daily": "原始日线",
    "adjustment_factors": "复权因子",
    "adj_daily": "前复权日线",
    "hfq_daily": "后复权日线",
    "factors": "因子数据",
}

TEXT_LABELS = {
    "rebalance plan skipped by --skip-rebalance": "调仓计划已跳过：运行时使用了 --skip-rebalance",
    "portfolio skipped because strategies were skipped": "策略已跳过，因此组合构建也已跳过",
    "dataset rebuilt": "数据集已重建",
    "compare generated": "策略对比已生成",
    "consensus generated": "共振股票已生成",
    "portfolio built": "组合已生成",
    "portfolio risk checked": "组合风险已检查",
    "daily report generated": "日报已生成",
    "manifest saved": "清单已保存",
    "report skipped": "报告生成已跳过",
    "strategies skipped": "策略运行已跳过",
    "portfolio skipped": "组合构建已跳过",
    "success": "成功",
    "failed": "失败",
    "skipped": "已跳过",
}

TAG_GLOSSARY = {
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

TOKEN_LABELS = {key: value[0] for key, value in TAG_GLOSSARY.items()} | LABELS

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


def fmt_int(value: object) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def fmt_float(value: object, *, digits: int = 2) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    try:
        return f"{float(value):,.{digits}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(value)


def fmt_pct(value: object, *, digits: int = 2) -> str:
    if value is None:
        return "无"
    try:
        number = float(value) * 100
        return f"{number:,.{digits}f}".rstrip("0").rstrip(".") + "%"
    except (TypeError, ValueError):
        return str(value)


def fmt_bool(value: object) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    return "是" if bool(value) else "否"


def fmt_list(value: object) -> str:
    if value is None:
        return "无"
    if isinstance(value, (list, tuple, set)):
        items = [_stringify(item) for item in value if item not in (None, "")]
        return "，".join(items) if items else "无"
    return _stringify(value)


def md_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
    header_row = "| " + " | ".join(_escape_md_cell(str(header)) for header in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(_escape_md_cell(_stringify(cell)) for cell in row) + " |" for row in rows]
    return "\n".join([header_row, separator, *body]) if body else "\n".join([header_row, separator])


def render_daily_markdown(report: Any, *, stock_names: dict[tuple[str, str], str] | None = None) -> str:
    stock_names = stock_names or {}
    payload = _payload(report)
    portfolio_summary = payload.get("portfolio_summary") if isinstance(payload.get("portfolio_summary"), dict) else {}
    holdings = portfolio_summary.get("holdings") if isinstance(portfolio_summary, dict) else []
    risk_summary = portfolio_summary.get("risk_summary") if isinstance(portfolio_summary, dict) else {}
    lines: list[str] = []
    lines.extend(_section_header("TDX 股票每日综合报告"))
    lines.extend(_daily_strategy_overview(payload))
    lines.extend(_daily_highlights(payload))
    lines.extend(_summary_block(payload))
    data_quality = payload.get("data_quality")
    checks = data_quality.get("checks") if isinstance(data_quality, dict) else data_quality
    lines.extend(_with_fallback("数据质量", _render_checks_section("数据质量", checks)))
    lines.extend(_with_fallback("策略摘要", _render_kv_section("策略摘要", payload.get("strategy_summary"))))
    lines.extend(_with_fallback("共振股票", _render_consensus_section(payload.get("consensus_summary"), stock_names)))
    lines.extend(_with_fallback("组合摘要", _render_portfolio_summary(portfolio_summary)))
    lines.extend(_render_market_regime_section(portfolio_summary))
    lines.extend(_render_risk_interception_section(portfolio_summary, stock_names))
    lines.extend(_render_sector_exposure_section(portfolio_summary))
    lines.extend(_render_portfolio_holdings_section(holdings, stock_names, heading="目标持仓"))
    lines.extend(_with_fallback("风险摘要", _render_risk_summary_section(risk_summary)))
    lines.extend(_with_fallback("调仓计划", _render_rebalance_section(payload.get("rebalance_summary"))))
    lines.extend(_with_fallback("输出文件", _render_outputs_section(payload.get("outputs"))))
    lines.extend(_with_fallback("警告", _render_simple_list_section("警告", payload.get("warnings"))))
    lines.extend(_with_fallback("错误", _render_simple_list_section("错误", payload.get("errors"))))
    lines.extend(_label_glossary(payload))
    lines.extend(_render_json_details("原始 JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def render_strategy_markdown(report: dict[str, Any], *, stock_names: dict[tuple[str, str], str] | None = None) -> str:
    stock_names = stock_names or {}
    payload = _payload(report)
    lines: list[str] = []
    lines.extend(_section_header("TDX 股票策略报告"))
    lines.extend(_strategy_technical_overview(payload))
    lines.extend(_render_kv_table("报告概览", [
        ("策略名称", payload.get("strategy_name")),
        ("数据日期", payload.get("as_of")),
        ("生成时间", payload.get("generated_at")),
        ("数据批次", payload.get("data_run_id")),
        ("因子版本", payload.get("factor_version")),
        ("候选数量", payload.get("candidate_count")),
        ("剔除数量", payload.get("excluded_count")),
    ]))
    lines.extend(_render_strategy_identity_section(payload))
    lines.extend(_render_strategy_candidates_section(payload.get("candidates"), stock_names))
    lines.extend(_render_strategy_excluded_section(payload.get("excluded_summary")))
    lines.extend(_render_strategy_risk_section(payload.get("risk_summary")))
    lines.extend(_label_glossary(payload))
    lines.extend(_render_json_details("原始 JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def render_portfolio_markdown(report: dict[str, Any], *, stock_names: dict[tuple[str, str], str] | None = None) -> str:
    stock_names = stock_names or {}
    payload = _payload(report)
    lines: list[str] = []
    lines.extend(_section_header("TDX 股票组合报告"))
    lines.extend(_portfolio_strategy_overview(payload))
    lines.extend(_render_kv_table("报告概览", [
        ("来源", payload.get("source")),
        ("数据日期", payload.get("as_of")),
        ("生成时间", payload.get("generated_at")),
        ("数据批次", payload.get("data_run_id")),
    ]))
    lines.extend(_render_kv_section("组合摘要", payload.get("summary")))
    lines.extend(_render_market_regime_section(payload))
    lines.extend(_render_risk_interception_section(payload, stock_names))
    lines.extend(_render_sector_exposure_section(payload))
    lines.extend(_render_risk_summary_section(payload.get("risk_summary")))
    lines.extend(_render_portfolio_holdings_section(payload.get("holdings"), stock_names, heading="目标持仓"))
    lines.extend(_holding_details(payload.get("holdings"), stock_names))
    lines.extend(_label_glossary(payload))
    lines.extend(_render_json_details("原始 JSON", payload))
    return "\n".join(lines).rstrip() + "\n"


def _section_header(title: str) -> list[str]:
    return [f"# {title}", ""]


def _daily_strategy_overview(payload: dict[str, Any]) -> list[str]:
    strategy = payload.get("strategy_summary") if isinstance(payload.get("strategy_summary"), dict) else {}
    consensus = payload.get("consensus_summary") if isinstance(payload.get("consensus_summary"), dict) else {}
    portfolio = payload.get("portfolio_summary") if isinstance(payload.get("portfolio_summary"), dict) else {}
    portfolio_summary = portfolio.get("summary") if isinstance(portfolio.get("summary"), dict) else {}
    strategies = strategy.get("strategies")
    rows = [
        ("运行命令", "tdx-stocks run daily"),
        ("信号策略", _format_tokens(strategies)),
        ("筛选数量上限", strategy.get("limit")),
        ("最低分", strategy.get("min_score")),
        ("共振规则", f"至少 {fmt_int(consensus.get('min_hit'))} 个策略同时命中" if consensus.get("min_hit") is not None else None),
        ("组合来源", portfolio.get("source") or portfolio_summary.get("source")),
        ("权重方式", portfolio_summary.get("weighting")),
        ("技术面细节", _strategy_technical_text(strategies)),
        ("风险检查", "重点观察接近20日高点、近5日涨幅较强、RSI偏高、波动偏高等短线追高和波动风险"),
    ]
    return _render_kv_table("当前命令与策略技术面", rows)


def _portfolio_strategy_overview(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    params = summary.get("params") if isinstance(summary.get("params"), dict) else {}
    rows = [
        ("运行命令", "tdx-stocks run portfolio"),
        ("组合来源", params.get("source") or payload.get("source")),
        ("最多持仓数", params.get("top")),
        ("权重方式", params.get("weighting")),
        ("单票权重上限", params.get("max_weight")),
        ("剔除风险标签", _format_tokens(params.get("exclude_risk_tags"))),
        ("技术面细节", "优先纳入多策略共振、趋势结构健康、成交额活跃、相对强势或放量突破的股票"),
        ("风险检查", "若组合内接近20日高点、近5日涨幅较强或RSI偏高的股票较多，报告会提示追高风险"),
    ]
    return _render_kv_table("当前命令与策略技术面", rows)



def _strategy_technical_overview(payload: dict[str, Any]) -> list[str]:
    rows = [
        ("运行命令", "tdx-stocks report strategy"),
        ("策略名称", payload.get("strategy_name")),
        ("策略说明", payload.get("description")),
        ("候选类型", _format_tokens(payload.get("candidate_types"))),
        ("风险标签", _format_tokens(payload.get("risk_tags"))),
        ("技术面细节", _strategy_technical_text([payload.get("strategy_name"), *(payload.get("aliases") or [])])),
    ]
    return _render_kv_table("当前命令与策略技术面", rows)


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

def _daily_highlights(payload: dict[str, Any]) -> list[str]:
    portfolio_summary = payload.get("portfolio_summary") if isinstance(payload.get("portfolio_summary"), dict) else {}
    risk_summary = portfolio_summary.get("risk_summary") if isinstance(portfolio_summary, dict) else {}
    risk_data = risk_summary.get("summary") if isinstance(risk_summary, dict) and isinstance(risk_summary.get("summary"), dict) else {}
    warnings = payload.get("warnings") or []
    consensus = payload.get("consensus_summary") if isinstance(payload.get("consensus_summary"), dict) else {}
    rows = [
        ("运行状态", payload.get("status")),
        ("数据日期", payload.get("as_of")),
        ("共振股票数", consensus.get("rows") if not isinstance(consensus.get("rows"), list) else len(consensus.get("rows") or [])),
        ("组合持仓数", len(portfolio_summary.get("holdings") or []) if isinstance(portfolio_summary, dict) else None),
        ("主要警告", warnings[0] if isinstance(warnings, list) and warnings else None),
    ]
    if risk_data:
        rows.extend([
            ("接近20日高点", risk_data.get("risk_tag_distribution", {}).get("near_20d_high") if isinstance(risk_data.get("risk_tag_distribution"), dict) else None),
            ("高风险股票数", risk_data.get("high_risk_stock_count")),
        ])
    return _render_kv_table("今日结论", rows)


def _summary_block(payload: dict[str, Any]) -> list[str]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return _render_kv_table("运行摘要", [
        ("数据日期", payload.get("as_of")),
        ("运行状态", payload.get("status")),
        ("数据批次", payload.get("data_run_id")),
        ("生成时间", payload.get("generated_at")),
        ("步骤数量", summary.get("step_count")),
        ("警告数量", summary.get("warning_count")),
        ("错误数量", summary.get("error_count")),
    ])


def _render_checks_section(title: str, checks: object) -> list[str]:
    rows_in = list(checks or []) if isinstance(checks, list) else []
    table_rows = []
    for row in rows_in:
        if isinstance(row, dict):
            name = row.get("name") or row.get("table") or row.get("step_name") or row.get("check")
            status = row.get("passed") if "passed" in row else row.get("status")
            detail = row.get("detail") or row.get("message") or row.get("summary")
            if status in (None, "", "N/A", "n/a") and detail in (None, "", "N/A", "n/a"):
                status = "未提供质量明细"
                detail = "本次日报未包含该项质量明细"
            table_rows.append((_label(name), _stringify(status), _stringify(detail)))
    if table_rows:
        return [f"## {title}", "", md_table(("名称", "状态", "详情"), table_rows), ""]
    return [f"## {title}", "", "本次日报未包含数据质量明细。", ""]

def _render_kv_section(title: str, data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = [(_label(key), value) for key, value in _flatten_dict(data).items() if key not in {"holdings", "diagnostics", "candidates"}]
    return [f"## {title}", "", md_table(("项目", "内容"), rows), ""] if rows else []


def _render_consensus_section(data: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows_in = data.get("rows")
    if isinstance(rows_in, list) and rows_in:
        rows = []
        for index, row in enumerate(rows_in[:20], start=1):
            if isinstance(row, dict):
                rows.append((
                    index,
                    stock_display(row, stock_names),
                    row.get("hit_count"),
                    fmt_float(row.get("avg_score")),
                    _format_tokens(row.get("risk_flags")),
                    _action_hint(row.get("risk_flags")),
                ))
        return ["## 共振股票", "", md_table(("排名", "股票", "命中数", "平均分", "风险提示", "操作提示"), rows), ""]
    return _render_kv_section("共振股票", data)


def _render_portfolio_summary(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    rows = [
        ("来源", data.get("source")),
        ("数据日期", data.get("as_of")),
        ("数据批次", data.get("data_run_id")),
        ("持仓数量", len(data.get("holdings") or [])),
    ]
    rows.extend((_label(key), value) for key, value in _flatten_dict(summary).items())
    return ["## 组合摘要", "", md_table(("项目", "内容"), rows), ""]


def _render_risk_summary_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = [(_label(key), value) for key, value in _flatten_dict(data).items()]
    return ["## 风险摘要", "", md_table(("项目", "内容"), rows), ""] if rows else []


def _render_rebalance_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    if data.get("summary") == "skipped":
        return ["## 调仓计划", "", "本次调仓计划已跳过。若需要生成调仓计划，请在运行配置中启用 rebalance，并提供当前持仓文件。", ""]
    return _render_kv_section("调仓计划", data)


def _render_outputs_section(data: object) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    rows = [("本报告", value) for value in data.values() if str(value).endswith(".md")]
    if not rows:
        return []
    lines = ["## 输出文件", "", md_table(("名称", "路径"), rows), ""]
    if any(str(value).endswith(".json") for value in data.values()):
        lines.extend(["调试 JSON 保存在 `Database/report_payloads/`，通常无需日常查看。", ""])
    return lines


def _render_simple_list_section(title: str, values: object) -> list[str]:
    if not values:
        return []
    if isinstance(values, list):
        rows = [(index + 1, item) for index, item in enumerate(values)]
        return [f"## {title}", "", md_table(("序号", "内容"), rows), ""]
    return [f"## {title}", "", str(values), ""]


def _render_json_details(title: str, payload: object) -> list[str]:
    return [f"## {title}", "", "调试 JSON 保存在 `Database/report_payloads/`，通常无需日常查看。", ""]


def _with_fallback(title: str, lines: list[str]) -> list[str]:
    return lines if lines else [f"## {title}", "", "暂无数据", ""]


def _render_kv_table(title: str, rows: Sequence[tuple[str, object]]) -> list[str]:
    filtered = [(key, value) for key, value in rows if value not in (None, [], {})]
    return [f"## {title}", "", md_table(("项目", "内容"), filtered), ""] if filtered else []


def _render_portfolio_holdings_section(holdings: object, stock_names: dict[tuple[str, str], str], *, heading: str) -> list[str]:
    if not isinstance(holdings, list) or not holdings:
        return []
    rows = []
    for index, row in enumerate(holdings[:20], start=1):
        if not isinstance(row, dict):
            continue
        rows.append((
            index,
            stock_display(row, stock_names),
            fmt_pct(row.get("weight")),
            fmt_float(row.get("score")),
            _format_tokens(row.get("candidate_type")),
            _format_tokens(row.get("risk_flags")),
            _money(_factor(row, "amount_ma20")),
            fmt_pct(_factor(row, "target_amount_to_adv")),
            fmt_float(_factor(row, "expected_liquidation_days")),
        ))
    return [f"## {heading}", "", md_table(("排名", "股票", "权重", "分数", "候选类型", "风险提示", "20日均成交额", "目标金额/ADV", "预计变现天数"), rows), ""] if rows else []


def _holding_details(holdings: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not isinstance(holdings, list) or not holdings:
        return []
    lines = ["## 持仓详情", ""]
    for index, row in enumerate(holdings[:20], start=1):
        if not isinstance(row, dict):
            continue
        lines.extend([
            f"### {index}. {stock_display(row, stock_names)}", "",
            f"- 股票代码：{stock_code(row)}",
            f"- 权重：{fmt_pct(row.get('weight'))}",
            f"- 分数：{fmt_float(row.get('score'))}",
            f"- 候选类型：{_format_tokens(row.get('candidate_type'))}",
            f"- 风险提示：{_format_tokens(row.get('risk_flags'))}",
            f"- 标签：{_format_tokens(row.get('tags'), max_items=8)}",
            f"- 入选理由：{_stringify(row.get('reason'))}",
            f"- 20日均成交额：{_money(_factor(row, 'amount_ma20'))}",
            f"- 目标金额/ADV：{fmt_pct(_factor(row, 'target_amount_to_adv'))}",
            f"- 预计变现天数：{fmt_float(_factor(row, 'expected_liquidation_days'))}",
            "",
        ])
    return lines



def _render_risk_interception_section(payload: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not isinstance(payload, dict):
        return []
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    rows_in = diagnostics.get("risk_interceptions") if isinstance(diagnostics, dict) else []
    if not isinstance(rows_in, list) or not rows_in:
        if diagnostics.get("risk_filter_applied"):
            return ["## 风控拦截日志", "", "今日无股票触发组合风控拦截。", ""]
        return []
    rows = []
    for row in rows_in[:50]:
        if isinstance(row, dict):
            rows.append((
                stock_display(row, stock_names, include_code=True),
                fmt_float(row.get("score")),
                _format_tokens(row.get("source_strategies") or row.get("source_strategy")),
                _format_tokens(row.get("trigger_tags")),
                _stringify(row.get("reason")),
                "已一票否决",
            ))
    return ["## 风控拦截日志", "", md_table(("股票", "分数", "来源策略", "触发标签", "拦截原因", "处理"), rows), ""] if rows else []


def _render_market_regime_section(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    regime = diagnostics.get("market_regime") if isinstance(diagnostics.get("market_regime"), dict) else {}
    if not regime:
        return []
    return _render_kv_table("市场环境滤网", [
        ("是否启用", regime.get("enabled")),
        ("参考指数", regime.get("index")),
        ("均线窗口", regime.get("ma_window")),
        ("市场状态", regime.get("status")),
        ("系统动作", regime.get("action")),
        ("说明", regime.get("message")),
    ])


def _render_sector_exposure_section(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), dict) else {}
    exposure = diagnostics.get("sector_exposure") if isinstance(diagnostics.get("sector_exposure"), dict) else {}
    if not exposure:
        return []
    rows_in = exposure.get("rows")
    if not isinstance(rows_in, list) or not rows_in:
        return ["## 行业暴露", "", "未找到行业分类数据，无法计算行业暴露。", ""]
    rows = []
    for row in rows_in:
        if isinstance(row, dict):
            rows.append((row.get("sector"), fmt_int(row.get("count")), fmt_pct(row.get("weight")), "行业集中度过高" if row.get("warning") else "正常"))
    return ["## 行业暴露", "", md_table(("行业", "股票数量", "权重占比", "风险提示"), rows), ""]


def _factor(row: dict[str, Any], key: str) -> Any:
    factors = row.get("factor_values") if isinstance(row.get("factor_values"), dict) else {}
    return row.get(key) if row.get(key) is not None else factors.get(key)


def _money(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "无"
    if abs(number) >= 100_000_000:
        return f"{number / 100_000_000:.2f}亿"
    if abs(number) >= 10_000:
        return f"{number / 10_000:.2f}万"
    return fmt_float(number)

def _render_strategy_identity_section(payload: dict[str, Any]) -> list[str]:
    rows = [
        ("显示名称", payload.get("display_name")),
        ("说明", payload.get("description")),
        ("分组", payload.get("group")),
        ("风格", payload.get("style")),
        ("必需字段", fmt_list(payload.get("required_fields"))),
        ("可选字段", fmt_list(payload.get("optional_fields"))),
        ("候选类型", _format_tokens(payload.get("candidate_types"))),
        ("风险标签", _format_tokens(payload.get("risk_tags"))),
        ("别名", fmt_list(payload.get("aliases"))),
        ("研究能力", fmt_list(payload.get("supported_research_capabilities"))),
    ]
    return ["## 策略定义", "", md_table(("项目", "内容"), rows), ""]


def _render_strategy_candidates_section(candidates: object, stock_names: dict[tuple[str, str], str]) -> list[str]:
    if not isinstance(candidates, list) or not candidates:
        return []
    rows = []
    for index, row in enumerate(candidates[:20], start=1):
        if isinstance(row, dict):
            rows.append((index, stock_display(row, stock_names), fmt_float(row.get("score")), _format_tokens(row.get("candidate_type")), _format_tokens(row.get("risk_flags")), _action_hint(row.get("risk_flags"))))
    return ["## 候选股票", "", md_table(("排名", "股票", "分数", "候选类型", "风险提示", "操作提示"), rows), ""] if rows else []


def _render_strategy_excluded_section(excluded_summary: object) -> list[str]:
    if not isinstance(excluded_summary, dict) or not excluded_summary:
        return []
    rows = [("合计", excluded_summary.get("total"))]
    reasons = excluded_summary.get("reasons")
    if isinstance(reasons, dict):
        rows.extend((str(key), value) for key, value in reasons.items())
    return ["## 剔除摘要", "", md_table(("项目", "数量"), rows), ""]


def _render_strategy_risk_section(risk_summary: object) -> list[str]:
    if not isinstance(risk_summary, dict) or not risk_summary:
        return []
    rows = [(_format_tokens(key), value) for key, value in risk_summary.items()]
    return ["## 风险摘要", "", md_table(("风险标签", "数量"), rows), ""]


def _label_glossary(payload: object) -> list[str]:
    seen = sorted(_collect_tokens(payload) & set(TAG_GLOSSARY.keys()))
    if not seen:
        return []
    rows = [(f"`{key}`", TAG_GLOSSARY[key][0], TAG_GLOSSARY[key][1]) for key in seen]
    return ["## 标签说明", "", md_table(("标签", "中文含义", "操作建议"), rows), ""]


def _collect_tokens(value: object) -> set[str]:
    tokens: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"tags", "risk_flags", "candidate_type", "candidate_types"}:
                if isinstance(item, list):
                    tokens.update(str(x) for x in item)
                elif item:
                    tokens.add(str(item))
            tokens.update(_collect_tokens(item))
    elif isinstance(value, list):
        for item in value:
            tokens.update(_collect_tokens(item))
    return tokens


def _payload(report: Any) -> dict[str, Any]:
    if is_dataclass(report):
        return asdict(report)
    if hasattr(report, "to_dict"):
        return dict(report.to_dict())
    return dict(report)


def _flatten_dict(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict):
            out.update(_flatten_dict(value, full_key))
        else:
            out[full_key] = value
    return out


def _label(value: object) -> str:
    text = str(value)
    if text in SPECIAL_FIELD_LABELS:
        return SPECIAL_FIELD_LABELS[text]
    if "." in text:
        return " - ".join(_label(part) for part in text.split("."))
    return FIELD_LABELS.get(text, TOKEN_LABELS.get(text, text))


def _format_tokens(values: object, max_items: int = 5) -> str:
    if values is None or values == []:
        return "无"
    if isinstance(values, str):
        return TOKEN_LABELS.get(values, values)
    if not isinstance(values, (list, tuple, set)):
        return _stringify(values)
    items = [TOKEN_LABELS.get(str(item), str(item)) for item in values if item not in (None, "")]
    if not items:
        return "无"
    if len(items) <= max_items:
        return "，".join(items)
    return "，".join(items[:max_items]) + f" 等{len(items)}项"


def _action_hint(flags: object) -> str:
    values = set(str(item) for item in flags) if isinstance(flags, list) else ({str(flags)} if flags else set())
    if "rsi_high" in values or "ret_5_strong" in values:
        return "短线偏热，谨慎追涨"
    if "near_20d_high" in values:
        return "降级为Watchlist：仅在回踩至量化支撑位附近且不破位时激活"
    if "mild_volatility" in values or "high_volatility" in values:
        return "控制仓位"
    if not values:
        return "优先观察"
    return "结合盘面确认"


def _stringify(value: object) -> str:
    if value is None:
        return "无"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (list, tuple, set)):
        items = [_stringify(item) for item in value if item not in (None, "")]
        return "，".join(items) if items else "无"
    if isinstance(value, dict):
        if not value:
            return "无"
        parts = [f"{_label(key)}：{_stringify(item)}" for key, item in _flatten_dict(value).items()]
        return "<br>".join(parts)
    if isinstance(value, float):
        return fmt_float(value)
    text = str(value)
    return TEXT_LABELS.get(text, LABELS.get(text, TOKEN_LABELS.get(text, text)))


def _escape_md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", "<br>")
