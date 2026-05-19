from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.cli import cmd_verify_adjustment
from tdx_stocks.config import AppConfig, BuildConfig, PathsConfig
from tdx_stocks.export_io import read_export_records
from tdx_stocks.parquet_io import (
    adjustment_factors_schema,
    corporate_actions_schema,
    raw_daily_schema,
    write_empty_table,
)

try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None


class AdjustmentVerifyTest(unittest.TestCase):
    def test_read_export_records_supports_day_month_year_dates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            export_dir = Path(tmp)
            export_path = export_dir / "SH#600519.txt"
            export_path.write_text(
                "\n".join(
                    [
                        "600519 测试股票 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "02/01/2020\t100.00\t101.00\t99.00\t100.00\t1000\t100000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            records = list(read_export_records(export_path))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].trade_date.isoformat(), "2020-01-02")

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_verify_adjustment_reports_zero_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "Database"
            export_dir = root / "export"
            version_dir = data_root / "versions" / "run-1"
            parquet_dir = version_dir / "parquet"
            adj_dir = parquet_dir / "adj_daily"
            raw_dir = parquet_dir / "raw_daily"
            corporate_actions_dir = parquet_dir / "corporate_actions"
            adjustment_factors_dir = parquet_dir / "adjustment_factors"
            hfq_dir = parquet_dir / "hfq_daily"
            factors_dir = parquet_dir / "factors"
            for path in (
                adj_dir,
                raw_dir,
                corporate_actions_dir,
                adjustment_factors_dir,
                hfq_dir,
                factors_dir,
            ):
                path.mkdir(parents=True, exist_ok=True)

            _write_adj_daily(
                adj_dir,
                [
                    ("sh", "600519", "2024-01-02", 2024, 100.0, 101.0, 99.0, 100.0, 1000, 100000.0, 1.0),
                    ("sh", "600519", "2024-01-03", 2024, 101.0, 102.0, 100.0, 101.5, 1100, 111650.0, 1.0),
                ],
            )
            for root_path, schema in (
                (raw_dir, raw_daily_schema()),
                (corporate_actions_dir, corporate_actions_schema()),
                (adjustment_factors_dir, adjustment_factors_schema()),
                (hfq_dir, raw_daily_schema()),
                (factors_dir, raw_daily_schema()),
            ):
                write_empty_table(root_path, schema)

            (data_root / "latest.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "version_dir": version_dir.as_posix(),
                        "parquet_dir": parquet_dir.as_posix(),
                        "raw_daily": raw_dir.as_posix(),
                        "corporate_actions": corporate_actions_dir.as_posix(),
                        "adjustment_factors": adjustment_factors_dir.as_posix(),
                        "adj_daily": adj_dir.as_posix(),
                        "hfq_daily": hfq_dir.as_posix(),
                        "factors": factors_dir.as_posix(),
                        "report": (version_dir / "reports" / "build_report.json").as_posix(),
                        "summary": {},
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "SH#600519.txt").write_text(
                "\n".join(
                    [
                        "600519 测试股票 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/02\t100.00\t101.00\t99.00\t100.00\t1000\t100000.00",
                        "2024/01/03\t101.00\t102.00\t100.00\t101.50\t1100\t111650.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=root / "vipdoc",
                    tdx_export=export_dir,
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )

            buf = io.StringIO()
            args = Namespace(
                config=None,
                symbol="600519.SH",
                input=None,
                from_date=None,
                to_date=None,
                threshold=0.01,
                json=False,
            )
            with patch(
                "tdx_stocks.commands.audit.load_config",
                return_value=config,
            ), contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_verify_adjustment(args), 0)
            output = buf.getvalue()
            self.assertIn("ok=True", output)
            self.assertIn("max_abs_error=0.0", output)
            self.assertIn("mismatch_count=0", output)

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_verify_adjustment_reports_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_root = root / "Database"
            export_dir = root / "export"
            version_dir = data_root / "versions" / "run-1"
            parquet_dir = version_dir / "parquet"
            adj_dir = parquet_dir / "adj_daily"
            raw_dir = parquet_dir / "raw_daily"
            corporate_actions_dir = parquet_dir / "corporate_actions"
            adjustment_factors_dir = parquet_dir / "adjustment_factors"
            hfq_dir = parquet_dir / "hfq_daily"
            factors_dir = parquet_dir / "factors"
            for path in (
                adj_dir,
                raw_dir,
                corporate_actions_dir,
                adjustment_factors_dir,
                hfq_dir,
                factors_dir,
            ):
                path.mkdir(parents=True, exist_ok=True)

            _write_adj_daily(
                adj_dir,
                [
                    ("sh", "600519", "2024-01-02", 2024, 100.0, 101.0, 99.0, 100.0, 1000, 100000.0, 1.0),
                ],
            )
            for root_path, schema in (
                (raw_dir, raw_daily_schema()),
                (corporate_actions_dir, corporate_actions_schema()),
                (adjustment_factors_dir, adjustment_factors_schema()),
                (hfq_dir, raw_daily_schema()),
                (factors_dir, raw_daily_schema()),
            ):
                write_empty_table(root_path, schema)

            (data_root / "latest.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-1",
                        "version_dir": version_dir.as_posix(),
                        "parquet_dir": parquet_dir.as_posix(),
                        "raw_daily": raw_dir.as_posix(),
                        "corporate_actions": corporate_actions_dir.as_posix(),
                        "adjustment_factors": adjustment_factors_dir.as_posix(),
                        "adj_daily": adj_dir.as_posix(),
                        "hfq_daily": hfq_dir.as_posix(),
                        "factors": factors_dir.as_posix(),
                        "report": (version_dir / "reports" / "build_report.json").as_posix(),
                        "summary": {},
                    },
                    ensure_ascii=True,
                    indent=2,
                ),
                encoding="utf-8",
            )

            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "SH#600519.txt").write_text(
                "\n".join(
                    [
                        "600519 测试股票 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/02\t100.00\t101.00\t99.00\t100.05\t1000\t100000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )

            config = AppConfig(
                paths=PathsConfig(
                    tdx_vipdoc=root / "vipdoc",
                    tdx_export=export_dir,
                    data_root=data_root,
                ),
                build=BuildConfig(),
            )

            buf = io.StringIO()
            args = Namespace(
                config=None,
                symbol="600519.SH",
                input=None,
                from_date=None,
                to_date=None,
                threshold=0.01,
                json=False,
            )
            with patch(
                "tdx_stocks.commands.audit.load_config",
                return_value=config,
            ), contextlib.redirect_stdout(buf):
                self.assertEqual(cmd_verify_adjustment(args), 3)
            output = buf.getvalue()
            self.assertIn("ok=False", output)
            self.assertIn("mismatch_count=1", output)


def _write_adj_daily(root: Path, rows: list[tuple]) -> None:
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            """
            CREATE TABLE adj_input (
                market VARCHAR,
                symbol VARCHAR,
                trade_date DATE,
                trade_year INTEGER,
                adj_open DOUBLE,
                adj_high DOUBLE,
                adj_low DOUBLE,
                adj_close DOUBLE,
                volume BIGINT,
                amount DOUBLE,
                adj_factor DOUBLE
            )
            """
        )
        con.executemany("INSERT INTO adj_input VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        con.execute(
            f"""
            COPY adj_input
            TO '{root.as_posix()}'
            (FORMAT PARQUET, PARTITION_BY (trade_year, market), COMPRESSION ZSTD)
            """
        )
    finally:
        con.close()


if __name__ == "__main__":
    unittest.main()
