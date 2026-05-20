from __future__ import annotations

import contextlib
import io
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import main
from tdx_stocks.config import AppConfig, PathsConfig, load_config
from tdx_stocks.strategies import registry as strategy_registry
from tdx_stocks.strategies.registry import get_strategy, load_plugins


class StrategyPluginTest(unittest.TestCase):
    def test_load_plugins_registers_strategy_file(self) -> None:
        strategy_name = f"plugin-test-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "sample_plugin.py").write_text(
                f"""
from tdx_stocks.strategies.base import StrategyParams, StrategyReport
from tdx_stocks.strategies.registry import StrategyDefinition, register_strategy


def run_plugin_strategy(config, params):
    return StrategyReport(summary={{}}, picks=[], excluded=[], explain=None)


register_strategy(
    StrategyDefinition(
        name={strategy_name!r},
        description="Plugin test strategy.",
        runner=run_plugin_strategy,
        default_params=StrategyParams(),
    )
)
""",
                encoding="utf-8",
            )

            try:
                load_plugins(plugin_dir)
                self.assertEqual(get_strategy(strategy_name).name, strategy_name)
            finally:
                _unregister_strategy(strategy_name)

    def test_load_plugins_rejects_non_directory_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin_path = Path(tmp) / "plugin.py"
            plugin_path.write_text("pass", encoding="utf-8")

            with self.assertRaises(NotADirectoryError):
                load_plugins(plugin_path)

    def test_load_plugins_ignores_duplicate_loads(self) -> None:
        strategy_name = f"plugin-duplicate-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            (plugin_dir / "duplicate_plugin.py").write_text(
                f"""
from tdx_stocks.strategies.base import StrategyParams, StrategyReport
from tdx_stocks.strategies.registry import StrategyDefinition, register_strategy


def run_plugin_strategy(config, params):
    return StrategyReport(summary={{}}, picks=[], excluded=[], explain=None)


register_strategy(
    StrategyDefinition(
        name={strategy_name!r},
        description="Duplicate load test strategy.",
        runner=run_plugin_strategy,
        default_params=StrategyParams(),
    )
)
""",
                encoding="utf-8",
            )

            try:
                load_plugins(plugin_dir)
                first_definition = get_strategy(strategy_name)
                load_plugins(plugin_dir)
                second_definition = get_strategy(strategy_name)
                self.assertIs(first_definition, second_definition)
            finally:
                _unregister_strategy(strategy_name)

    def test_load_plugins_propagates_bad_plugin_and_allows_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp)
            bad_plugin = plugin_dir / "bad_plugin.py"
            bad_plugin.write_text("raise RuntimeError('boom')", encoding="utf-8")

            with self.assertRaises(RuntimeError):
                load_plugins(plugin_dir)
            with self.assertRaises(RuntimeError):
                load_plugins(plugin_dir)

    def test_config_loads_plugin_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "tdx_stocks.toml"
            plugin_dir = Path(tmp) / "plugins"
            config_path.write_text(
                f"""
[paths]
plugin_dir = "{plugin_dir.as_posix()}"
""",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.paths.plugin_dir, plugin_dir)
        self.assertIsInstance(AppConfig(paths=PathsConfig(plugin_dir=plugin_dir)), AppConfig)

    def test_main_help_does_not_load_plugins(self) -> None:
        with patch("tdx_stocks.cli.load_plugins") as mocked_load, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--help"]), 0)
        mocked_load.assert_not_called()

    def test_main_enable_plugins_loads_plugin_strategy(self) -> None:
        strategy_name = f"plugin-cli-test-{uuid.uuid4().hex}"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plugin_dir = root / "plugins"
            plugin_dir.mkdir(parents=True, exist_ok=True)
            (plugin_dir / "sample_plugin.py").write_text(
                f"""
from tdx_stocks.strategies.base import StrategyParams, StrategyReport
from tdx_stocks.strategies.registry import StrategyDefinition, register_strategy


def run_plugin_strategy(config, params):
    return StrategyReport(summary={{}}, picks=[], excluded=[], explain=None)


register_strategy(
    StrategyDefinition(
        name={strategy_name!r},
        description="Plugin test strategy.",
        runner=run_plugin_strategy,
        default_params=StrategyParams(),
    )
)
""",
                encoding="utf-8",
            )

            try:
                config = AppConfig(paths=PathsConfig(plugin_dir=plugin_dir))
                with patch("tdx_stocks.cli.AppConfig", return_value=config), contextlib.redirect_stdout(
                    io.StringIO()
                ), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["--enable-plugins", "strategy", "list", "--json"]), 0)
                self.assertEqual(get_strategy(strategy_name).name, strategy_name)
            finally:
                _unregister_strategy(strategy_name)

    def test_main_reports_plugin_load_root_cause(self) -> None:
        buffer = io.StringIO()
        with patch("tdx_stocks.cli.load_plugins", side_effect=RuntimeError("boom")):
            with contextlib.redirect_stderr(buffer):
                code = main(["--enable-plugins", "status"])

        self.assertEqual(code, 1)
        self.assertIn("RuntimeError: failed to load plugins: boom", buffer.getvalue())

    def test_main_reports_command_root_cause(self) -> None:
        buffer = io.StringIO()
        with patch("tdx_stocks.commands.status.cmd_status", side_effect=RuntimeError("kaboom")):
            with contextlib.redirect_stderr(buffer):
                code = main(["status"])

        self.assertEqual(code, 1)
        self.assertIn("RuntimeError: kaboom", buffer.getvalue())

def _unregister_strategy(strategy_name: str) -> None:
    for key, definition in list(strategy_registry._REGISTRY.items()):
        if definition.name == strategy_name:
            strategy_registry._REGISTRY.pop(key, None)


if __name__ == "__main__":
    unittest.main()
