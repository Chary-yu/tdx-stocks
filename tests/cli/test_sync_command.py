from __future__ import annotations

import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main as cli_main


class SyncCommandTest(unittest.TestCase):
    def test_sync_dry_run_and_full_flags_are_accepted(self) -> None:
        plan = SimpleNamespace(needs_write=True, to_dict=lambda: {"plan": "ok"})
        with patch("tdx_stocks.commands.sync.load_config", return_value=SimpleNamespace()), patch(
            "tdx_stocks.commands.sync.build_sync_plan",
            return_value=plan,
        ), patch("tdx_stocks.commands.sync.execute_sync", return_value=SimpleNamespace(update_report={}, build_report={})), patch(
            "tdx_stocks.commands.sync._write_lock",
            return_value=contextlib.nullcontext(),
        ):
            code = cli_main(["sync", "--dry-run"])
            self.assertEqual(code, 0)
            code = cli_main(["sync", "--full"])
            self.assertEqual(code, 0)

    def test_sync_forwards_range_and_limits(self) -> None:
        plan = SimpleNamespace(needs_write=True, to_dict=lambda: {"plan": "ok"})
        execution = SimpleNamespace(update_report={"updated": 1}, build_report={"built": 1})
        with (
            patch("tdx_stocks.commands.sync.load_config", return_value=SimpleNamespace()),
            patch("tdx_stocks.commands.sync.build_sync_plan", return_value=plan),
            patch("tdx_stocks.commands.sync.execute_sync", return_value=execution) as mocked_execute,
            patch("tdx_stocks.commands.sync._write_lock", return_value=contextlib.nullcontext()),
        ):
            code = cli_main(
                [
                    "sync",
                    "--from-date",
                    "2024-01-01",
                    "--to-date",
                    "2024-01-31",
                    "--limit-symbols",
                    "10",
                    "--overwrite-staging",
                ]
            )
        self.assertEqual(code, 0)
        mocked_execute.assert_called_once()

    def test_sync_missing_config_surfaces_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "missing.toml"
            with patch("tdx_stocks.commands.sync.load_config", side_effect=FileNotFoundError("missing config")):
                code = cli_main(["sync", "--config", config_path.as_posix()])
        self.assertEqual(code, 2)
