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

def _unregister_strategy(strategy_name: str) -> None:
    for key, definition in list(strategy_registry._REGISTRY.items()):
        if definition.name == strategy_name:
            strategy_registry._REGISTRY.pop(key, None)


if __name__ == "__main__":
    unittest.main()
