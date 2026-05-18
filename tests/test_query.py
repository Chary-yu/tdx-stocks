from __future__ import annotations

import statistics
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from tdx_stocks.duckdb_ops import build_factors
from tdx_stocks.factor_sql import build_factor_spec, factor_build_report, render_build_factors_sql
from tdx_stocks.query import (
    build_stock_sql,
    build_select_sql,
    ensure_read_only_sql,
    format_bytes,
    normalize_output_data,
    print_rows,
    register_query_macros,
    validate_table,
)

try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None


class QueryHelpersTest(unittest.TestCase):
    def test_validate_table(self) -> None:
        validate_table("raw_daily")
        with self.assertRaises(ValueError):
            validate_table("not_a_table")

    def test_format_bytes(self) -> None:
        self.assertEqual(format_bytes(512), "512 B")
        self.assertEqual(format_bytes(1536), "1.5 KB")

    def test_print_rows_empty(self) -> None:
        with patch("builtins.print") as mocked_print:
            print_rows(["a"], [])
        mocked_print.assert_called_once_with("(no rows)")

    def test_print_rows_formats_numbers(self) -> None:
        with patch("builtins.print") as mocked_print:
            print_rows(
                ["price", "volume", "amount"],
                [{"price": 101.239, "volume": 1234567, "amount": 987654321.0}],
            )
        rendered = "\n".join(call.args[0] for call in mocked_print.call_args_list)
        self.assertIn("101.24", rendered)
        self.assertIn("1.23M", rendered)
        self.assertIn("987.65M", rendered)

    def test_normalize_output_data_rounds_values(self) -> None:
        normalized = normalize_output_data(
            [{"price": 101.239, "volume": 1234567, "amount": 987654321.0}]
        )
        self.assertEqual(normalized[0]["price"], 101.24)
        self.assertEqual(normalized[0]["volume"], 1234567)
        self.assertEqual(normalized[0]["amount"], 987654321)

    def test_ensure_read_only_sql_rejects_write_statements(self) -> None:
        self.assertEqual(ensure_read_only_sql("SELECT 1"), "SELECT 1")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("CREATE TABLE demo(id INT)")
        with self.assertRaises(ValueError):
            ensure_read_only_sql("SELECT 1; DROP TABLE demo")

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_select_sql_rejects_unsafe_where_expression(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE raw_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE
                )
                """
            )
            with self.assertRaises(ValueError):
                build_select_sql(con, "raw_daily", where="1 = 1; DROP TABLE raw_daily")
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_register_query_macros_last_n_days(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE adj_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    adj_close DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO adj_daily VALUES
                    ('sh', '600519', DATE '2024-01-02', 100.0),
                    ('sh', '600519', DATE '2024-01-03', 101.0),
                    ('sh', '600519', DATE '2024-01-04', 102.0),
                    ('sz', '000001', DATE '2024-01-04', 10.0)
                """
            )
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    pct_chg DOUBLE
                )
                """
            )
            register_query_macros(con)

            rows = con.execute(
                """
                SELECT market, symbol, trade_date, adj_close
                FROM last_n_days('600519.SH', 2)
                """
            ).fetchall()

            self.assertEqual(
                rows,
                [
                    ("sh", "600519", date(2024, 1, 4), 102.0),
                    ("sh", "600519", date(2024, 1, 3), 101.0),
                ],
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_code('sh600519')").fetchone()[0],
                "600519",
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_market('600519.SH')").fetchone()[0],
                "sh",
            )
            self.assertEqual(
                con.execute("SELECT tdx_symbol_market('sh600519')").fetchone()[0],
                "sh",
            )
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_stock_sql_joins_daily_and_factors(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE raw_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume BIGINT,
                    amount DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO raw_daily VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, 100.0, 101.0,
                     99.0, 100.5, 1000, 100500.0),
                    ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0,
                     100.0, 101.5, 1100, 111650.0)
                """
            )
            con.execute(
                """
                CREATE TABLE adj_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    adj_open DOUBLE,
                    adj_high DOUBLE,
                    adj_low DOUBLE,
                    adj_close DOUBLE,
                    adj_factor DOUBLE,
                    volume BIGINT,
                    amount DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO adj_daily VALUES
                    ('sh', '600519', DATE '2024-01-03', 2024, 100.0, 101.0,
                     99.0, 100.5, 1.0, 1000, 100500.0),
                    ('sh', '600519', DATE '2024-01-04', 2024, 101.0, 102.0,
                     100.0, 101.5, 1.0, 1100, 111650.0)
                """
            )
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    pct_chg DOUBLE,
                    ret_1 DOUBLE,
                    ret_20 DOUBLE,
                    ma5 DOUBLE,
                    ma10 DOUBLE,
                    ma20 DOUBLE,
                    ma60 DOUBLE,
                    ma120 DOUBLE,
                    ma250 DOUBLE,
                    vol_ma5 DOUBLE,
                    vol_ma20 DOUBLE,
                    vol_20 DOUBLE,
                    high_20 DOUBLE,
                    low_20 DOUBLE,
                    range_20 DOUBLE,
                    dd_20 DOUBLE,
                    pos_20 DOUBLE,
                    atr_pct_14 DOUBLE,
                    bb_width_20 DOUBLE,
                    rsi_14 DOUBLE,
                    bias_20 DOUBLE,
                    plus_di_14 DOUBLE,
                    minus_di_14 DOUBLE,
                    adx_14 DOUBLE,
                    rsv_9 DOUBLE,
                    k_9 DOUBLE,
                    d_9 DOUBLE,
                    j_9 DOUBLE,
                    amount_ma20 DOUBLE,
                    amount_ma60 DOUBLE,
                    vol_ratio_20 DOUBLE,
                    macd_dif DOUBLE,
                    macd_dea DOUBLE,
                    macd_hist DOUBLE
                )
                """
            )
            factor_columns = [
                "market",
                "symbol",
                "trade_date",
                "trade_year",
                "pct_chg",
                "ret_1",
                "ret_20",
                "ma5",
                "ma10",
                "ma20",
                "ma60",
                "ma120",
                "ma250",
                "vol_ma5",
                "vol_ma20",
                "vol_20",
                "high_20",
                "low_20",
                "range_20",
                "dd_20",
                "pos_20",
                "atr_pct_14",
                "bb_width_20",
                "rsi_14",
                "bias_20",
                "plus_di_14",
                "minus_di_14",
                "adx_14",
                "rsv_9",
                "k_9",
                "d_9",
                "j_9",
                "amount_ma20",
                "amount_ma60",
                "vol_ratio_20",
                "macd_dif",
                "macd_dea",
                "macd_hist",
            ]
            factor_rows = [
                {
                    "market": "sh",
                    "symbol": "600519",
                    "trade_date": date(2024, 1, 3),
                    "trade_year": 2024,
                    "pct_chg": None,
                    "ret_1": None,
                    "ret_20": None,
                    "ma5": 100.5,
                    "ma10": 100.5,
                    "ma20": 100.5,
                    "ma60": 100.5,
                    "ma120": 100.5,
                    "ma250": 100.5,
                    "vol_ma5": 1000.0,
                    "vol_ma20": 1000.0,
                    "vol_20": None,
                    "high_20": 101.0,
                    "low_20": 99.0,
                    "range_20": 0.0202020202,
                    "dd_20": None,
                    "pos_20": None,
                    "atr_pct_14": None,
                    "bb_width_20": None,
                    "rsi_14": None,
                    "bias_20": None,
                    "plus_di_14": None,
                    "minus_di_14": None,
                    "adx_14": None,
                    "rsv_9": None,
                    "k_9": None,
                    "d_9": None,
                    "j_9": None,
                    "amount_ma20": None,
                    "amount_ma60": None,
                    "vol_ratio_20": None,
                    "macd_dif": 0.0,
                    "macd_dea": 0.0,
                    "macd_hist": 0.0,
                },
                {
                    "market": "sh",
                    "symbol": "600519",
                    "trade_date": date(2024, 1, 4),
                    "trade_year": 2024,
                    "pct_chg": 0.0099502488,
                    "ret_1": 0.0099502488,
                    "ret_20": 0.01,
                    "ma5": 101.0,
                    "ma10": 101.0,
                    "ma20": 101.0,
                    "ma60": 101.0,
                    "ma120": 101.0,
                    "ma250": 101.0,
                    "vol_ma5": 1100.0,
                    "vol_ma20": 1100.0,
                    "vol_20": 0.02,
                    "high_20": 102.0,
                    "low_20": 100.0,
                    "range_20": 0.02,
                    "dd_20": -0.0001,
                    "pos_20": 0.01,
                    "atr_pct_14": 0.02,
                    "bb_width_20": 55.0,
                    "rsi_14": 0.01,
                    "bias_20": 50.0,
                    "plus_di_14": 48.0,
                    "minus_di_14": 52.0,
                    "adx_14": 54.0,
                    "rsv_9": 54.0,
                    "k_9": 55.0,
                    "d_9": 56.0,
                    "j_9": 57.0,
                    "amount_ma20": 1100.0,
                    "amount_ma60": 1100.0,
                    "vol_ratio_20": 0.0,
                    "macd_dif": 0.02,
                    "macd_dea": 0.01,
                    "macd_hist": 0.01,
                },
            ]
            placeholders = ", ".join(["?"] * len(factor_columns))
            con.executemany(
                f"INSERT INTO factors VALUES ({placeholders})",
                [tuple(row[column] for column in factor_columns) for row in factor_rows],
            )
            register_query_macros(con)

            sql = build_stock_sql(con, "600519.SH", limit=1)
            result = con.execute(sql)
            row = result.fetchone()
            columns = [item[0] for item in result.description]
            row_map = dict(zip(columns, row, strict=True))

            self.assertEqual(
                columns[:5],
                ["market", "symbol", "trade_date", "trade_year", "open"],
            )
            self.assertEqual(row_map["market"], "sh")
            self.assertEqual(row_map["symbol"], "600519")
            self.assertEqual(row_map["trade_date"], date(2024, 1, 4))
            self.assertEqual(row_map["adj_close"], 101.5)
            self.assertEqual(row_map["pct_chg"], 0.0099502488)
            self.assertEqual(row_map["ret_1"], 0.0099502488)
            self.assertEqual(row_map["ret_20"], 0.01)
            self.assertEqual(row_map["ma120"], 101.0)
            self.assertEqual(row_map["macd_hist"], 0.01)
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_stock_sql_supports_adjust_modes(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT
                )
                """
            )
            sql_raw = build_stock_sql(con, "600519.SH", adjust="raw")
            sql_hfq = build_stock_sql(con, "600519.SH", adjust="hfq")
            self.assertIn("LEFT JOIN raw_daily AS adj", sql_raw)
            self.assertIn("LEFT JOIN hfq_daily AS adj", sql_hfq)
            self.assertIn("adj.open AS adj_open", sql_raw)
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_stock_sql_appends_dynamic_factor_columns(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
                """
                CREATE TABLE raw_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume BIGINT,
                    amount DOUBLE
                )
                """
            )
            con.execute(
                """
                CREATE TABLE adj_daily (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    adj_open DOUBLE,
                    adj_high DOUBLE,
                    adj_low DOUBLE,
                    adj_close DOUBLE,
                    adj_factor DOUBLE
                )
                """
            )
            con.execute(
                """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    trade_year BIGINT,
                    pct_chg DOUBLE,
                    ret_1 DOUBLE,
                    ret_20 DOUBLE,
                    ma5 DOUBLE,
                    ma10 DOUBLE,
                    ma20 DOUBLE,
                    ma60 DOUBLE,
                    ma120 DOUBLE,
                    ma250 DOUBLE,
                    vol_ma5 DOUBLE,
                    vol_ma20 DOUBLE,
                    vol_20 DOUBLE,
                    high_20 DOUBLE,
                    low_20 DOUBLE,
                    range_20 DOUBLE,
                    dd_20 DOUBLE,
                    pos_20 DOUBLE,
                    atr_pct_14 DOUBLE,
                    bb_width_20 DOUBLE,
                    rsi_14 DOUBLE,
                    bias_20 DOUBLE,
                    plus_di_14 DOUBLE,
                    minus_di_14 DOUBLE,
                    adx_14 DOUBLE,
                    rsv_9 DOUBLE,
                    k_9 DOUBLE,
                    d_9 DOUBLE,
                    j_9 DOUBLE,
                    amount_ma20 DOUBLE,
                    amount_ma60 DOUBLE,
                    vol_ratio_20 DOUBLE,
                    macd_dif DOUBLE,
                    macd_dea DOUBLE,
                    macd_hist DOUBLE,
                    ma7 DOUBLE,
                    ret_7 DOUBLE,
                    vol_ma7 DOUBLE,
                    vol_7 DOUBLE,
                    high_7 DOUBLE,
                    low_7 DOUBLE,
                    range_7 DOUBLE,
                    dd_7 DOUBLE,
                    pos_7 DOUBLE,
                    bias_7 DOUBLE
                )
                """
            )
            con.execute(
                """
                INSERT INTO raw_daily VALUES
                    ('sh', '600519', DATE '2024-01-04', 2024, 101, 102, 100, 101.5, 1100, 111650)
                """
            )
            con.execute(
                """
                INSERT INTO adj_daily VALUES
                    ('sh', '600519', DATE '2024-01-04', 2024, 101, 102, 100, 101.5, 1.0)
                """
            )
            con.execute(
                """
                INSERT INTO factors (
                    market, symbol, trade_date, trade_year,
                    pct_chg, ret_1, ret_20,
                    ma5, ma10, ma20, ma60, ma120, ma250,
                    vol_ma5, vol_ma20, vol_20,
                    high_20, low_20, range_20, dd_20, pos_20,
                    atr_pct_14, bb_width_20, rsi_14, bias_20,
                    plus_di_14, minus_di_14, adx_14,
                    rsv_9, k_9, d_9, j_9,
                    amount_ma20, amount_ma60, vol_ratio_20,
                    macd_dif, macd_dea, macd_hist,
                    ma7, ret_7, pos_7
                ) VALUES (
                    'sh', '600519', DATE '2024-01-04', 2024,
                    0.01, 0.01, 0.02,
                    101, 101, 101, 101, 101, 101,
                    1000, 1000, 0.02,
                    102, 100, 0.02, -0.01, 0.5,
                    0.03, 0.1, 60, 0.01,
                    48, 52, 54,
                    54, 55, 56, 57,
                    1100, 1200, 0.1,
                    0.02, 0.01, 0.01,
                    101.2, 0.02, 0.6
                )
                """
            )
            register_query_macros(con)

            sql = build_stock_sql(con, "600519.SH", limit=1)
            self.assertIn("factors.ma7", sql)
            self.assertIn("factors.ret_7", sql)
            self.assertIn("factors.vol_7", sql)
            self.assertIn("factors.pos_7", sql)
            self.assertIn("factors.macd_hist,\n    factors.ma7", sql)

            result = con.execute(sql)
            row = result.fetchone()
            columns = [item[0] for item in result.description]
            row_map = dict(zip(columns, row, strict=True))
            self.assertEqual(row_map["ma7"], 101.2)
            self.assertEqual(row_map["ret_7"], 0.02)
            self.assertEqual(row_map["pos_7"], 0.6)
        finally:
            con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_register_latest_views_allows_missing_optional_xsec_columns(self) -> None:
        from tdx_stocks.query import register_latest_views, table_column_names

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            data_root = root / "Database"
            factors_dir = data_root / "versions" / "run-1" / "parquet" / "factors"
            xsec_dir = data_root / "versions" / "run-1" / "parquet" / "factors_xsec"
            quality_dir = data_root / "versions" / "run-1" / "parquet" / "factors_quality"
            for directory in (factors_dir, xsec_dir, quality_dir):
                directory.mkdir(parents=True, exist_ok=True)

            writer = duckdb.connect(":memory:")
            try:
                writer.execute(
                    """
                    CREATE TABLE factors (
                        market VARCHAR,
                        symbol VARCHAR,
                        trade_date DATE,
                        trade_year BIGINT
                    )
                    """
                )
                writer.execute(
                    """
                    INSERT INTO factors VALUES ('sh', '600000', DATE '2024-01-04', 2024)
                    """
                )
                writer.execute(
                    f"COPY factors TO '{(factors_dir / 'data.parquet').as_posix()}' (FORMAT PARQUET)"
                )
                writer.execute(
                    """
                    CREATE TABLE factors_xsec (
                        market VARCHAR,
                        symbol VARCHAR,
                        trade_date DATE,
                        trade_year BIGINT,
                        rank_ret_20 BIGINT
                    )
                    """
                )
                writer.execute(
                    """
                    INSERT INTO factors_xsec VALUES ('sh', '600000', DATE '2024-01-04', 2024, 1)
                    """
                )
                writer.execute(
                    f"COPY factors_xsec TO '{(xsec_dir / 'data.parquet').as_posix()}' (FORMAT PARQUET)"
                )
                writer.execute(
                    """
                    CREATE TABLE factors_quality (
                        market VARCHAR,
                        symbol VARCHAR,
                        trade_date DATE,
                        trade_year BIGINT,
                        missing_price_flag BIGINT
                    )
                    """
                )
                writer.execute(
                    """
                    INSERT INTO factors_quality VALUES ('sh', '600000', DATE '2024-01-04', 2024, 0)
                    """
                )
                writer.execute(
                    f"COPY factors_quality TO '{(quality_dir / 'data.parquet').as_posix()}' (FORMAT PARQUET)"
                )
            finally:
                writer.close()

            con = duckdb.connect(":memory:")
            try:
                register_latest_views(
                    con,
                    {
                        "factors": factors_dir.as_posix(),
                        "factors_xsec": xsec_dir.as_posix(),
                        "factors_quality": quality_dir.as_posix(),
                    },
                )

                columns = table_column_names(con, "factor_full")
                self.assertIn("risk_score", columns)
                self.assertIn("atr_pct_14_pct_rank", columns)
                value = con.execute("SELECT atr_pct_14_pct_rank FROM factor_full WHERE symbol = '600000'").fetchone()[0]
                self.assertIsNone(value)
            finally:
                con.close()

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_factors_generates_core_indicators_and_kdj(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "adj_daily"
            output_dir = tmp_path / "factors"
            con = duckdb.connect(":memory:")
            try:
                input_rows = []
                for offset in range(25):
                    close = 10.0 + offset
                    input_rows.append(
                        (
                            "sh",
                            "600519",
                            date(2024, 1, 2 + offset),
                            2024,
                            close,
                            close + 1.0,
                            close - 1.0,
                            close,
                            1000,
                            1000.0 * close,
                            1.0,
                        )
                    )
                values_sql = ",\n".join(
                    (
                        f"    ('{market}', '{symbol}', DATE '{trade_date.isoformat()}', "
                        f"{trade_year}, {adj_open}, {adj_high}, {adj_low}, {adj_close}, "
                        f"{volume}, {amount}, {adj_factor})"
                    )
                    for (
                        market,
                        symbol,
                        trade_date,
                        trade_year,
                        adj_open,
                        adj_high,
                        adj_low,
                        adj_close,
                        volume,
                        amount,
                        adj_factor,
                    ) in input_rows
                )
                con.execute(
                    f"""
                    COPY (
                        SELECT *
                        FROM (
                            VALUES
{values_sql}
                        ) AS t(
                            market, symbol, trade_date, trade_year, adj_open, adj_high,
                            adj_low, adj_close, volume, amount, adj_factor
                        )
                    )
                    TO '{input_dir.as_posix()}'
                    (FORMAT PARQUET, PARTITION_BY (trade_year, market))
                    """
                )

                build_factors(con, input_dir, output_dir, "zstd")

                result_rows = con.execute(
                    f"""
                    SELECT
                        trade_date,
                        adj_close,
                        pct_chg,
                        ret_1,
                        ret_20,
                        ma20,
                        ma120,
                        vol_20,
                        vol_ma20,
                        range_20,
                        dd_20,
                        pos_20,
                        atr_14,
                        atr_pct_14,
                        bb_width_20,
                        rsi_14,
                        bias_20,
                        plus_di_14,
                        minus_di_14,
                        adx_14,
                        rsv_9,
                        k_9,
                        d_9,
                        j_9,
                        vol_ratio_20,
                        macd_dif,
                        macd_dea,
                        macd_hist
                    FROM read_parquet(
                        '{output_dir.as_posix()}/**/*.parquet',
                        hive_partitioning=true
                    )
                    ORDER BY trade_date
                    """
                ).fetchall()

                columns = [
                    "trade_date",
                    "adj_close",
                    "pct_chg",
                    "ret_1",
                    "ret_20",
                    "ma20",
                    "ma120",
                    "vol_20",
                    "vol_ma20",
                    "range_20",
                    "dd_20",
                    "pos_20",
                    "atr_14",
                    "atr_pct_14",
                    "bb_width_20",
                    "rsi_14",
                    "bias_20",
                    "plus_di_14",
                    "minus_di_14",
                    "adx_14",
                    "rsv_9",
                    "k_9",
                    "d_9",
                    "j_9",
                    "vol_ratio_20",
                    "macd_dif",
                    "macd_dea",
                    "macd_hist",
                ]
                row = dict(zip(columns, result_rows[-1], strict=True))
                closes = [10.0 + i for i in range(25)]
                pct_chgs = [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
                self.assertEqual(row["adj_close"], closes[-1])
                self.assertAlmostEqual(row["pct_chg"], closes[-1] / closes[-2] - 1, places=12)
                self.assertAlmostEqual(row["ret_1"], closes[-1] / closes[-2] - 1, places=12)
                self.assertAlmostEqual(row["ret_20"], closes[-1] / closes[-21] - 1, places=12)
                self.assertEqual(row["ma20"], sum(closes[-20:]) / 20)
                self.assertEqual(row["ma120"], sum(closes) / 25)
                self.assertAlmostEqual(row["vol_20"], statistics.stdev(pct_chgs[-20:]), places=12)
                self.assertEqual(row["vol_ma20"], 1000.0)
                self.assertAlmostEqual(
                    row["range_20"],
                    (closes[-1] + 1.0) / (closes[-20] - 1.0) - 1,
                    places=12,
                )
                self.assertAlmostEqual(row["dd_20"], closes[-1] / (closes[-1] + 1.0) - 1, places=12)
                self.assertAlmostEqual(
                    row["pos_20"],
                    (closes[-1] - (closes[-20] - 1.0))
                    / ((closes[-1] + 1.0) - (closes[-20] - 1.0)),
                    places=12,
                )
                self.assertEqual(row["atr_14"], 2.0)
                self.assertAlmostEqual(row["atr_pct_14"], 2.0 / closes[-1], places=12)

                window_closes = closes[-20:]
                ma20 = sum(window_closes) / 20
                std20 = statistics.stdev(window_closes)
                self.assertAlmostEqual(row["bb_width_20"], 4.0 * std20 / ma20, places=12)
                self.assertEqual(row["rsi_14"], 100.0)
                self.assertAlmostEqual(row["bias_20"], closes[-1] / ma20 - 1, places=12)
                self.assertEqual(row["plus_di_14"], 50.0)
                self.assertEqual(row["minus_di_14"], 0.0)
                self.assertEqual(row["adx_14"], 100.0)
                self.assertAlmostEqual(row["rsv_9"], 90.0, places=12)

                k = 50.0
                d = 50.0
                for _ in range(17):
                    k = (2.0 / 3.0) * k + (1.0 / 3.0) * 90.0
                    d = (2.0 / 3.0) * d + (1.0 / 3.0) * k
                j = 3.0 * k - 2.0 * d
                self.assertAlmostEqual(row["k_9"], k, places=12)
                self.assertAlmostEqual(row["d_9"], d, places=12)
                self.assertAlmostEqual(row["j_9"], j, places=12)
                self.assertEqual(row["vol_ratio_20"], 0.0)
                alpha12 = 2.0 / 13.0
                alpha26 = 2.0 / 27.0
                alpha9 = 2.0 / 10.0
                ema12 = closes[0]
                ema26 = closes[0]
                dea = 0.0
                dif = 0.0
                hist = 0.0
                for close in closes:
                    ema12 = alpha12 * close + (1.0 - alpha12) * ema12
                    ema26 = alpha26 * close + (1.0 - alpha26) * ema26
                    dif = ema12 - ema26
                    dea = alpha9 * dif + (1.0 - alpha9) * dea
                    hist = 2.0 * (dif - dea)
                self.assertAlmostEqual(row["macd_dif"], dif, places=12)
                self.assertAlmostEqual(row["macd_dea"], dea, places=12)
                self.assertAlmostEqual(row["macd_hist"], hist, places=12)
            finally:
                con.close()

    def test_render_build_factors_sql_clamps_adx(self) -> None:
        sql = render_build_factors_sql(Path("/tmp/in"), Path("/tmp/out"), "zstd")
        self.assertIn("ROUND(avg(dx_14)", sql)
        self.assertIn("least(100.0, greatest(0.0", sql)

    def test_render_build_factors_sql_adds_tradeability_flags_and_incremental_filter(self) -> None:
        sql = render_build_factors_sql(
            Path("/tmp/in"),
            Path("/tmp/out"),
            "zstd",
            from_date=date(2024, 1, 31),
            max_window_days=10,
        )
        self.assertIn("AS is_limit_up", sql)
        self.assertIn("AS is_limit_down", sql)
        self.assertIn("AS is_suspended", sql)
        self.assertIn("WHERE trade_date >= DATE '2024-01-21'", sql)
        self.assertIn("WHERE s.trade_date > DATE '2024-01-31'", sql)
        self.assertIn("APPEND", sql)

    def test_render_build_factors_sql_adds_configured_windows(self) -> None:
        spec = build_factor_spec((7, 30, 20))
        self.assertEqual(spec.configured_windows, (7, 20, 30))
        report = factor_build_report(spec)
        self.assertEqual(report["configured_windows"], [7, 20, 30])
        self.assertEqual(report["generated_ma_windows"], [5, 7, 10, 20, 30, 60, 120, 250])
        self.assertEqual(report["generated_ret_windows"], [1, 5, 7, 10, 20, 30, 60, 120, 250])
        self.assertEqual(report["generated_vol_windows"], [5, 7, 10, 20, 30, 60])
        self.assertEqual(report["generated_range_windows"], [7, 20, 30])
        self.assertEqual(report["generated_pos_windows"], [7, 20, 30, 60])
        self.assertEqual(report["generated_drawdown_windows"], [7, 20, 30, 60])
        sql = render_build_factors_sql(
            Path("/tmp/in"),
            Path("/tmp/out"),
            "zstd",
            factor_windows=(7, 30),
        )
        self.assertIn("AS ma7", sql)
        self.assertIn("AS ret_7", sql)
        self.assertIn("AS vol_7", sql)
        self.assertIn("AS pos_7", sql)
        self.assertIn("AS ma30", sql)
        self.assertIn("AS ret_30", sql)
        self.assertIn("AS pos_30", sql)
        self.assertNotIn("OVER (7)", sql)
        self.assertNotIn("OVER (30)", sql)
        self.assertIn("ROWS BETWEEN 6 PRECEDING AND CURRENT ROW", sql)
        self.assertIn("ROWS BETWEEN 29 PRECEDING AND CURRENT ROW", sql)

    @unittest.skipIf(duckdb is None, "duckdb is not installed")
    def test_build_factors_supports_configured_windows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            input_dir = tmp_path / "adj_daily"
            output_dir = tmp_path / "factors"
            con = duckdb.connect(":memory:")
            try:
                input_rows = []
                base_date = date(2024, 1, 2)
                for offset in range(40):
                    close = 20.0 + offset
                    input_rows.append(
                        (
                            "sh",
                            "600519",
                            base_date + timedelta(days=offset),
                            2024,
                            close,
                            close + 1.0,
                            close - 1.0,
                            close,
                            1000,
                            1000.0 * close,
                            1.0,
                        )
                    )
                values_sql = ",\n".join(
                    (
                        f"    ('{market}', '{symbol}', DATE '{trade_date.isoformat()}', "
                        f"{trade_year}, {adj_open}, {adj_high}, {adj_low}, {adj_close}, "
                        f"{volume}, {amount}, {adj_factor})"
                    )
                    for (
                        market,
                        symbol,
                        trade_date,
                        trade_year,
                        adj_open,
                        adj_high,
                        adj_low,
                        adj_close,
                        volume,
                        amount,
                        adj_factor,
                    ) in input_rows
                )
                con.execute(
                    f"""
                    COPY (
                        SELECT *
                        FROM (
                            VALUES
{values_sql}
                        ) AS t(
                            market, symbol, trade_date, trade_year, adj_open, adj_high,
                            adj_low, adj_close, volume, amount, adj_factor
                        )
                    )
                    TO '{input_dir.as_posix()}'
                    (FORMAT PARQUET, PARTITION_BY (trade_year, market))
                    """
                )

                build_factors(con, input_dir, output_dir, "zstd", factor_windows=(7, 30))

                row = con.execute(
                    f"""
                    SELECT ma7, ret_7, vol_7, pos_7, ma30, ret_30, vol_30, pos_30
                    FROM read_parquet(
                        '{output_dir.as_posix()}/**/*.parquet',
                        hive_partitioning=true
                    )
                    ORDER BY trade_date DESC
                    LIMIT 1
                    """
                ).fetchone()
                self.assertIsNotNone(row)
                self.assertEqual(len(row), 8)
                self.assertTrue(all(value is not None for value in row))
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
