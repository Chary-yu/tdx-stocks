from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tdx_stocks.config_validators import optional_str, validate_compression
from tdx_stocks.path_guard import resolve_reports_root


@pytest.mark.parametrize("compression", ["zstd", "ZSTD", "snappy", "gzip", "uncompressed"])
def test_accepts_allowed_compression(compression: str) -> None:
    assert validate_compression(compression) in {"ZSTD", "SNAPPY", "GZIP", "UNCOMPRESSED"}


@pytest.mark.parametrize("compression", ["", "brotli", "zstd); drop table; --"])
def test_rejects_invalid_compression(compression: str) -> None:
    with pytest.raises(ValueError):
        validate_compression(compression)


def test_optional_str_returns_none_for_empty_values() -> None:
    assert optional_str(None) is None
    assert optional_str("   ") is None
    assert optional_str("value") == "value"


def test_resolve_reports_root_blocks_escape() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "reports"
        base.mkdir()
        with pytest.raises(ValueError):
            resolve_reports_root(base, "../escape")


def test_resolve_reports_root_accepts_nested_subdir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "reports"
        target = base / "strategies" / "latest"
        target.mkdir(parents=True)
        resolved = resolve_reports_root(base, "strategies/latest")
        assert resolved == target.resolve()
