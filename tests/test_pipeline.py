from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import cmd_build, cmd_rebuild, cmd_update_actions
from tdx_stocks.config import AppConfig, BuildConfig, PathsConfig
from tdx_stocks.export_io import load_export_adjustment_factor_rows
from tdx_stocks.pipeline import rebuild_dataset
from tdx_stocks.tdx_day import DAY_RECORD


class PipelineTest(unittest.TestCase):
    def test_rebuild_dataset_preserves_cache_and_clears_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            cache_file = data_root / "cache" / "adjustment_factors" / "test.parquet"
            nested_file = data_root / "versions" / "old" / "marker.txt"
            staging_file = data_root / "_staging" / "old" / "marker.txt"
            latest_file = data_root / "latest.json"
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(b"fake parquet marker")
            nested_file.parent.mkdir(parents=True, exist_ok=True)
            nested_file.write_text("old", encoding="utf-8")
            staging_file.parent.mkdir(parents=True, exist_ok=True)
            staging_file.write_text("old", encoding="utf-8")
            latest_file.write_text("old", encoding="utf-8")

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
            self.assertTrue(cache_file.exists())
            self.assertFalse(nested_file.exists())
            self.assertFalse(latest_file.exists())
            staging_dir = data_root / "_staging"
            self.assertTrue(not staging_dir.exists() or not any(staging_dir.iterdir()))
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

    def test_export_source_derives_adjustment_factors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vipdoc = root / "vipdoc"
            export_dir = root / "export"
            raw_file = vipdoc / "sh" / "lday" / "sh600000.day"
            export_file = export_dir / "SH#600000.txt"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            export_dir.mkdir(parents=True, exist_ok=True)

            raw_rows = [
                (20240102, 1000, 1100, 990, 1000, 1000000.0, 100000, 0),
                (20240103, 2000, 2100, 1980, 2000, 2000000.0, 120000, 0),
            ]
            with raw_file.open("wb") as handle:
                for row in raw_rows:
                    handle.write(DAY_RECORD.pack(*row))

            export_file.write_text(
                "\n".join(
                    [
                        "600000 测试银行 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/02\t5.00\t5.50\t4.95\t5.00\t100000\t1000000.00",
                        "2024/01/03\t20.00\t21.00\t19.80\t20.00\t120000\t2000000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=vipdoc,
                    tdx_export=export_dir,
                ),
                build=BuildConfig(markets=("sh",), universe="ashare"),
            )

            rows = load_export_adjustment_factor_rows(
                export_dir,
                config.paths.tdx_vipdoc,
                markets=config.build.markets,
                universe=config.build.universe,
            )

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["trade_date"].isoformat(), "2024-01-02")
            self.assertEqual(rows[0]["qfq_factor"], 0.5)
            self.assertEqual(rows[0]["hfq_factor"], 1.0)
            self.assertEqual(rows[1]["trade_date"].isoformat(), "2024-01-03")
            self.assertEqual(rows[1]["qfq_factor"], 1.0)
            self.assertEqual(rows[1]["hfq_factor"], 2.0)

    def test_export_source_skips_nonpositive_export_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vipdoc = root / "vipdoc"
            export_dir = root / "export"
            raw_file = vipdoc / "sh" / "lday" / "sh600188.day"
            export_file = export_dir / "SH#600188.txt"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            export_dir.mkdir(parents=True, exist_ok=True)

            raw_rows = [
                (20201201, 1000, 1100, 990, 1000, 1000000.0, 100000, 0),
                (20201202, 2000, 2100, 1980, 2000, 2000000.0, 120000, 0),
                (20201203, 3000, 3100, 2980, 3000, 3000000.0, 140000, 0),
            ]
            with raw_file.open("wb") as handle:
                for row in raw_rows:
                    handle.write(DAY_RECORD.pack(*row))

            export_file.write_text(
                "\n".join(
                    [
                        "600188 测试证券 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2020/12/01\t-0.70\t-0.59\t-0.73\t-0.70\t100000\t1000000.00",
                        "2020/12/02\t0.60\t0.70\t0.50\t0.60\t120000\t2000000.00",
                        "2020/12/03\t0.90\t1.00\t0.80\t0.90\t140000\t3000000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            rows = load_export_adjustment_factor_rows(
                export_dir,
                vipdoc,
                markets=("sh",),
                universe="ashare",
            )

            self.assertEqual([row["trade_date"].isoformat() for row in rows], ["2020-12-02", "2020-12-03"])
            self.assertEqual(rows[-1]["qfq_factor"], 1.0)


if __name__ == "__main__":
    unittest.main()
