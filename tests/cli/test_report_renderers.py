from __future__ import annotations

import unittest

from tdx_stocks.daily.models import DailyRunReport
from tdx_stocks.reports.renderers import render_daily_markdown, render_portfolio_markdown, render_strategy_markdown


class ReportRenderersTest(unittest.TestCase):
    def test_daily_markdown_has_key_sections_and_hides_raw_json_in_body(self) -> None:
        report = DailyRunReport(
            schema_version="daily-report-v1",
            app_version="0.7.0",
            as_of="2024-01-31",
            generated_at="2024-02-01T10:00:00",
            data_run_id="run-1",
            status="success",
            steps=[],
            summary={"step_count": 2, "warning_count": 0, "error_count": 0},
            data_quality={"checks": [{"name": "factors", "passed": True, "detail": "ok"}]},
            strategy_summary={"strategies": ["trend-strength"]},
            consensus_summary={"rows": [{"market": "sh", "symbol": "600519", "hit_count": 2, "avg_score": 88.2, "max_score": 91.1, "strategies": ["trend-strength"], "risk_flags": []}]},
            portfolio_summary={
                "source": "consensus",
                "as_of": "2024-01-31",
                "generated_at": "2024-02-01T10:00:00",
                "data_run_id": "run-1",
                "summary": {"holding_count": 1, "市场暴露": {"sh": 0.625, "sz": 0.375}},
                "risk_summary": {"passed": True},
                "holdings": [{"market": "sh", "symbol": "600519", "weight": 0.12, "score": 88.2, "source_strategy": "trend-strength", "candidate_type": "strong_trend", "risk_flags": ["none"], "tags": ["trend"], "reason": "top pick", "factor_values": {"holdings": [1, 2, 3]}}],
                "diagnostics": {"holdings": [1, 2, 3]},
            },
            rebalance_summary={"turnover": 0.2},
            warnings=["watch liquidity"],
            errors=[],
            outputs={"latest_md": "/tmp/daily.md"},
        )
        markdown = render_daily_markdown(report)
        self.assertIn("## 数据质量", markdown)
        self.assertIn("## 组合摘要", markdown)
        self.assertIn("## 风险摘要", markdown)
        self.assertIn("## 输出文件", markdown)
        self.assertIn("## 原始 JSON", markdown)
        self.assertIn("Database/report_payloads/", markdown)
        self.assertIn("市场暴露", markdown)
        self.assertNotIn('"holdings": [', markdown)
        self.assertNotIn('"diagnostics"', markdown)
        self.assertNotIn("{'市场暴露':", markdown)

    def test_strategy_and_portfolio_markdown_have_readable_sections(self) -> None:
        strategy_markdown = render_strategy_markdown(
            {
                "strategy_name": "trend-strength",
                "display_name": "Trend Strength",
                "description": "strong trend",
                "group": "trend",
                "style": "momentum",
                "required_fields": ["ma20"],
                "optional_fields": ["rsi_14"],
                "candidate_types": ["strong_trend"],
                "risk_tags": ["high_volatility"],
                "aliases": ["trend"],
                "supported_research_capabilities": ["run", "backtest"],
                "as_of": "latest",
                "generated_at": "2024-02-01T10:00:00",
                "data_run_id": "run-1",
                "candidate_count": 1,
                "excluded_count": 0,
                "candidates": [{"market": "sh", "symbol": "600519", "score": 88.2, "candidate_type": "strong_trend", "tags": ["trend"], "risk_flags": [], "reason": "top pick"}],
                "excluded_summary": {"total": 2, "reasons": {"foo": 1, "bar": 2}},
                "risk_summary": {"high_volatility": 1},
            }
        )
        portfolio_markdown = render_portfolio_markdown(
            {
                "source": "consensus",
                "as_of": "2024-01-31",
                "generated_at": "2024-02-01T10:00:00",
                "data_run_id": "run-1",
                "summary": {"holding_count": 1, "市场暴露": {"sh": 0.625, "sz": 0.375}},
                "risk_summary": {"passed": True},
                "holdings": [{"market": "sh", "symbol": "600519", "weight": 0.12, "score": 88.2, "source_strategy": "trend-strength", "candidate_type": "strong_trend", "risk_flags": ["none"], "tags": ["trend"], "reason": "top pick"}],
            }
        )
        self.assertIn("## 策略定义", strategy_markdown)
        self.assertIn("## 候选股票", strategy_markdown)
        self.assertIn("| foo | 1 |", strategy_markdown)
        self.assertIn("## 组合摘要", portfolio_markdown)
        self.assertIn("## 目标持仓", portfolio_markdown)
        self.assertIn("市场暴露", portfolio_markdown)
        self.assertNotIn("{'市场暴露':", portfolio_markdown)
