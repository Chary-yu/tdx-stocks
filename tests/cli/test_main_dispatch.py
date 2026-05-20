from __future__ import annotations

import contextlib
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import main
from tdx_stocks.exit_codes import UsageError


class MainDispatchTest(unittest.TestCase):
    def test_main_normal_return_and_usage_error(self) -> None:
        parser = SimpleNamespace(
            parse_args=lambda argv: SimpleNamespace(func=lambda args: 0),
        )
        with patch("tdx_stocks.cli.build_parser", return_value=parser):
            self.assertEqual(main(["status"]), 0)

        bad_parser = SimpleNamespace(parse_args=lambda argv: (_ for _ in ()).throw(UsageError("bad command")))
        with patch("tdx_stocks.cli.build_parser", return_value=bad_parser):
            self.assertEqual(main(["bad"]), 6)

    def test_main_handles_common_exceptions_and_debug_traceback(self) -> None:
        def make_parser(exc, *, debug: bool = False):
            return SimpleNamespace(
                parse_args=lambda argv: SimpleNamespace(debug=debug, func=lambda args: (_ for _ in ()).throw(exc))
            )

        for exc, code in (
            (FileNotFoundError("missing"), 2),
            (ValueError("bad"), 6),
            (RuntimeError("boom"), 1),
            (KeyboardInterrupt(), 130),
        ):
            with self.subTest(exc=exc):
                parser = make_parser(exc)
                with patch("tdx_stocks.cli.build_parser", return_value=parser):
                    stderr = io.StringIO()
                    with contextlib.redirect_stderr(stderr):
                        self.assertEqual(main(["status"]), code)

        parser = make_parser(RuntimeError("boom"), debug=True)
        with patch("tdx_stocks.cli.build_parser", return_value=parser):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["status", "--debug"]), 1)
            self.assertIn("Traceback", stderr.getvalue())

    def test_main_triggers_plugin_loading(self) -> None:
        parser = SimpleNamespace(parse_args=lambda argv: SimpleNamespace(func=lambda args: 0))
        with patch("tdx_stocks.cli.build_parser", return_value=parser), patch("tdx_stocks.cli._load_plugins_for_argv") as mocked:
            with patch.dict("os.environ", {"TDX_STOCKS_ENABLE_PLUGINS": "1"}):
                self.assertEqual(main(["status"]), 0)
        mocked.assert_called_once()
