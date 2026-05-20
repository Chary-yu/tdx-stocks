from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main
from tdx_stocks.commands.run import RUN_CONFIG_PRESETS, _resolve_run_config


class RunCommandTest(unittest.TestCase):
    def test_presets_resolve_to_expected_templates(self) -> None:
        self.assertEqual(_resolve_run_config("daily"), RUN_CONFIG_PRESETS["daily"])
        self.assertEqual(_resolve_run_config("signal"), RUN_CONFIG_PRESETS["signal"])
        self.assertEqual(_resolve_run_config("portfolio"), RUN_CONFIG_PRESETS["portfolio"])
        self.assertEqual(_resolve_run_config("rebalance"), RUN_CONFIG_PRESETS["rebalance"])
        self.assertEqual(_resolve_run_config("backtest"), RUN_CONFIG_PRESETS["backtest"])
        self.assertEqual(_resolve_run_config("grid"), RUN_CONFIG_PRESETS["grid"])

    def test_custom_toml_is_not_rewritten(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / "custom.toml"
            toml_path.write_text("[task]\ntype = \"daily\"\n", encoding="utf-8")
            loaded = SimpleNamespace(
                app_config=SimpleNamespace(paths=SimpleNamespace(data_root=Path(tmp))),
                task_type="daily",
                task_name="daily",
                path=toml_path,
                config={"task": {"type": "daily"}},
            )
            with (
                patch("tdx_stocks.commands.run.load_run_config", return_value=loaded) as mocked_load,
                patch("tdx_stocks.commands.run.build_run_plan", return_value={"plan": 1}),
                patch("tdx_stocks.commands.run.render_run_plan", return_value="plan"),
                patch("tdx_stocks.commands.run.dispatch_run", return_value=SimpleNamespace(task_type="daily", status="success", to_dict=lambda: {"ok": True})) as mocked_dispatch,
                patch("tdx_stocks.commands.run.save_latest_run_report"),
            ):
                code = cli_main(["run", toml_path.as_posix(), "--dry-run"])
            self.assertEqual(code, 0)
            mocked_load.assert_called_once_with(toml_path)
            mocked_dispatch.assert_not_called()

    def test_run_daily_preset_and_json_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "run.json"
            loaded = SimpleNamespace(
                app_config=SimpleNamespace(paths=SimpleNamespace(data_root=Path(tmp))),
                task_type="daily",
                task_name="daily",
                path=Path("experiments/daily.toml"),
                config={"task": {"type": "daily"}},
            )
            with (
                patch("tdx_stocks.commands.run.load_run_config", return_value=loaded),
                patch("tdx_stocks.commands.run.build_run_plan", return_value={"step": "plan"}),
                patch("tdx_stocks.commands.run.render_run_plan", return_value="plan"),
                patch("tdx_stocks.commands.run.dispatch_run", return_value=SimpleNamespace(task_type="daily", status="success", to_dict=lambda: {"status": "success"})),
                patch("tdx_stocks.commands.run.build_latest_run_report", return_value={"status": "success"}),
                patch("tdx_stocks.commands.run.save_latest_run_report"),
            ):
                code = cli_main(["run", "daily", "--json", "--output", output_path.as_posix()])
            self.assertEqual(code, 0)
            self.assertTrue(output_path.exists())

    def test_dry_run_and_explain_do_not_dispatch(self) -> None:
        loaded = SimpleNamespace(
            app_config=SimpleNamespace(paths=SimpleNamespace(data_root=Path("/tmp"))),
            task_type="daily",
            task_name="daily",
            path=Path("experiments/daily.toml"),
            config={"task": {"type": "daily"}},
        )
        with (
            patch("tdx_stocks.commands.run.load_run_config", return_value=loaded),
            patch("tdx_stocks.commands.run.build_run_plan", return_value={"plan": 1}),
            patch("tdx_stocks.commands.run.render_run_plan", return_value="plan"),
            patch("tdx_stocks.commands.run.dispatch_run") as mocked_dispatch,
            patch("tdx_stocks.commands.run.save_latest_run_report"),
        ):
            code = cli_main(["run", "daily", "--dry-run"])
            self.assertEqual(code, 0)
            code = cli_main(["run", "daily", "--explain", "--json"])
        self.assertEqual(code, 0)
        mocked_dispatch.assert_not_called()
