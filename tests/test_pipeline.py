from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import cmd_build, cmd_rebuild, cmd_update_actions
from tdx_stocks.config import AppConfig, BuildConfig, PathsConfig
from tdx_stocks.pipeline import rebuild_dataset


class PipelineTest(unittest.TestCase):
    def test_rebuild_dataset_clears_database_before_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            nested_file = data_root / "versions" / "old" / "marker.txt"
            nested_file.parent.mkdir(parents=True, exist_ok=True)
            nested_file.write_text("old", encoding="utf-8")

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=Path("/tmp/tdx_vipdoc"),
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )

            with patch("tdx_stocks.pipeline.build_dataset", return_value={"ok": True}) as mocked:
                report = rebuild_dataset(
                    config,
                    from_date=None,
                    to_date=None,
                    limit_symbols=3,
                    overwrite_staging=True,
                )

            self.assertEqual(report, {"ok": True})
            self.assertFalse(data_root.exists())
            mocked.assert_called_once_with(
                config,
                from_date=None,
                to_date=None,
                limit_symbols=3,
                overwrite_staging=True,
                progress=None,
            )

    def test_build_and_rebuild_commands_pass_progress(self) -> None:
        args = Namespace(
            config=None,
            from_date=None,
            to_date=None,
            limit_symbols=None,
            overwrite_staging=False,
        )
        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli.build_dataset",
            return_value={"ok": True},
        ) as mocked_build:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_build(args), 0)
            self.assertTrue(callable(mocked_build.call_args.kwargs["progress"]))

        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli.rebuild_dataset",
            return_value={"ok": True},
        ) as mocked_rebuild:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_rebuild(args), 0)
            self.assertTrue(callable(mocked_rebuild.call_args.kwargs["progress"]))

    def test_update_actions_command_passes_progress(self) -> None:
        args = Namespace(
            config=None,
            source="local",
            input=None,
        )
        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli.update_actions",
            return_value={"ok": True},
        ) as mocked_update:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_update_actions(args), 0)
            self.assertTrue(callable(mocked_update.call_args.kwargs["progress"]))
            self.assertEqual(mocked_update.call_args.kwargs["source"], "local")


if __name__ == "__main__":
    unittest.main()
