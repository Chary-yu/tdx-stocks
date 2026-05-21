from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tdx_stocks.config import AppConfig, PathsConfig
from tdx_stocks.runner.backtest import run_backtest_task
from tdx_stocks.runner.config import LoadedRunConfig
from tdx_stocks.runner.daily import run_daily_task
from tdx_stocks.runner.grid_search import run_grid_search_task
from tdx_stocks.runner.outputs import (
    build_latest_run_report,
    build_run_plan,
    load_latest_run_report,
    render_run_plan,
    save_latest_run_report,
)
from tdx_stocks.runner.portfolio import run_portfolio_task
from tdx_stocks.runner.rebalance import run_rebalance_task
from tdx_stocks.runner.signal import run_signal_task
from tdx_stocks.reports.rendering import render_run_result_markdown
from tdx_stocks.sync import SyncPlanStep, build_sync_plan, execute_sync

pytestmark = pytest.mark.integration


def _loaded_run_config(task_type: str, config: dict[str, object]) -> LoadedRunConfig:
    return LoadedRunConfig(
        raw_config=config,
        config=config,
        run_config=None,
        app_config=AppConfig(paths=PathsConfig(data_root=Path(tempfile.gettempdir()) / "tdx-stocks-runner-test")),
        path=Path(f"/tmp/{task_type}.toml"),
        base_dir=Path("/tmp"),
        task_type=task_type,
        task_name=str(config["task"]["name"]),  # type: ignore[index]
    )


class RunnerOutputsTest(unittest.TestCase):
    def test_build_run_plan_and_render_daily(self) -> None:
        config = {
            "task": {"type": "daily", "name": "daily-workflow"},
            "data": {"as_of": "latest"},
            "strategies": {"enabled": ["trend-strength"], "limit": 25, "min_score": 62.0},
            "consensus": {"min_hit": 2},
            "portfolio": {"top": 10, "weighting": "equal"},
            "rebalance": {"current_holdings": "holdings.csv"},
        }
        run_config = _loaded_run_config("daily", config)

        plan = build_run_plan(run_config)
        rendered = render_run_plan(plan)

        self.assertEqual(plan["task"]["type"], "daily")
        self.assertEqual(plan["inputs"]["strategies"], ["trend-strength"])
        self.assertIn("run selected strategies", rendered)
        self.assertIn("reports/daily_<date>.md", rendered)
        self.assertIn("report_payloads/daily_<date>.json", rendered)

    def test_build_run_plan_handles_portfolio_and_backtest(self) -> None:
        portfolio_config = {
            "task": {"type": "portfolio", "name": "portfolio-build"},
            "portfolio": {"source": "consensus", "top": 12, "weighting": "score"},
            "data": {"as_of": "2024-01-31"},
        }
        backtest_config = {
            "task": {"type": "backtest", "name": "backtest-run"},
            "strategy": {"name": "trend-strength", "limit": 8, "min_score": 65.0},
            "backtest": {"from_date": "2024-01-01", "to_date": "2024-01-31", "hold_days": 5},
        }
        portfolio_plan = build_run_plan(_loaded_run_config("portfolio", portfolio_config))
        backtest_plan = build_run_plan(_loaded_run_config("backtest", backtest_config))

        self.assertEqual(portfolio_plan["inputs"]["source"], "consensus")
        self.assertEqual(backtest_plan["inputs"]["strategy"], "trend-strength")
        self.assertIn("reports/backtest_<date>.md", backtest_plan["outputs"]["reports"])
        self.assertIn("report_payloads/backtest_<date>.json", backtest_plan["outputs"]["payloads"])

    def test_save_and_load_latest_run_report_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            report = build_latest_run_report(
                _loaded_run_config("daily", {"task": {"type": "daily", "name": "daily-workflow"}}),
                SimpleNamespace(
                    task_type="daily",
                    name="daily-workflow",
                    status="success",
                    outputs={"daily_json": "/tmp/daily.json"},
                    warnings=["warn"],
                    errors=[],
                    to_dict=lambda: {"task_type": "daily", "status": "success"},
                ),
            )
            saved = save_latest_run_report(data_root, report)
            loaded = load_latest_run_report(data_root)
            self.assertTrue(saved.exists())
            self.assertEqual(loaded["status"], "success")
            self.assertEqual(loaded["task_type"], "daily")


class RunnerTaskAdapterTest(unittest.TestCase):
    def test_runner_adapters_pass_expected_parameters(self) -> None:
        daily_config = _loaded_run_config(
            "daily",
            {
                "task": {"type": "daily", "name": "daily-workflow"},
                "data": {"as_of": "2024-01-31"},
                "strategies": {"enabled": ["trend-strength"], "limit": 25, "min_score": 62.0},
                "consensus": {"min_hit": 2},
                "portfolio": {"top": 10, "weighting": "equal", "exclude_risk_tags": ["risk_factor_missing"]},
                "rebalance": {"current_holdings": "holdings.csv"},
            },
        )
        backtest_config = _loaded_run_config(
            "backtest",
            {
                "task": {"type": "backtest", "name": "backtest-run"},
                "strategy": {"name": "trend-strength", "limit": 8, "min_score": 65.0, "min_amount_ma20": 1_000_000.0},
                "backtest": {
                    "from_date": "2024-01-01",
                    "to_date": "2024-01-31",
                    "top": 12,
                    "hold_days": 7,
                    "fee_rate": 0.001,
                    "slippage_bps": 10.0,
                },
            },
        )
        grid_config = _loaded_run_config(
            "grid_search",
            {
                "task": {"type": "grid_search", "name": "grid-run"},
                "strategy": {"name": "trend-strength"},
                "backtest": {"from_date": "2024-01-01", "to_date": "2024-01-31"},
                "grid": {"strategy.min_score": [55, 60], "backtest.top": [10], "backtest.hold_days": [5, 10]},
            },
        )
        portfolio_config = _loaded_run_config(
            "portfolio",
            {
                "task": {"type": "portfolio", "name": "portfolio-build"},
                "portfolio": {"source": "consensus", "top": 12, "weighting": "score"},
                "data": {"as_of": "2024-01-31"},
            },
        )
        rebalance_config = _loaded_run_config(
            "rebalance",
            {
                "task": {"type": "rebalance", "name": "rebalance-run"},
                "portfolio": {"source": "consensus", "top": 12, "weighting": "score"},
                "data": {"as_of": "2024-01-31"},
                "rebalance": {"current_holdings": "holdings.csv", "min_trade_weight": 0.01, "max_turnover": 0.5},
            },
        )
        signal_config = _loaded_run_config(
            "signal",
            {
                "task": {"type": "signal", "name": "signal-run"},
                "data": {"as_of": "2024-01-31"},
                "strategies": {"enabled": ["trend-strength", "relative-strength"]},
                "consensus": {"min_hit": 2},
            },
        )

        fake_daily = SimpleNamespace(
            report=SimpleNamespace(summary={"status": "ok"}, status="success", warnings=[], errors=[]),
            outputs={"daily_json": "/tmp/daily.json"},
        )
        fake_backtest = SimpleNamespace(to_dict=lambda: {"rows": [{"strategy_name": "trend-strength"}]})
        fake_portfolio = SimpleNamespace(
            holdings=[],
            as_of="2024-01-31",
            to_dict=lambda: {"holdings": [], "summary": {"source": "consensus"}},
        )
        fake_plan = SimpleNamespace(to_dict=lambda: {"weight_changes": []}, as_of="2024-01-31")
        fake_signal_compare = SimpleNamespace(to_dict=lambda: {"rows": []})
        fake_signal_consensus = SimpleNamespace(to_dict=lambda: {"rows": []})

        with (
            patch("tdx_stocks.runner.daily.run_daily_workflow", return_value=fake_daily),
            patch("tdx_stocks.runner.backtest.run_backtest", return_value=fake_backtest),
            patch("tdx_stocks.runner.grid_search.tune_strategy_parameters", return_value={"rows": []}) as mocked_tune,
            patch("tdx_stocks.runner.portfolio.build_portfolio", return_value=fake_portfolio),
            patch("tdx_stocks.runner.rebalance.build_portfolio", return_value=fake_portfolio),
            patch("tdx_stocks.runner.rebalance.load_current_holdings_csv", return_value=[]),
            patch("tdx_stocks.runner.rebalance.build_rebalance_plan", return_value=fake_plan),
            patch("tdx_stocks.runner.signal.compare_strategies", return_value=fake_signal_compare),
            patch("tdx_stocks.runner.signal.build_consensus", return_value=fake_signal_consensus),
        ):
            daily_result = run_daily_task(daily_config)
            backtest_result = run_backtest_task(backtest_config)
            grid_result = run_grid_search_task(grid_config)
            portfolio_result = run_portfolio_task(portfolio_config)
            rebalance_result = run_rebalance_task(rebalance_config)
            signal_result = run_signal_task(signal_config)

        self.assertEqual(daily_result.summary["daily"]["status"], "ok")
        self.assertEqual(backtest_result.summary["rows"][0]["strategy_name"], "trend-strength")
        self.assertEqual(grid_result.summary["rows"], [])
        self.assertEqual(portfolio_result.summary["holdings"], [])
        self.assertEqual(rebalance_result.summary["weight_changes"], [])
        self.assertEqual(signal_result.summary["compare"]["rows"], [])
        mocked_tune.assert_called_once()

    def test_render_run_result_markdown_formats_signal_summary(self) -> None:
        result = SimpleNamespace(
            task_type="signal",
            name="today-signal",
            status="success",
            outputs={"signal_markdown": "Database/reports/signal_markdown.md"},
            warnings=[],
            errors=[],
            summary={
                "compare": {
                    "as_of": "latest",
                    "strategies": [
                        {
                            "strategy_name": "trend-strength",
                            "candidate_count": 2,
                            "avg_score": 88.75,
                            "max_score": 91.0,
                            "high_score_count": 1,
                            "risk_flag_count": 1,
                            "stocks": ["600519.SH", "000001.SZ"],
                        }
                    ],
                    "overlaps": [
                        {
                            "left_strategy": "trend-strength",
                            "right_strategy": "relative-strength",
                            "overlap_count": 1,
                            "stocks": ["600519.SH"],
                        }
                    ],
                    "unique_stocks": {"trend-strength": ["000001.SZ"]},
                },
                "consensus": {
                    "as_of": "latest",
                    "rows": [
                        {
                            "market": "sh",
                            "symbol": "600519",
                            "hit_count": 2,
                            "avg_score": 89.4,
                            "max_score": 91.0,
                            "strategies": ["trend-strength", "relative-strength"],
                            "risk_flags": ["mild_volatility"],
                        }
                    ],
                },
            },
            to_dict=lambda: {
                "task_type": "signal",
                "name": "today-signal",
                "status": "success",
                "summary": {
                    "compare": {
                        "as_of": "latest",
                        "strategies": [
                            {
                                "strategy_name": "trend-strength",
                                "candidate_count": 2,
                                "avg_score": 88.75,
                                "max_score": 91.0,
                                "high_score_count": 1,
                                "risk_flag_count": 1,
                                "stocks": ["600519.SH", "000001.SZ"],
                            }
                        ],
                        "overlaps": [
                            {
                                "left_strategy": "trend-strength",
                                "right_strategy": "relative-strength",
                                "overlap_count": 1,
                                "stocks": ["600519.SH"],
                            }
                        ],
                        "unique_stocks": {"trend-strength": ["000001.SZ"]},
                    },
                    "consensus": {
                        "as_of": "latest",
                        "rows": [
                            {
                                "market": "sh",
                                "symbol": "600519",
                                "hit_count": 2,
                                "avg_score": 89.4,
                                "max_score": 91.0,
                                "strategies": ["trend-strength", "relative-strength"],
                                "risk_flags": ["mild_volatility"],
                            }
                        ],
                    },
                },
                "outputs": {"signal_markdown": "Database/reports/signal_markdown.md"},
                "warnings": [],
                "errors": [],
            },
        )

        markdown = render_run_result_markdown(result)

        self.assertIn("## 策略对比", markdown)
        self.assertIn("## 共振股票", markdown)
        self.assertIn("## 策略独有股票", markdown)
        self.assertIn("趋势强度，相对强度", markdown)
        self.assertIn("600519.SH，000001.SZ", markdown)

    def test_render_run_result_markdown_formats_daily_summary(self) -> None:
        result = SimpleNamespace(
            task_type="daily",
            name="daily-workflow",
            status="success",
            outputs={"latest_md": "Database/reports/daily/latest.md"},
            warnings=[],
            errors=[],
            summary={
                "daily": {
                    "step_count": 6,
                    "warning_count": 1,
                    "error_count": 0,
                }
            },
            to_dict=lambda: {
                "task_type": "daily",
                "name": "daily-workflow",
                "status": "success",
                "summary": {"daily": {"step_count": 6, "warning_count": 1, "error_count": 0}},
                "outputs": {"latest_md": "Database/reports/daily/latest.md"},
                "warnings": [],
                "errors": [],
            },
        )

        markdown = render_run_result_markdown(result)

        self.assertIn("## 运行摘要", markdown)
        self.assertIn("step_count", markdown)
        self.assertIn("warning_count", markdown)
        self.assertIn("error_count", markdown)

    def test_render_run_result_markdown_prefers_stock_names_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            export_dir = root / "export"
            export_dir.mkdir(parents=True)
            (export_dir / "SH#600519.txt").write_text("600519 贵州茅台 日线\n", encoding="gbk")
            config = AppConfig(paths=PathsConfig(data_root=root / "Database", tdx_export=export_dir))
            result = SimpleNamespace(
                task_type="signal",
                name="today-signal",
                status="success",
                outputs={"signal_markdown": "Database/reports/signal_markdown.md"},
                warnings=[],
                errors=[],
                summary={
                    "compare": {"strategies": [{"strategy_name": "trend-strength", "stocks": ["600519.SH"]}]},
                    "consensus": {"rows": [{"market": "sh", "symbol": "600519", "hit_count": 2, "avg_score": 90.0}]},
                },
                to_dict=lambda: {
                    "task_type": "signal",
                    "name": "today-signal",
                    "status": "success",
                    "summary": {
                        "compare": {"strategies": [{"strategy_name": "trend-strength", "stocks": ["600519.SH"]}]},
                        "consensus": {"rows": [{"market": "sh", "symbol": "600519", "hit_count": 2, "avg_score": 90.0}]},
                    },
                    "outputs": {"signal_markdown": "Database/reports/signal_markdown.md"},
                    "warnings": [],
                    "errors": [],
                },
            )

            markdown = render_run_result_markdown(result, app_config=config)

        self.assertIn("贵州茅台", markdown)
        self.assertIn("股票代码：600519.SH", markdown)


class SyncTest(unittest.TestCase):
    def test_build_sync_plan_and_execute_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "Database"
            export_dir = root / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            config = AppConfig(paths=PathsConfig(data_root=data_root, tdx_export=export_dir))
            latest_manifest = {"summary": {"generated_at": "2024-02-01T10:00:00"}}
            plan = None

            with (
                patch("tdx_stocks.sync.load_latest_manifest", return_value=latest_manifest),
                patch("tdx_stocks.sync.iter_export_files", return_value=iter(())),
                patch("tdx_stocks.sync.has_parquet_files", return_value=False),
            ):
                plan = build_sync_plan(config)

            self.assertIsNotNone(plan)
            self.assertTrue(plan.needs_write)
            self.assertEqual(plan.steps[0], SyncPlanStep("refresh export cache", "no export text files found; using local sync"))

            with (
                patch("tdx_stocks.sync._has_export_text_files", return_value=True),
                patch("tdx_stocks.sync.update_actions", return_value={"source": "export"}) as mocked_update,
                patch("tdx_stocks.sync.rebuild_dataset", return_value={"run_id": "run-1"}) as mocked_rebuild,
            ):
                result = execute_sync(
                    config,
                    plan,
                    from_date=date(2024, 1, 1),
                    to_date=date(2024, 1, 31),
                    limit_symbols=2,
                    overwrite_staging=True,
                )

            self.assertEqual(result.update_report, {"source": "export"})
            self.assertEqual(result.build_report, {"run_id": "run-1"})
            mocked_update.assert_called_once()
            mocked_rebuild.assert_called_once()
