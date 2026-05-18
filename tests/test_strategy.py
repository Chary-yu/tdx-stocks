from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import build_parser, cmd_strategy_run, cmd_strategy_run_trend_strength
from tdx_stocks.config import AppConfig
from tdx_stocks.exit_codes import NoDataError
from tdx_stocks.strategies.scoring import build_trend_score_breakdown
from tdx_stocks.strategies.signals import (
    build_trend_risk_flags,
    build_trend_watch_plan,
    classify_trend_candidate,
)
from tdx_stocks.strategies.registry import get_strategy, list_strategies
from tdx_stocks.strategy import StrategyParams, StrategyReport, run_trend_strength_strategy

try:
    import duckdb
except ModuleNotFoundError:
    duckdb = None


@dataclass
class FakeContext:
    con: object
    manifest: dict
    closed: bool = False

    def close(self) -> None:
        self.closed = True
        self.con.close()


@unittest.skipIf(duckdb is None, "duckdb is not installed")
class StrategyLogicTest(unittest.TestCase):
    def setUp(self) -> None:
        self.con = duckdb.connect(":memory:")
        self._create_tables()
        self.manifest = {
            "run_id": "run-1",
            "summary": {
                "generated_at": "2026-05-16T16:18:59",
                "factor_version": "v1",
            },
        }

    def tearDown(self) -> None:
        self.con.close()

    def _create_tables(self) -> None:
        self.con.execute(
            """
                CREATE TABLE factors (
                    market VARCHAR,
                    symbol VARCHAR,
                    trade_date DATE,
                    adj_close DOUBLE,
                    ma5 DOUBLE,
                    ma20 DOUBLE,
                    ma60 DOUBLE,
                    ret_5 DOUBLE,
                    ret_20 DOUBLE,
                    ret_60 DOUBLE,
                    amount_ma20 DOUBLE,
                    pos_20 DOUBLE,
                    pos_60 DOUBLE,
                    dd_20 DOUBLE,
                    vol_ratio_20 DOUBLE,
                    rsi_14 DOUBLE,
                    atr_pct_14 DOUBLE,
                    vol_20 DOUBLE,
                    vol_60 DOUBLE,
                    high_20 DOUBLE,
                    low_20 DOUBLE
                )
                """
            )
        self.con.execute(
            """
            CREATE TABLE adj_daily (
                market VARCHAR,
                symbol VARCHAR,
                trade_date DATE
            )
            """
        )

    def _insert_rows(self, factors_rows: list[tuple], adj_rows: list[tuple]) -> None:
        self.con.executemany(
            """
            INSERT INTO factors (
                market, symbol, trade_date, adj_close, ma5, ma20, ma60,
                ret_5, ret_20, amount_ma20, pos_20, dd_20, vol_ratio_20,
                rsi_14, atr_pct_14, vol_20, high_20, low_20
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            factors_rows,
        )
        self.con.executemany(
            "INSERT INTO adj_daily VALUES (?, ?, ?)",
            adj_rows,
        )

    def _run(self, params: StrategyParams):
        fake_context = FakeContext(self.con, self.manifest)
        with patch("tdx_stocks.strategy.open_query_context", return_value=fake_context):
            return run_trend_strength_strategy(AppConfig(), params)

    def test_default_as_of_execute_date_and_summary_counts(self) -> None:
        self._insert_rows(
            [
                (
                    "sh",
                    "600000",
                    date(2024, 1, 4),
                    12.0,
                    11.0,
                    10.0,
                    9.0,
                    0.03,
                    0.12,
                    200_000_000.0,
                    0.90,
                    -0.01,
                    0.20,
                    60.0,
                    0.03,
                    0.02,
                    12.5,
                    9.5,
                ),
                (
                    "sh",
                    "600001",
                    date(2024, 1, 4),
                    10.5,
                    10.2,
                    10.0,
                    9.0,
                    0.00,
                    0.01,
                    50_000_000.0,
                    0.50,
                    -0.10,
                    0.10,
                    60.0,
                    0.03,
                    0.02,
                    11.0,
                    9.0,
                ),
            ],
            [
                ("sh", "600000", date(2024, 1, 4)),
                ("sh", "600000", date(2024, 1, 5)),
                ("sh", "600001", date(2024, 1, 4)),
                ("sh", "600001", date(2024, 1, 5)),
            ],
        )

        report = self._run(StrategyParams())

        self.assertEqual(report.summary["trade_date"], "2024-01-04")
        self.assertEqual(report.summary["execute_date"], "2024-01-05")
        self.assertEqual(report.summary["total_scanned"], 2)
        self.assertEqual(report.summary["eligible"], 2)
        self.assertEqual(report.summary["low_score_filtered"], 1)
        self.assertEqual(report.summary["picked"], 1)
        self.assertEqual(report.summary["excluded"], 0)
        self.assertEqual(report.summary["excluded_returned"], 0)
        self.assertEqual(
            report.summary["candidate_type_counts"],
            {"breakout_watch": 1, "strong_trend": 1},
        )
        self.assertEqual(report.picks[0]["display_symbol"], "600000.SH")
        self.assertEqual(report.picks[0]["rank"], 1)
        self.assertEqual(report.picks[0]["candidate_type"], "breakout_watch")
        self.assertEqual(report.explain, None)

    def test_as_of_warning_and_cross_market_explain(self) -> None:
        self._insert_rows(
            [
                (
                    "sh",
                    "600000",
                    date(2024, 1, 4),
                    12.0,
                    11.0,
                    10.0,
                    9.0,
                    0.03,
                    0.12,
                    200_000_000.0,
                    0.90,
                    -0.01,
                    0.20,
                    60.0,
                    0.03,
                    0.02,
                    12.5,
                    9.5,
                ),
                (
                    "sz",
                    "000001",
                    date(2024, 1, 4),
                    11.0,
                    10.5,
                    10.0,
                    9.5,
                    0.02,
                    0.10,
                    180_000_000.0,
                    0.88,
                    -0.02,
                    0.18,
                    62.0,
                    0.03,
                    0.02,
                    11.3,
                    9.4,
                ),
            ],
            [
                ("sh", "600000", date(2024, 1, 4)),
                ("sh", "600000", date(2024, 1, 5)),
                ("sz", "000001", date(2024, 1, 4)),
                ("sz", "000001", date(2024, 1, 5)),
            ],
        )

        report = self._run(
            StrategyParams(
                market="sh",
                as_of=date(2024, 1, 5),
                explain_symbol="000001.SZ",
            )
        )

        self.assertEqual(report.summary["trade_date"], "2024-01-04")
        self.assertEqual(report.summary["execute_date"], "2024-01-05")
        self.assertIn(
            "as_of date is not a trading date; using latest available trade_date <= as_of",
            report.summary["warnings"],
        )
        self.assertEqual(report.summary["markets"], ["sh"])
        self.assertEqual(report.explain["status"], "picked")
        self.assertEqual(report.explain["pick"]["display_symbol"], "000001.SZ")
        self.assertEqual(report.explain["pick"]["symbol"], "000001")

    def test_bj_market_only_scan(self) -> None:
        self._insert_rows(
            [
                (
                    "bj",
                    "830001",
                    date(2024, 1, 4),
                    6.0,
                    5.8,
                    5.5,
                    5.0,
                    0.02,
                    0.11,
                    200_000_000.0,
                    0.92,
                    -0.05,
                    0.16,
                    58.0,
                    0.04,
                    0.03,
                    6.2,
                    5.1,
                )
            ],
            [
                ("bj", "830001", date(2024, 1, 4)),
                ("bj", "830001", date(2024, 1, 5)),
            ],
        )

        report = self._run(StrategyParams(market="bj"))

        self.assertEqual(report.summary["markets"], ["bj"])
        self.assertEqual(report.summary["total_scanned"], 1)
        self.assertEqual(report.picks[0]["display_symbol"], "830001.BJ")

    def test_include_excluded_limit_and_sorting(self) -> None:
        self._insert_rows(
            [
                (
                    "sh",
                    "600000",
                    date(2024, 1, 4),
                    12.0,
                    11.0,
                    10.0,
                    9.0,
                    0.03,
                    0.12,
                    200_000_000.0,
                    0.90,
                    -0.01,
                    0.20,
                    60.0,
                    0.03,
                    0.02,
                    12.5,
                    9.5,
                ),
                (
                    "sh",
                    "600002",
                    date(2024, 1, 4),
                    8.0,
                    7.8,
                    7.5,
                    7.0,
                    0.01,
                    None,
                    100_000_000.0,
                    0.80,
                    -0.02,
                    0.10,
                    55.0,
                    0.04,
                    0.03,
                    8.2,
                    7.1,
                ),
                (
                    "sh",
                    "600003",
                    date(2024, 1, 4),
                    8.0,
                    7.8,
                    7.5,
                    7.0,
                    0.01,
                    0.11,
                    10_000_000.0,
                    0.80,
                    -0.02,
                    0.10,
                    55.0,
                    0.04,
                    0.03,
                    8.2,
                    7.1,
                ),
            ],
            [
                ("sh", "600000", date(2024, 1, 4)),
                ("sh", "600000", date(2024, 1, 5)),
                ("sh", "600002", date(2024, 1, 4)),
                ("sh", "600003", date(2024, 1, 4)),
            ],
        )

        report = self._run(
            StrategyParams(include_excluded=True, show_excluded_limit=1)
        )

        self.assertEqual(report.summary["excluded"], 2)
        self.assertEqual(report.summary["excluded_returned"], 1)
        self.assertEqual(len(report.excluded), 1)
        self.assertEqual(report.excluded[0]["excluded_reason"], "missing_required_factor")

    def test_no_available_trade_date_raises(self) -> None:
        self._insert_rows(
            [
                (
                    "sh",
                    "600000",
                    date(2024, 1, 4),
                    12.0,
                    11.0,
                    10.0,
                    9.0,
                    0.03,
                    0.12,
                    200_000_000.0,
                    0.90,
                    -0.01,
                    0.20,
                    60.0,
                    0.03,
                    0.02,
                    12.5,
                    9.5,
                )
            ],
            [("sh", "600000", date(2024, 1, 4))],
        )

        with self.assertRaises(NoDataError):
            self._run(StrategyParams(as_of=date(2024, 1, 1)))

    def test_signal_and_scoring_helpers(self) -> None:
        row = {
            "adj_close": 12.0,
            "ma20": 10.0,
            "ma60": 9.0,
            "ret_5": 0.03,
            "ret_20": 0.12,
            "ret_60": 0.18,
            "amount_ma20": 200_000_000.0,
            "pos_20": 0.9,
            "pos_60": 0.8,
            "dd_20": -0.01,
            "vol_ratio_20": 0.2,
            "rsi_14": 60.0,
            "atr_pct_14": 0.03,
            "vol_20": 0.02,
        }

        candidate_type, tags, reasons = classify_trend_candidate(row, StrategyParams())
        risk_flags = build_trend_risk_flags(row)
        score_breakdown = build_trend_score_breakdown(row, StrategyParams().min_amount_ma20, risk_flags)
        watch_plan = build_trend_watch_plan(candidate_type, risk_flags)

        self.assertEqual(candidate_type, "breakout_watch")
        self.assertIn("breakout_watch", tags)
        self.assertIn("趋势延续", reasons)
        self.assertIn("near_20d_high", risk_flags)
        self.assertIn("trend", score_breakdown)
        self.assertIn("突破", watch_plan)

    def _insert_strategy_row(self, row: dict[str, object], trade_date: date = date(2024, 1, 4)) -> None:
        self.con.execute(
            """
            INSERT INTO factors (
                market, symbol, trade_date, adj_close, ma5, ma20, ma60,
                ret_5, ret_20, ret_60, amount_ma20, pos_20, pos_60,
                dd_20, vol_ratio_20, rsi_14, atr_pct_14, vol_20, vol_60,
                high_20, low_20
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["market"],
                row["symbol"],
                trade_date,
                row["adj_close"],
                row["ma5"],
                row["ma20"],
                row["ma60"],
                row["ret_5"],
                row["ret_20"],
                row["ret_60"],
                row["amount_ma20"],
                row["pos_20"],
                row["pos_60"],
                row["dd_20"],
                row["vol_ratio_20"],
                row["rsi_14"],
                row["atr_pct_14"],
                row["vol_20"],
                row["vol_60"],
                row["high_20"],
                row["low_20"],
            ),
        )
        self.con.execute(
            "INSERT INTO adj_daily VALUES (?, ?, ?)",
            (row["market"], row["symbol"], trade_date),
        )
        self.con.execute(
            "INSERT INTO adj_daily VALUES (?, ?, ?)",
            (row["market"], row["symbol"], date(2024, 1, 5)),
        )

    def _run_preset(self, strategy_name: str, params: StrategyParams | None = None):
        fake_context = FakeContext(self.con, self.manifest)
        with patch("tdx_stocks.strategies.presets.trend_strength.open_query_context", return_value=fake_context):
            runner = get_strategy(strategy_name).runner
            return runner(AppConfig(), params or StrategyParams())

    def test_low_vol_breakout_preset_is_distinct(self) -> None:
        self._insert_strategy_row(
            {
                "market": "sh",
                "symbol": "600100",
                "adj_close": 12.0,
                "ma5": 11.7,
                "ma20": 11.0,
                "ma60": 10.2,
                "ret_5": 0.02,
                "ret_20": 0.11,
                "ret_60": 0.16,
                "amount_ma20": 220_000_000.0,
                "pos_20": 0.93,
                "pos_60": 0.88,
                "dd_20": -0.01,
                "vol_ratio_20": 0.28,
                "rsi_14": 62.0,
                "atr_pct_14": 0.03,
                "vol_20": 0.02,
                "vol_60": 0.025,
                "high_20": 12.2,
                "low_20": 10.8,
            }
        )

        report = self._run_preset("low-vol-breakout")

        self.assertEqual(report.summary["strategy"], "low-vol-breakout")
        self.assertEqual(report.picks[0]["candidate_type"], "breakout_watch")
        self.assertIn("low_volatility", report.picks[0]["tags"])
        self.assertIn("低波收敛", report.picks[0]["reasons"])

    def test_ma_pullback_preset_is_distinct(self) -> None:
        self._insert_strategy_row(
            {
                "market": "sh",
                "symbol": "600101",
                "adj_close": 10.1,
                "ma5": 10.0,
                "ma20": 10.0,
                "ma60": 9.5,
                "ret_5": 0.01,
                "ret_20": 0.06,
                "ret_60": 0.11,
                "amount_ma20": 160_000_000.0,
                "pos_20": 0.52,
                "pos_60": 0.61,
                "dd_20": -0.04,
                "vol_ratio_20": 0.08,
                "rsi_14": 58.0,
                "atr_pct_14": 0.025,
                "vol_20": 0.02,
                "vol_60": 0.021,
                "high_20": 10.8,
                "low_20": 9.7,
            }
        )

        report = self._run_preset("ma-pullback")

        self.assertEqual(report.summary["strategy"], "ma-pullback")
        self.assertEqual(report.picks[0]["candidate_type"], "pullback_watch")
        self.assertIn("回踩均线", report.picks[0]["reasons"])
        self.assertIn("ma_bullish", report.picks[0]["tags"])

    def test_relative_strength_preset_is_distinct(self) -> None:
        self._insert_strategy_row(
            {
                "market": "sh",
                "symbol": "600102",
                "adj_close": 13.0,
                "ma5": 12.5,
                "ma20": 11.8,
                "ma60": 10.9,
                "ret_5": 0.03,
                "ret_20": 0.14,
                "ret_60": 0.18,
                "amount_ma20": 180_000_000.0,
                "pos_20": 0.78,
                "pos_60": 0.76,
                "dd_20": -0.02,
                "vol_ratio_20": 0.12,
                "rsi_14": 64.0,
                "atr_pct_14": 0.03,
                "vol_20": 0.02,
                "vol_60": 0.02,
                "high_20": 13.2,
                "low_20": 11.5,
            }
        )

        report = self._run_preset("relative-strength")

        self.assertEqual(report.summary["strategy"], "relative-strength")
        self.assertEqual(report.picks[0]["candidate_type"], "strong_trend")
        self.assertIn("relative_strength", report.picks[0]["tags"])
        self.assertIn("20日动量强", report.picks[0]["reasons"])

    def test_volume_breakout_preset_is_distinct(self) -> None:
        self._insert_strategy_row(
            {
                "market": "sh",
                "symbol": "600103",
                "adj_close": 9.6,
                "ma5": 9.3,
                "ma20": 9.0,
                "ma60": 8.7,
                "ret_5": 0.04,
                "ret_20": 0.09,
                "ret_60": 0.12,
                "amount_ma20": 210_000_000.0,
                "pos_20": 0.91,
                "pos_60": 0.84,
                "dd_20": -0.01,
                "vol_ratio_20": 0.34,
                "rsi_14": 66.0,
                "atr_pct_14": 0.03,
                "vol_20": 0.025,
                "vol_60": 0.024,
                "high_20": 9.8,
                "low_20": 8.7,
            }
        )

        report = self._run_preset("volume-breakout")

        self.assertEqual(report.summary["strategy"], "volume-breakout")
        self.assertEqual(report.picks[0]["candidate_type"], "breakout_watch")
        self.assertIn("volume_breakout", report.picks[0]["tags"])
        self.assertIn("放量突破", report.picks[0]["reasons"])


class StrategyCliTest(unittest.TestCase):
    def test_parser_contains_strategy_list(self) -> None:
        args = build_parser().parse_args(["strategy", "list"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "list")

    def test_parser_contains_strategy_run(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "trend-strength", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "trend-strength")
        self.assertEqual(args.limit, 1)

    def test_strategy_registry_contains_trend_strength(self) -> None:
        names = [definition.name for definition in list_strategies()]
        self.assertEqual(
            names,
            [
                "low-vol-breakout",
                "ma-pullback",
                "relative-strength",
                "trend-strength",
                "volume-breakout",
            ],
        )
        self.assertEqual(get_strategy("trend-strength").name, "trend-strength")

    def test_strategy_registry_contains_low_vol_breakout(self) -> None:
        names = [definition.name for definition in list_strategies()]
        self.assertIn("low-vol-breakout", names)
        self.assertEqual(get_strategy("low-vol-breakout").name, "low-vol-breakout")

    def test_strategy_registry_contains_ma_pullback(self) -> None:
        names = [definition.name for definition in list_strategies()]
        self.assertIn("ma-pullback", names)
        self.assertEqual(get_strategy("ma-pullback").name, "ma-pullback")

    def test_strategy_registry_contains_relative_strength(self) -> None:
        names = [definition.name for definition in list_strategies()]
        self.assertIn("relative-strength", names)
        self.assertEqual(get_strategy("relative-strength").name, "relative-strength")

    def test_strategy_registry_contains_volume_breakout(self) -> None:
        names = [definition.name for definition in list_strategies()]
        self.assertIn("volume-breakout", names)
        self.assertEqual(get_strategy("volume-breakout").name, "volume-breakout")

    def test_parser_contains_low_vol_breakout(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "low-vol-breakout", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "low-vol-breakout")
        self.assertEqual(args.limit, 1)

    def test_parser_contains_ma_pullback(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "ma-pullback", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "ma-pullback")
        self.assertEqual(args.limit, 1)

    def test_parser_contains_relative_strength(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "relative-strength", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "relative-strength")
        self.assertEqual(args.limit, 1)

    def test_parser_contains_volume_breakout(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "volume-breakout", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "volume-breakout")
        self.assertEqual(args.limit, 1)

    def test_command_writes_json_and_keeps_stdout_table(self) -> None:
        report = StrategyReport(
            summary={"strategy": "trend-strength", "picked": 1, "excluded_returned": 0},
            picks=[
                {
                    "trade_date": "2024-01-04",
                    "execute_date": "2024-01-05",
                    "market": "sh",
                    "symbol": "600000",
                    "display_symbol": "600000.SH",
                    "score": 88.5,
                    "score_breakdown": {"trend": 35.0},
                    "rank": 1,
                    "candidate_type": "breakout_watch",
                    "tags": ["breakout_watch", "trend_strong"],
                    "priority_weight": 0.885,
                    "reasons": ["趋势延续"],
                    "risk_flags": ["ret_5_strong"],
                    "watch_plan": "watch plan",
                    "dataset_run_id": "run-1",
                    "factor_version": "v1",
                    "excluded": False,
                    "excluded_reason": None,
                }
            ],
            excluded=[],
            explain=None,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "strategy.json"
            args = SimpleNamespace(
                config=None,
                limit=1,
                json=False,
                as_of=None,
                market=None,
                min_amount_ma20=50_000_000.0,
                min_score=60.0,
                candidate_type=None,
                include_excluded=False,
                show_excluded_limit=20,
                explain_symbol=None,
                to=output_path,
            )
            with patch("tdx_stocks.cli.load_config", return_value=AppConfig()):
                with patch("tdx_stocks.cli.run_trend_strength_strategy", return_value=report):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        cmd_strategy_run_trend_strength(args)

            self.assertIn("rank", stdout.getvalue())
            self.assertTrue(output_path.exists())
            payload = output_path.read_text(encoding="utf-8")
            self.assertIn('"strategy": "trend-strength"', payload)
            self.assertIn('"display_symbol": "600000.SH"', payload)

    def test_command_json_output_uses_report_structure(self) -> None:
        report = StrategyReport(
            summary={"strategy": "trend-strength", "picked": 1, "excluded_returned": 1},
            picks=[],
            excluded=[
                {
                    "trade_date": "2024-01-04",
                    "execute_date": "2024-01-05",
                    "market": "sh",
                    "symbol": "600001",
                    "display_symbol": "600001.SH",
                    "score": None,
                    "score_breakdown": None,
                    "candidate_type": None,
                    "tags": [],
                    "priority_weight": None,
                    "reasons": [],
                    "risk_flags": [],
                    "watch_plan": "watch plan",
                    "dataset_run_id": "run-1",
                    "factor_version": "v1",
                    "excluded": True,
                    "excluded_reason": "missing_required_factor",
                }
            ],
            explain={"status": "picked"},
        )
        args = SimpleNamespace(
            config=None,
            limit=1,
            json=True,
            as_of=None,
            market=None,
            min_amount_ma20=50_000_000.0,
            min_score=60.0,
            candidate_type=None,
            include_excluded=True,
            show_excluded_limit=1,
            explain_symbol=None,
            to=None,
        )
        with patch("tdx_stocks.cli.load_config", return_value=AppConfig()):
            with patch("tdx_stocks.cli.run_trend_strength_strategy", return_value=report):
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    cmd_strategy_run_trend_strength(args)

        rendered = stdout.getvalue()
        self.assertIn('"summary"', rendered)
        self.assertIn('"excluded"', rendered)
        self.assertIn('"explain"', rendered)

    def test_generic_strategy_run_uses_registry_runner(self) -> None:
        report = StrategyReport(
            summary={"strategy": "trend-strength", "picked": 1, "excluded_returned": 0},
            picks=[
                {
                    "trade_date": "2024-01-04",
                    "execute_date": "2024-01-05",
                    "market": "sh",
                    "symbol": "600000",
                    "display_symbol": "600000.SH",
                    "score": 88.5,
                    "score_breakdown": {"trend": 35.0},
                    "rank": 1,
                    "candidate_type": "breakout_watch",
                    "tags": ["breakout_watch", "trend_strong"],
                    "priority_weight": 0.885,
                    "reasons": ["趋势延续"],
                    "risk_flags": ["ret_5_strong"],
                    "watch_plan": "watch plan",
                    "dataset_run_id": "run-1",
                    "factor_version": "v1",
                    "excluded": False,
                    "excluded_reason": None,
                }
            ],
            excluded=[],
            explain=None,
        )
        args = SimpleNamespace(
            config=None,
            strategy_name="trend-strength",
            limit=1,
            json=False,
            as_of=None,
            market=None,
            min_amount_ma20=50_000_000.0,
            min_score=60.0,
            candidate_type=None,
            include_excluded=False,
            show_excluded_limit=20,
            explain_symbol=None,
            to=None,
        )
        with patch("tdx_stocks.cli.load_config", return_value=AppConfig()):
            with patch("tdx_stocks.strategies.registry.get_strategy") as get_strategy:
                get_strategy.return_value = SimpleNamespace(
                    name="trend-strength",
                    runner=lambda config, params: report,
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    cmd_strategy_run(args)

        self.assertIn("rank", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
