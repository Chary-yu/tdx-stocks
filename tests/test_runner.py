from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import build_parser, main as cli_main
from tdx_stocks.commands.run import RUN_CONFIG_PRESETS, _resolve_run_config
from tdx_stocks.runner import dispatch_run, load_run_config
from tdx_stocks.runner.errors import InvalidRunConfigError
from tdx_stocks.runner.models import RunResult


class InitCommandTest(unittest.TestCase):
    def test_init_generates_workspace_templates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                code = cli_main(["init", "--data-root", "Database"])
                root = Path(tmp)
                self.assertEqual(code, 0)
                self.assertTrue((root / "tdx_stocks.toml").exists())
                self.assertTrue((root / "experiments" / "daily.toml").exists())
                self.assertTrue((root / "experiments" / "backtest.toml").exists())
                self.assertTrue((root / "experiments" / "portfolio.toml").exists())
                self.assertTrue((root / "experiments" / "advanced" / "signal.toml").exists())
                self.assertTrue((root / "experiments" / "advanced" / "grid_search.toml").exists())
                self.assertTrue((root / "experiments" / "advanced" / "rebalance.toml").exists())
                self.assertTrue((root / "holdings.csv.example").exists())
                payload = (root / "tdx_stocks.toml").read_text(encoding="utf-8")
                self.assertIn('tdx_vipdoc = "./vipdoc"', payload)
                self.assertIn('tdx_export = "./export"', payload)
                self.assertIn('portfolio_max_weight = 0.08', payload)
                self.assertTrue((root / "vipdoc").exists())
                self.assertTrue((root / "export").exists())
                self.assertTrue((root / "Database").exists())
                self.assertTrue((root / "reports" / "daily").exists())
                self.assertTrue((root / "reports" / "backtests").exists())
                self.assertTrue((root / "reports" / "portfolios").exists())
                self.assertTrue((root / "reports" / "signals").exists())
                self.assertTrue((root / "reports" / "grid_search").exists())
                self.assertTrue((root / "reports" / "rebalance").exists())
            finally:
                os.chdir(cwd)

    def test_init_force_overwrites_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                Path("tdx_stocks.toml").write_text("old", encoding="utf-8")
                cli_main(["init", "--force", "--data-root", "Database"])
                self.assertIn("[paths]", Path("tdx_stocks.toml").read_text(encoding="utf-8"))
            finally:
                os.chdir(cwd)

    def test_init_minimal_creates_minimal_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                cli_main(["init", "--minimal", "--data-root", "Database"])
                self.assertTrue((Path("experiments") / "daily.toml").exists())
                self.assertFalse((Path("experiments") / "backtest.toml").exists())
                self.assertFalse((Path("holdings.csv.example")).exists())
            finally:
                os.chdir(cwd)

    def test_init_research_profile_uses_full_research_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                cli_main(["init", "--profile", "research", "--data-root", "Database"])
                payload = Path("tdx_stocks.toml").read_text(encoding="utf-8")
                daily = Path("experiments/daily.toml").read_text(encoding="utf-8")
                backtest = Path("experiments/backtest.toml").read_text(encoding="utf-8")
            finally:
                os.chdir(cwd)

        self.assertIn('enabled_strategies = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]', payload)
        self.assertIn('strategy_limit = 50', payload)
        self.assertIn('strategy_min_score = 60.0', payload)
        self.assertIn('portfolio_max_weight = 0.10', payload)
        self.assertIn('enabled = ["trend-strength", "relative-strength", "low-vol-breakout", "volume-breakout"]', daily)
        self.assertIn('hold_days = 5', backtest)
        self.assertIn('top = 20', backtest)
        self.assertIn('enabled = false', daily)

    def test_init_portfolio_profile_tunes_portfolio_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                cli_main(["init", "--profile", "portfolio", "--data-root", "Database"])
                payload = Path("tdx_stocks.toml").read_text(encoding="utf-8")
                portfolio = Path("experiments/portfolio.toml").read_text(encoding="utf-8")
                rebalance = Path("experiments/advanced/rebalance.toml").read_text(encoding="utf-8")
            finally:
                os.chdir(cwd)

        self.assertIn('portfolio_top = 50', payload)
        self.assertIn('portfolio_max_weight = 0.05', payload)
        self.assertIn('top = 50', portfolio)
        self.assertIn('max_weight = 0.05', portfolio)
        self.assertIn('enabled = true', rebalance)
        self.assertIn('min_trade_weight = 0.005', rebalance)


class RunSchemaTest(unittest.TestCase):
    def test_missing_task_type_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text("[backtest]\nfrom_date = \"2024-01-01\"\n", encoding="utf-8")
            with self.assertRaisesRegex(InvalidRunConfigError, "\\[task\\]"):
                load_run_config(path)

    def test_invalid_backtest_key_has_suggestion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.toml"
            path.write_text(
                """
[task]
type = "backtest"

[strategy]
name = "trend-strength"

[backtest]
from = "2022-01-01"
to_date = "2024-12-31"
""".strip(),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InvalidRunConfigError, "from_date"):
                load_run_config(path)

    def test_relative_paths_are_resolved_against_config_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_path = root / "experiments" / "daily.toml"
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(
                """
[task]
type = "daily"

[rebalance]
current_holdings = "../holdings.csv"
""".strip(),
                encoding="utf-8",
            )
            loaded = load_run_config(config_path)
        self.assertTrue(loaded.config["rebalance"]["current_holdings"].endswith("holdings.csv"))

    def test_run_config_auto_detects_standard_tdx_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vipdoc = root / "vipdoc"
            export_dir = root / "T0002" / "export"
            (vipdoc / "sh" / "lday").mkdir(parents=True)
            (vipdoc / "sh" / "lday" / "sh600000.day").write_bytes(b"day")
            export_dir.mkdir(parents=True)
            (export_dir / "sh600000.txt").write_text("code,date,open,high,low,close,volume,amount\n", encoding="utf-8")
            config_path = root / "daily.toml"
            config_path.write_text(
                """
[task]
type = "daily"

[paths]
tdx_vipdoc = "./vipdoc"
tdx_export = "./export"
data_root = "./Database"
""".strip(),
                encoding="utf-8",
            )
            with patch("tdx_stocks.config._candidate_tdx_roots", return_value=(root,)):
                loaded = load_run_config(config_path)
        self.assertEqual(loaded.app_config.paths.tdx_vipdoc, vipdoc)
        self.assertEqual(loaded.app_config.paths.tdx_export, export_dir)

    def test_daily_config_is_loaded_without_backtest_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.toml"
            path.write_text(
                """
[task]
type = "daily"
name = "daily-workflow"

[strategies]
enabled = ["trend-strength"]

[portfolio]
enabled = true
""".strip(),
                encoding="utf-8",
            )
            loaded = load_run_config(path)
        self.assertEqual(loaded.task_type, "daily")
        self.assertEqual(loaded.task_name, "daily-workflow")


class RunDispatcherTest(unittest.TestCase):
    def test_dispatches_to_daily_signal_backtest_portfolio_and_rebalance(self) -> None:
        cases = [
            ("daily", "run_daily_task"),
            ("signal", "run_signal_task"),
            ("backtest", "run_backtest_task"),
            ("grid_search", "run_grid_search_task"),
            ("portfolio", "run_portfolio_task"),
            ("rebalance", "run_rebalance_task"),
        ]
        for task_type, attr in cases:
            with self.subTest(task_type=task_type):
                run_config = type(
                    "RunConfig",
                    (),
                    {
                        "task_type": task_type,
                        "app_config": object(),
                        "config": {"task": {"name": task_type}},
                    },
                )()
                sentinel = RunResult(task_type=task_type, name=task_type, status="success", summary={})
                with patch(f"tdx_stocks.runner.dispatcher.{attr}", return_value=sentinel):
                    result = dispatch_run(run_config)
                self.assertEqual(result, sentinel)


class RootHelpTest(unittest.TestCase):
    def test_root_help_mentions_new_primary_commands(self) -> None:
        help_text = build_parser().format_help()
        self.assertIn("tdx-stocks init", help_text)
        self.assertIn("tdx-stocks sync", help_text)
        self.assertIn("tdx-stocks run daily", help_text)
        self.assertIn("tdx-stocks query stock 600519.SH", help_text)
        self.assertIn("tdx-stocks ui", help_text)
        self.assertIn("tdx-stocks doctor", help_text)
        self.assertIn("tdx-stocks status", help_text)
        self.assertIn("tdx-stocks report", help_text)
        self.assertIn("tdx-stocks help run", help_text)
        self.assertNotIn("==SUPPRESS==", help_text)


class RunCommandTest(unittest.TestCase):
    def test_run_preset_names_resolve_to_templates(self) -> None:
        for preset, expected in RUN_CONFIG_PRESETS.items():
            with self.subTest(preset=preset):
                self.assertEqual(_resolve_run_config(preset), expected)

    def test_dry_run_does_not_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.toml"
            path.write_text(
                """
[task]
type = "daily"

[strategies]
enabled = ["trend-strength"]
""".strip(),
                encoding="utf-8",
            )
            with patch("tdx_stocks.commands.run.dispatch_run") as dispatch_run_mock:
                code = cli_main(["run", str(path), "--dry-run"])
            self.assertEqual(code, 0)
            dispatch_run_mock.assert_not_called()

    def test_preset_run_resolves_daily_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                (Path("experiments")).mkdir(parents=True, exist_ok=True)
                (Path("experiments") / "daily.toml").write_text(
                    """
[task]
type = "daily"

[strategies]
enabled = ["trend-strength"]
""".strip(),
                    encoding="utf-8",
                )
                with patch("tdx_stocks.commands.run.dispatch_run") as dispatch_run_mock:
                    code = cli_main(["run", "daily", "--dry-run"])
                self.assertEqual(code, 0)
                dispatch_run_mock.assert_not_called()
            finally:
                os.chdir(cwd)

    def test_explain_does_not_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily.toml"
            path.write_text(
                """
[task]
type = "daily"

[strategies]
enabled = ["trend-strength"]
""".strip(),
                encoding="utf-8",
            )
            with patch("tdx_stocks.commands.run.dispatch_run") as dispatch_run_mock:
                code = cli_main(["run", str(path), "--explain"])
            self.assertEqual(code, 0)
            dispatch_run_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
