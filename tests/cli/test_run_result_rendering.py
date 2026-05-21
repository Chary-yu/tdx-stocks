from __future__ import annotations

from tdx_stocks.reports.rendering import render_run_result_markdown
from tdx_stocks.runner.models import RunResult
from tdx_stocks.runner.outputs import ensure_run_report_markdown


def test_signal_run_result_markdown_has_readable_signal_sections() -> None:
    result = RunResult(
        task_type="signal",
        name="today-signal",
        status="success",
        summary={
            "compare": {
                "as_of": "latest",
                "strategies": [
                    {
                        "strategy_name": "relative-strength",
                        "candidate_count": 1,
                        "avg_score": 88.8,
                        "max_score": 90.0,
                        "high_score_count": 1,
                        "risk_flag_count": 0,
                        "stocks": ["600519.SH"],
                    }
                ],
                "overlaps": [
                    {
                        "left_strategy": "relative-strength",
                        "right_strategy": "trend-strength",
                        "overlap_count": 1,
                        "stocks": ["600519.SH"],
                    }
                ],
                "unique_stocks": {"relative-strength": ["600519.SH"]},
            },
            "consensus": {
                "as_of": "latest",
                "min_hit": 2,
                "rows": [
                    {
                        "market": "sh",
                        "symbol": "600519",
                        "hit_count": 2,
                        "strategies": ["relative-strength", "trend-strength"],
                        "avg_score": 88.8,
                        "max_score": 90.0,
                        "candidate_types": ["strong_trend"],
                        "risk_flags": [],
                        "reasons": ["趋势向上"],
                    }
                ],
            },
        },
        outputs={"signal_markdown": "Database/reports/signal_markdown.md"},
    )

    markdown = render_run_result_markdown(result)

    assert "# Signal Report: today-signal" in markdown
    assert "## Strategy Compare" in markdown
    assert "### Unique Stocks" in markdown
    assert "## Consensus" in markdown
    assert "600519.SH" in markdown


def test_portfolio_backtest_grid_and_rebalance_have_task_sections() -> None:
    cases = [
        (
            RunResult(
                task_type="portfolio",
                name="portfolio",
                status="success",
                summary={
                    "as_of": "2024-01-31",
                    "source": "consensus",
                    "summary": {"holding_count": 1},
                    "risk_summary": {"passed": True},
                    "holdings": [{"market": "sh", "symbol": "600519", "weight": 0.1, "score": 88}],
                },
                outputs={"portfolio_markdown": "portfolio.md"},
            ),
            "# Portfolio Report: portfolio",
            "## Holdings",
        ),
        (
            RunResult(
                task_type="backtest",
                name="backtest",
                status="success",
                summary={
                    "strategy_name": "trend-strength",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                    "trade_count": 1,
                    "period_count": 1,
                    "total_return": 0.12,
                    "annual_return": 0.3,
                    "max_drawdown": -0.05,
                    "win_rate": 0.6,
                    "avg_period_return": 0.01,
                    "best_period_return": 0.03,
                    "worst_period_return": -0.02,
                    "turnover": 0.2,
                    "params": {"top": 20},
                    "trades": [{"market": "sh", "symbol": "600519", "net_return": 0.02}],
                },
                outputs={"backtest_markdown": "backtest.md"},
            ),
            "# Backtest Report: backtest",
            "## Performance Metrics",
        ),
        (
            RunResult(
                task_type="grid_search",
                name="grid",
                status="success",
                summary={
                    "strategy_name": "trend-strength",
                    "params": {"top": 20},
                    "rows": [{"min_score": 60, "top": 20, "hold_days": 5, "research_score": 0.1}],
                },
                outputs={"grid_markdown": "grid.md"},
            ),
            "# Grid Search Report: grid",
            "## Grid Results",
        ),
        (
            RunResult(
                task_type="rebalance",
                name="rebalance",
                status="success",
                summary={
                    "as_of": "2024-01-31",
                    "turnover": 0.1,
                    "current_holdings": [],
                    "target_holdings": [{"market": "sh", "symbol": "600519", "weight": 0.1}],
                    "weight_changes": [
                        {
                            "market": "sh",
                            "symbol": "600519",
                            "action": "buy",
                            "current_weight": 0.0,
                            "target_weight": 0.1,
                            "delta_weight": 0.1,
                            "reason": "new target",
                        }
                    ],
                },
                outputs={"rebalance_markdown": "rebalance.md"},
            ),
            "# Rebalance Report: rebalance",
            "## Rebalance Actions",
        ),
    ]

    for result, expected_title, expected_section in cases:
        markdown = render_run_result_markdown(result)
        assert expected_title in markdown
        assert expected_section in markdown
        body, _details = markdown.split("<details>", 1)
        assert '"summary"' not in body


def test_daily_markdown_report_is_not_overwritten(tmp_path) -> None:
    path = tmp_path / "latest.md"
    path.write_text("# TDX Stocks Daily Report\n\nrich daily report\n", encoding="utf-8")
    result = RunResult(task_type="daily", name="daily", status="success", summary={"daily": {}})

    returned = ensure_run_report_markdown(path, result)

    assert returned == path
    assert path.read_text(encoding="utf-8") == "# TDX Stocks Daily Report\n\nrich daily report\n"
