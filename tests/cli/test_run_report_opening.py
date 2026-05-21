from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main


class RunReportOpeningCliTest(unittest.TestCase):
    def test_run_presets_open_report_path(self) -> None:
        presets = {
            "daily": "daily_markdown",
            "signal": "signal_markdown",
            "portfolio": "portfolio_markdown",
            "rebalance": "rebalance_markdown",
            "backtest": "backtest_markdown",
            "grid": "grid_markdown",
        }
        for preset, output_key in presets.items():
            with self.subTest(preset=preset):
                with tempfile.TemporaryDirectory() as tmp:
                    data_root = Path(tmp)
                    result = SimpleNamespace(
                        task_type=preset,
                        status="success",
                        name=preset,
                        outputs={output_key: (data_root / "reports" / f"{preset}.md").as_posix()},
                        to_dict=lambda: {"task_type": preset, "status": "success", "outputs": {}},
                    )
                    loaded = SimpleNamespace(
                        app_config=SimpleNamespace(paths=SimpleNamespace(data_root=data_root)),
                        task_type=preset if preset != "grid" else "grid_search",
                        task_name=preset,
                        path=Path(f"experiments/{preset}.toml"),
                        config={"task": {"type": preset}},
                    )
                    with (
                        patch("tdx_stocks.commands.run.load_run_config", return_value=loaded),
                        patch("tdx_stocks.commands.run.build_run_plan", return_value={"plan": 1}),
                        patch("tdx_stocks.commands.run.dispatch_run", return_value=result),
                        patch("tdx_stocks.commands.run.build_latest_run_report", return_value={"status": "success"}),
                        patch("tdx_stocks.commands.run.save_latest_run_report"),
                        patch("tdx_stocks.commands.run.ensure_run_report_markdown") as mocked_save_md,
                        patch("tdx_stocks.reports.opening.open_file") as mocked_open,
                    ):
                        stdout = io.StringIO()
                        with contextlib.redirect_stdout(stdout):
                            code = cli_main([ "run", preset ])
                        self.assertEqual(code, 0)
                        self.assertIn("Report:", stdout.getvalue())
                        if preset == "daily":
                            mocked_save_md.assert_not_called()
                        else:
                            mocked_save_md.assert_called_once()
                        mocked_open.assert_called_once()

    def test_run_no_open_json_and_dry_run_skip_opening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            result = SimpleNamespace(
                task_type="daily",
                status="success",
                name="daily",
                outputs={"daily_markdown": (data_root / "reports" / "daily.md").as_posix()},
                to_dict=lambda: {"task_type": "daily", "status": "success"},
            )
            loaded = SimpleNamespace(
                app_config=SimpleNamespace(paths=SimpleNamespace(data_root=data_root)),
                task_type="daily",
                task_name="daily",
                path=Path("experiments/daily.toml"),
                config={"task": {"type": "daily"}},
            )
            with (
                patch("tdx_stocks.commands.run.load_run_config", return_value=loaded),
                patch("tdx_stocks.commands.run.build_run_plan", return_value={"plan": 1}),
                patch("tdx_stocks.commands.run.dispatch_run", return_value=result),
                patch("tdx_stocks.commands.run.build_latest_run_report", return_value={"status": "success"}),
                patch("tdx_stocks.commands.run.save_latest_run_report"),
                patch("tdx_stocks.commands.run.ensure_run_report_markdown") as mocked_save_md,
                patch("tdx_stocks.reports.opening.open_file") as mocked_open,
            ):
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["run", "daily", "--no-open"])
                self.assertEqual(code, 0)
                self.assertIn("Report:", stdout.getvalue())
                mocked_save_md.assert_not_called()
                mocked_open.assert_not_called()

                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    code = cli_main(["run", "daily", "--json"])
                self.assertEqual(code, 0)
                self.assertNotIn("Report:", stdout.getvalue())
                mocked_open.assert_not_called()
