from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _DummyMetricColumn:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def metric(self, *args, **kwargs):
        return None


class _FakeStreamlit(types.SimpleNamespace):
    def __init__(self) -> None:
        super().__init__()
        self.sidebar = _DummyContext()
        self.session_state = {}

    def set_page_config(self, *args, **kwargs):
        return None

    def cache_data(self, *args, **kwargs):
        def decorator(fn):
            return fn

        return decorator

    def title(self, *args, **kwargs):
        return None

    def caption(self, *args, **kwargs):
        return None

    def header(self, *args, **kwargs):
        return None

    def text_input(self, *args, **kwargs):
        return kwargs.get("value")

    def file_uploader(self, *args, **kwargs):
        return None

    def selectbox(self, label, options, *args, **kwargs):
        return options[0] if options else None

    def error(self, *args, **kwargs):
        return None

    def stop(self):
        raise SystemExit(0)

    def subheader(self, *args, **kwargs):
        return None

    def columns(self, spec):
        size = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [_DummyMetricColumn() for _ in range(size)]

    def plotly_chart(self, *args, **kwargs):
        return None

    def dataframe(self, *args, **kwargs):
        return None

    def info(self, *args, **kwargs):
        return None

    def tabs(self, labels):
        return [_DummyContext() for _ in labels]

    def json(self, *args, **kwargs):
        return None

    def write(self, *args, **kwargs):
        return None


def _fake_report() -> dict[str, object]:
    empty_df = pd.DataFrame()
    return {
        "summary": {},
        "params": {},
        "equity_df": empty_df,
        "periods_df": empty_df,
        "trades_df": empty_df,
        "candidates_df": empty_df,
        "monthly_df": empty_df,
        "strategy_name": "trend-strength",
        "schema_version": "backtest-report-v1",
        "source_path": "/tmp/report.json",
        "raw": {},
    }


def _load_app_module():
    fake_streamlit = _FakeStreamlit()
    if "streamlit" in sys.modules:
        del sys.modules["streamlit"]
    with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
        data_loader = importlib.import_module("tdx_stocks.web.data_loader")
        with patch.object(data_loader, "discover_report_files", return_value=[Path("/tmp/report.json")]), patch.object(
            data_loader,
            "load_backtest_report",
            return_value=_fake_report(),
        ):
            sys.modules.pop("tdx_stocks.web.app", None)
            return importlib.import_module("tdx_stocks.web.app")


class WebAppTest(unittest.TestCase):
    def test_format_pct_uses_na_for_missing_or_invalid_values(self) -> None:
        app = _load_app_module()
        self.assertEqual(app._format_pct(None), "N/A")
        self.assertEqual(app._format_pct("bad"), "N/A")
        self.assertEqual(app._format_pct(float("inf")), "N/A")
        self.assertEqual(app._format_pct(0.125), "12.50%")

    def test_load_uploaded_report_rejects_invalid_and_large_payloads(self) -> None:
        app = _load_app_module()

        class Upload:
            def __init__(self, payload: bytes) -> None:
                self._payload = payload

            def getvalue(self) -> bytes:
                return self._payload

        with self.assertRaisesRegex(ValueError, "valid JSON"):
            app._load_uploaded_report(Upload(b"not-json"))
        with self.assertRaisesRegex(ValueError, "non-empty JSON object"):
            app._load_uploaded_report(Upload(b"[]"))
        with self.assertRaisesRegex(ValueError, "too large"):
            app._load_uploaded_report(Upload(b'{"x":"' + (b"a" * 32) + b'"}'), max_bytes=10)
