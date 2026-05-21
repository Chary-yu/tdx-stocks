from __future__ import annotations

from tdx_stocks.reports.rendering import render_run_result_markdown


def test_daily_report_contains_risk_sections() -> None:
    result = {
        "task_type": "daily",
        "name": "daily",
        "status": "failed",
        "summary": {
            "daily": {"step_count": 9, "warning_count": 0, "error_count": 1},
            "daily_report": {
                "summary": {"warning_count": 0, "error_count": 1},
                "data_quality": {"checks": [{"name": "factors", "passed": True}]},
                "portfolio_summary": {
                    "diagnostics": {"market_regime": {"status": "bear", "action": "pause_open", "reason": "test"}, "risk_interceptions": []}
                },
            },
        },
        "outputs": {},
    }
    markdown = render_run_result_markdown(result)
    assert "系统级风控结论" in markdown
    assert "数据质量错误等级" in markdown
    assert "市场环境滤网" in markdown
