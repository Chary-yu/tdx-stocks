from __future__ import annotations

import importlib.util

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: marks tests that exercise CLI or workflow integration")
    config.addinivalue_line(
        "markers",
        "requires_pyarrow: marks tests that need pyarrow-backed parquet helpers",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if importlib.util.find_spec("pyarrow") is not None:
        return

    skip_pyarrow = pytest.mark.skip(reason="pyarrow is not installed")
    for item in items:
        if "requires_pyarrow" in item.keywords:
            item.add_marker(skip_pyarrow)

