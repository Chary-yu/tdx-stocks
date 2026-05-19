from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import build_parser, main as cli_main
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
                self.assertTrue((root / "holdings.csv.example").exists())
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
        self.assertIn("tdx-stocks data sync", help_text)
        self.assertIn("tdx-stocks run <config.toml>", help_text)
        self.assertIn("tdx-stocks ui", help_text)
        self.assertIn("tdx-stocks help-summary", help_text)


if __name__ == "__main__":
    unittest.main()
