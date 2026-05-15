from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            )


if __name__ == "__main__":
    unittest.main()
