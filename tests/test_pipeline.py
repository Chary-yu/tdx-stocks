from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
import io
import contextlib
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import cmd_actions_status, cmd_build, cmd_rebuild, cmd_sync, cmd_update_actions
from tdx_stocks.config import AppConfig, BuildConfig, PathsConfig
from tdx_stocks.export_io import load_export_adjustment_factor_rows
from tdx_stocks.parquet_io import (
    adjustment_factors_schema,
    corporate_actions_schema,
    write_records_table,
)
from tdx_stocks.exit_codes import BuildCheckFailedError, NoDataError
from tdx_stocks.pipeline import CheckResult, _raise_on_errors, build_dataset, rebuild_dataset, update_actions
from tdx_stocks.sync import execute_sync
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
            "tdx_stocks.cli._write_lock",
            return_value=contextlib.nullcontext(),
        ) as mocked_lock, patch(
            "tdx_stocks.cli.build_dataset",
            return_value={"ok": True},
        ) as mocked_build:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_build(args), 0)
            mocked_lock.assert_called_once()
            self.assertTrue(callable(mocked_build.call_args.kwargs["progress"]))

        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli._write_lock",
            return_value=contextlib.nullcontext(),
        ) as mocked_lock, patch(
            "tdx_stocks.cli.rebuild_dataset",
            return_value={"ok": True},
        ) as mocked_rebuild:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_rebuild(args), 0)
            mocked_lock.assert_called_once()
            self.assertTrue(callable(mocked_rebuild.call_args.kwargs["progress"]))

    def test_build_dataset_raises_nodata_error_when_no_files_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=Path("/tmp/tdx_vipdoc"),
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )
            with patch("tdx_stocks.pipeline.iter_day_files", return_value=[]):
                with self.assertRaises(NoDataError):
                    build_dataset(config)

    def test_raise_on_errors_uses_build_check_failed_error(self) -> None:
        result = CheckResult(name="raw_daily", errors=["raw_daily has no rows"])
        with self.assertRaises(BuildCheckFailedError):
            _raise_on_errors([result])

    def test_update_actions_command_passes_progress(self) -> None:
        args = Namespace(
            config=None,
            source="local",
            input=None,
            dry_run=False,
        )
        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli._write_lock",
            return_value=contextlib.nullcontext(),
        ) as mocked_lock, patch(
            "tdx_stocks.cli.update_actions",
            return_value={"ok": True},
        ) as mocked_update:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_update_actions(args), 0)
            mocked_lock.assert_called_once()
            self.assertTrue(callable(mocked_update.call_args.kwargs["progress"]))
            self.assertEqual(mocked_update.call_args.kwargs["source"], "local")

    def test_update_actions_dry_run_skips_lock_and_report_write(self) -> None:
        args = Namespace(
            config=None,
            source="export",
            input=None,
            dry_run=True,
        )
        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli._write_lock"
        ) as mocked_lock, patch(
            "tdx_stocks.cli.update_actions",
            return_value={"ok": True},
        ) as mocked_update:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_update_actions(args), 0)
            mocked_lock.assert_not_called()
            self.assertEqual(mocked_update.call_args.kwargs["write_report"], False)

    def test_sync_dry_run_skips_lock_and_execution(self) -> None:
        args = Namespace(
            config=None,
            from_date=None,
            to_date=None,
            limit_symbols=None,
            overwrite_staging=False,
            dry_run=True,
            json=False,
        )
        from types import SimpleNamespace

        plan = SimpleNamespace(
            needs_write=True,
            to_dict=lambda: {"steps": [{"name": "data update", "reason": "export newer"}]},
        )
        with patch("builtins.print"), patch(
            "tdx_stocks.cli.load_config"
        ) as load_config, patch(
            "tdx_stocks.cli.build_sync_plan",
            return_value=plan,
        ) as mocked_plan, patch(
            "tdx_stocks.cli._write_lock"
        ) as mocked_lock, patch(
            "tdx_stocks.cli.update_actions"
        ) as mocked_update, patch(
            "tdx_stocks.cli.rebuild_dataset"
        ) as mocked_rebuild:
            load_config.return_value = AppConfig()
            self.assertEqual(cmd_sync(args), 0)
            mocked_plan.assert_called_once()
            mocked_lock.assert_not_called()
            mocked_update.assert_not_called()
            mocked_rebuild.assert_not_called()

    def test_execute_sync_calls_update_and_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / "Database"
            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=Path("/tmp/tdx_vipdoc"),
                    tdx_export=Path("/tmp/tdx_export"),
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )
            from types import SimpleNamespace

            plan = SimpleNamespace(to_dict=lambda: {"steps": []})
            with patch("tdx_stocks.sync.update_actions", return_value={"ok": True}) as mocked_update, patch(
                "tdx_stocks.sync.rebuild_dataset",
                return_value={"ok": True},
            ) as mocked_rebuild:
                result = execute_sync(
                    config,
                    plan,
                    from_date=None,
                    to_date=None,
                    limit_symbols=3,
                    overwrite_staging=True,
                    progress=None,
                )

            mocked_update.assert_called_once_with(
                config,
                source="export",
                input_path=config.paths.tdx_export,
                dry_run=False,
                progress=None,
                write_report=True,
            )
            mocked_rebuild.assert_called_once_with(
                config,
                from_date=None,
                to_date=None,
                limit_symbols=3,
                overwrite_staging=True,
                progress=None,
            )
            self.assertEqual(result.update_report, {"ok": True})
            self.assertEqual(result.build_report, {"ok": True})

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

    def test_update_actions_export_dry_run_reports_skipped_symbols(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vipdoc = root / "vipdoc"
            export_dir = root / "export"
            raw_file = vipdoc / "sh" / "lday" / "sh600000.day"
            matching_export_file = export_dir / "SH#600000.txt"
            skipped_export_file = export_dir / "SH#600001.txt"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            export_dir.mkdir(parents=True, exist_ok=True)

            raw_rows = [
                (20240102, 1000, 1100, 990, 1000, 1000000.0, 100000, 0),
                (20240103, 2000, 2100, 1980, 2000, 2000000.0, 120000, 0),
            ]
            with raw_file.open("wb") as handle:
                for row in raw_rows:
                    handle.write(DAY_RECORD.pack(*row))

            matching_export_file.write_text(
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
            skipped_export_file.write_text(
                "\n".join(
                    [
                        "600001 测试证券 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/02\t1.00\t1.10\t0.95\t1.00\t1000\t10000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=vipdoc,
                    tdx_export=export_dir,
                    data_root=root / "Database",
                ),
                build=BuildConfig(markets=("sh",), universe="ashare"),
            )

            report = update_actions(config, source="export", dry_run=True)

            cache_dir = config.paths.data_root / "cache" / "adjustment_factors"
            self.assertFalse(cache_dir.exists() and any(cache_dir.rglob("*.parquet")))
            self.assertTrue((config.paths.data_root / "cache" / "action_update_report.json").exists())
            self.assertTrue(report["dry_run"])
            self.assertEqual(report["adjustment_factors_rows"], 2)
            self.assertEqual(report["adjustment_factors_state"], "dry-run")
            nested_report = report["adjustment_factors_report"]
            self.assertIn("metrics", nested_report)
            self.assertIn("skipped_details", nested_report)
            self.assertEqual(nested_report["metrics"]["successful"], 1)
            self.assertGreaterEqual(nested_report["metrics"]["skipped"], 1)
            self.assertEqual(nested_report["metrics"]["bad_rows_dropped"], 0)
            self.assertEqual(nested_report["matched_symbols"], 1)
            self.assertGreaterEqual(nested_report["skipped_issue_count"], 1)
            self.assertTrue(
                any(
                    issue["reason"] == "missing_raw_file" and issue["symbol"] == "600001"
                    for issue in nested_report["issues_sample"]
                )
            )
            self.assertEqual(nested_report["matched_symbols_sample"][0]["skipped_rows"], 0)

    def test_actions_status_reports_cache_and_update_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "Database"
            cache_root = data_root / "cache"
            corporate_actions_dir = cache_root / "corporate_actions"
            adjustment_factors_dir = cache_root / "adjustment_factors"
            corporate_actions_dir.mkdir(parents=True, exist_ok=True)
            adjustment_factors_dir.mkdir(parents=True, exist_ok=True)

            write_records_table(
                corporate_actions_dir,
                corporate_actions_schema(),
                [
                    {
                        "market": "sh",
                        "symbol": "600000",
                        "ex_date": date(2024, 1, 2),
                        "category": 1,
                        "cash_dividend": 0.0,
                        "stock_dividend": 0.0,
                        "allotment_share": 0.0,
                        "allotment_price": 0.0,
                        "raw_c1": 0.0,
                        "raw_c2": 0.0,
                        "raw_c3": 0.0,
                        "raw_c4": 0.0,
                        "source": "manual",
                    }
                ],
            )
            write_records_table(
                adjustment_factors_dir,
                adjustment_factors_schema(),
                [
                    {
                        "market": "sh",
                        "symbol": "600000",
                        "trade_date": date(2024, 1, 2),
                        "start_date": date(2024, 1, 2),
                        "end_date": date(2024, 1, 2),
                        "qfq_factor": 1.0,
                        "hfq_factor": 1.0,
                        "source": "manual",
                    }
                ],
            )
            (cache_root / "action_update_report.json").write_text(
                """
                {
                  "generated_at": "2024-01-02T12:00:00",
                  "source": "export",
                  "dry_run": true,
                  "metrics": {
                    "total_scanned": 1,
                    "successful": 1,
                    "skipped": 0,
                    "bad_rows_dropped": 0,
                    "rows_generated": 1,
                    "date_range": {"min": "2024-01-02", "max": "2024-01-02"}
                  },
                  "adjustment_factors_state": "dry-run",
                  "corporate_actions_state": "unchanged",
                  "adjustment_factors_rows": 1,
                  "corporate_actions_rows": 0
                }
                """.strip(),
                encoding="utf-8",
            )

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=root / "vipdoc",
                    tdx_export=root / "export",
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )

            buf = io.StringIO()
            with patch("tdx_stocks.cli.load_config", return_value=config), contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_actions_status(Namespace(config=None, json=False)), 0)
            output = buf.getvalue()
            self.assertIn("corporate_actions.rows=1", output)
            self.assertIn("adjustment_factors.rows=1", output)
            self.assertIn("action_update_report.dry_run=True", output)
            self.assertIn("action_update_report.successful=1", output)
            self.assertIn("action_update_report.adjustment_factors_state=dry-run", output)

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
