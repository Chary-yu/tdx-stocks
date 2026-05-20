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

from tdx_stocks.backtest import (
    BacktestParams,
    PortfolioParams,
    run_backtest,
    run_portfolio_backtest,
)
from tdx_stocks.backtest.monte_carlo import run_monte_carlo_simulation
from tdx_stocks.backtest.prices import AdjDailyPrice, AdjOpenPrice
from tdx_stocks.backtest.research import (
    analyze_forward_returns,
    analyze_risk_tags,
    backtest_consensus,
    compare_backtests,
    tune_strategy_parameters,
)
from tdx_stocks.backtest.risk import check_exit_signal
from tdx_stocks.backtest.sizing import calc_target_shares
from tdx_stocks.backtest.validation import run_stress_test_suite, run_walk_forward_validation
from tdx_stocks.cli import build_parser, cmd_strategy_run, cmd_strategy_run_trend_strength
from tdx_stocks.commands.strategy import cmd_strategy_backtest
from tdx_stocks.config import AppConfig, PathsConfig
from tdx_stocks.exit_codes import NoDataError
from tdx_stocks.strategies.compare import compare_strategies
from tdx_stocks.strategies.consensus import build_consensus
from tdx_stocks.strategies.data import fetch_strategy_rows
from tdx_stocks.strategies.base import MultiFactorParams
from tdx_stocks.strategies.pairs import (
    PairsParams,
    _normalize_pair_symbol,
    _safe_in_list,
    run_pairs_strategy,
)
from tdx_stocks.strategies.registry import get_strategy, list_strategies
from tdx_stocks.strategies.storage import load_saved_report, save_report_document
from tdx_stocks.strategy import StrategyParams, StrategyReport, run_trend_strength_strategy

import pytest

duckdb = pytest.importorskip("duckdb")


@dataclass
class FakeContext:
    con: object
    manifest: dict
    closed: bool = False

    def close(self) -> None:
        self.closed = True
        self.con.close()


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

    def test_walk_forward_and_stress_validation_helpers(self) -> None:
        fake_report = SimpleNamespace(
            total_return=0.10,
            annual_return=0.10,
            max_drawdown=-0.02,
            win_rate=0.60,
            trade_count=1,
            period_count=1,
            equity_curve=[
                {"trade_date": "2021-01-01", "equity": 1.0},
                {"trade_date": "2021-01-02", "equity": 1.1},
            ],
            periods=[{"signal_date": "2021-01-01"}],
            trades=[{"net_return": 0.1}],
            to_dict=lambda: {},
        )

        def fake_run_backtest(_config, _strategy_name, _params, **_kwargs):
            return fake_report

        def fake_tune(_config, _strategy_name, _params, **_kwargs):
            return {
                "rows": [
                    {
                        "min_score": 60.0,
                        "top": 20,
                        "hold_days": 5,
                        "research_score": 1.0,
                    }
                ]
            }

        with patch("tdx_stocks.backtest.validation.run_backtest", side_effect=fake_run_backtest):
            with patch("tdx_stocks.backtest.research.tune_strategy_parameters", side_effect=fake_tune):
                walk = run_walk_forward_validation(
                    AppConfig(),
                    "trend-strength",
                    BacktestParams(from_date=date(2020, 1, 1), to_date=date(2021, 12, 31)),
                    train_years=1,
                    test_years=1,
                )
                stress = run_stress_test_suite(
                    AppConfig(),
                    "trend-strength",
                    BacktestParams(from_date=date(2020, 1, 1), to_date=date(2021, 12, 31)),
                    {"sample": ("2020-01-01", "2020-12-31")},
                )

        mc = run_monte_carlo_simulation(
            [
                {"net_return": 0.1},
                {"net_return": -0.05},
            ],
            1_000_000.0,
            iterations=32,
            seed=7,
        )

        self.assertEqual(walk["summary"]["phase_count"], 1)
        self.assertTrue(walk["equity_curve"])
        self.assertEqual(stress["rows"][0]["period"], "sample")
        self.assertIn("summary", mc)
        self.assertEqual(mc["trade_count"], 2)

    def test_pairs_strategy_emits_short_and_long_legs(self) -> None:
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS factors (
                market VARCHAR,
                symbol VARCHAR,
                trade_date DATE,
                adj_close DOUBLE
            )
            """
        )
        self.con.execute(
            """
            CREATE TABLE IF NOT EXISTS adj_daily (
                market VARCHAR,
                symbol VARCHAR,
                trade_date DATE
            )
            """
        )
        rows = [
            ("sh", "600000", date(2024, 1, 2), 10.0),
            ("sh", "600001", date(2024, 1, 2), 10.0),
            ("sh", "600000", date(2024, 1, 3), 20.0),
            ("sh", "600001", date(2024, 1, 3), 10.0),
        ]
        self.con.executemany("INSERT INTO factors (market, symbol, trade_date, adj_close) VALUES (?, ?, ?, ?)", rows)
        self.con.executemany(
            "INSERT INTO adj_daily VALUES (?, ?, ?)",
            [
                ("sh", "600000", date(2024, 1, 2)),
                ("sh", "600001", date(2024, 1, 2)),
                ("sh", "600000", date(2024, 1, 3)),
                ("sh", "600001", date(2024, 1, 3)),
            ],
        )

        fake_context = FakeContext(self.con, self.manifest)
        with patch("tdx_stocks.strategies.pairs.open_query_context", return_value=fake_context):
            report = run_pairs_strategy(
                AppConfig(),
                PairsParams(symbols=("600000", "600001"), lookback=2, zscore_threshold=0.5, max_pairs=1),
            )

        self.assertEqual(report.summary["picked"], 2)
        self.assertEqual(report.picks[0]["direction"], "SHORT")
        self.assertEqual(report.picks[1]["direction"], "LONG")

    def test_pairs_strategy_normalizes_and_validates_symbols(self) -> None:
        params = PairsParams(
            symbols=(
                _normalize_pair_symbol("600519.SH"),
                _normalize_pair_symbol("sh600519"),
                _normalize_pair_symbol("000001.SZ"),
            ),
            lookback=2,
            zscore_threshold=0.5,
            max_pairs=1,
        )
        self.assertEqual(params.symbols, ("600519", "600519", "000001"))
        self.assertEqual(_safe_in_list(("600519", "000001")), "'600519', '000001'")
        with self.assertRaisesRegex(ValueError, "invalid pairs strategy symbol"):
            _normalize_pair_symbol("600519; drop table factors")

    def test_pairs_strategy_build_params_normalizes_symbols(self) -> None:
        from tdx_stocks.strategies.pairs import _build_params

        args = SimpleNamespace(
            limit=20,
            min_score=60.0,
            min_amount_ma20=50_000_000.0,
            market=None,
            candidate_type=None,
            include_excluded=False,
            show_excluded_limit=20,
            explain_symbol=None,
            as_of=None,
            symbols="600519.SH,000001.SZ",
            lookback=20,
            zscore_threshold=2.0,
            max_pairs=10,
        )
        params = _build_params(args)
        self.assertEqual(params.symbols, ("600519", "000001"))

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
                "mean-reversion",
                "multi-factor",
                "pairs-arb",
                "relative-strength",
                "smart-money",
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

    def test_parser_contains_mean_reversion(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "mean-reversion", "--limit", "1"])
        self.assertEqual(args.strategy_name, "mean-reversion")

    def test_parser_contains_multi_factor(self) -> None:
        args = build_parser().parse_args(
            ["strategy", "run", "multi-factor", "--limit", "1", "--weight-mom", "0.5"]
        )
        self.assertEqual(args.strategy_name, "multi-factor")
        self.assertEqual(args.weight_mom, 0.5)

    def test_parser_contains_pairs_strategy(self) -> None:
        args = build_parser().parse_args(
            ["strategy", "run", "pairs-arb", "--limit", "1", "--symbols", "600000,600016"]
        )
        self.assertEqual(args.strategy_name, "pairs-arb")
        self.assertEqual(args.symbols, "600000,600016")

    def test_parser_contains_backtest_validation_flags(self) -> None:
        args = build_parser().parse_args(
            ["strategy", "backtest", "trend-strength", "--walk-forward", "--stress-test", "--monte-carlo"]
        )
        self.assertTrue(args.walk_forward)
        self.assertTrue(args.stress_test)
        self.assertTrue(args.monte_carlo)

    def test_backtest_stress_route_invokes_validation_suite(self) -> None:
        args = SimpleNamespace(
            config=None,
            strategy_name="trend-strength",
            from_date=None,
            to_date=None,
            top=20,
            hold_days=5,
            fee_rate=0.0,
            slippage=0.0,
            market=None,
            min_score=60.0,
            min_amount_ma20=50_000_000.0,
            candidate_type=None,
            format="table",
            json=False,
            output=None,
            stress_test=True,
            stress_period="all",
            walk_forward=False,
            monte_carlo=False,
            train_years=3,
            test_years=1,
            iterations=1000,
            seed=None,
        )
        with patch("tdx_stocks.commands.strategy.load_config", return_value=AppConfig()):
            with patch("tdx_stocks.commands.strategy.run_stress_test_suite", return_value={"rows": []}) as mocked:
                cmd_strategy_backtest(args)
        self.assertTrue(mocked.called)

    def test_parser_contains_volume_breakout(self) -> None:
        args = build_parser().parse_args(["strategy", "run", "volume-breakout", "--limit", "1"])
        self.assertEqual(args.command, "strategy")
        self.assertEqual(args.strategy_command, "run")
        self.assertEqual(args.strategy_name, "volume-breakout")
        self.assertEqual(args.limit, 1)

    def test_parser_contains_compare_consensus_backtest_reports(self) -> None:
        args = build_parser().parse_args(["strategy", "compare", "--strategies", "trend-strength,low-vol-breakout"])
        self.assertEqual(args.strategy_command, "compare")
        self.assertEqual(args.strategies, "trend-strength,low-vol-breakout")

        args = build_parser().parse_args(["strategy", "consensus", "--min-hit", "2"])
        self.assertEqual(args.strategy_command, "consensus")
        self.assertEqual(args.min_hit, 2)

        args = build_parser().parse_args(["strategy", "backtest", "trend-strength", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "backtest")
        self.assertEqual(args.strategy_name, "trend-strength")
        self.assertEqual(args.from_date, "2024-01-01")
        self.assertEqual(args.to_date, "2024-02-01")

        args = build_parser().parse_args(["strategy", "backtest-compare", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "backtest-compare")

        args = build_parser().parse_args(["strategy", "tune", "trend-strength", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "tune")

        args = build_parser().parse_args(["strategy", "analyze-forward-returns", "trend-strength", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "analyze-forward-returns")

        args = build_parser().parse_args(["strategy", "analyze-risk-tags", "trend-strength", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "analyze-risk-tags")

        args = build_parser().parse_args(["strategy", "backtest-consensus", "--from", "2024-01-01", "--to", "2024-02-01"])
        self.assertEqual(args.strategy_command, "backtest-consensus")

        args = build_parser().parse_args(["strategy", "reports", "list"])
        self.assertEqual(args.strategy_command, "reports")
        self.assertEqual(args.reports_command, "list")
        self.assertIsNone(args.config)

        args = build_parser().parse_args(["strategy", "reports", "list", "--config", "config/tdx_stocks.toml"])
        self.assertEqual(args.strategy_command, "reports")
        self.assertEqual(args.reports_command, "list")
        self.assertEqual(str(args.config), "config/tdx_stocks.toml")

        args = build_parser().parse_args(["strategy", "reports", "show", "trend-strength", "--as-of", "latest"])
        self.assertEqual(args.strategy_command, "reports")
        self.assertEqual(args.reports_command, "show")
        self.assertEqual(args.strategy_name, "trend-strength")
        self.assertEqual(args.as_of, "latest")

        args = build_parser().parse_args([
            "strategy",
            "reports",
            "show",
            "trend-strength",
            "--config",
            "config/tdx_stocks.toml",
            "--as-of",
            "latest",
        ])
        self.assertEqual(args.reports_command, "show")
        self.assertEqual(str(args.config), "config/tdx_stocks.toml")

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
            with patch("tdx_stocks.commands.strategy.load_config", return_value=AppConfig()):
                with patch("tdx_stocks.strategy.run_trend_strength_strategy", return_value=report):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        cmd_strategy_run_trend_strength(args)

            self.assertIn("排名", stdout.getvalue())
            self.assertTrue(output_path.exists())
            payload = output_path.read_text(encoding="utf-8")
            self.assertIn('"strategy": "trend-strength"', payload)
            self.assertIn('"display_symbol": "600000.SH"', payload)

    def test_command_table_localizes_fields_and_resolves_stock_name(self) -> None:
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
                    "tags": ["breakout_watch", "trend_strong", "near_20d_high", "active_amount"],
                    "priority_weight": 0.885,
                    "reasons": ["趋势延续"],
                    "risk_flags": ["ret_5_strong", "rsi_high"],
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
            export_dir = Path(tmpdir) / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "SH#600000.txt").write_text(
                "\n".join(
                    [
                        "600000 测试银行 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/04\t12.00\t12.50\t11.90\t12.30\t100000\t1230000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )
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
                to=None,
            )
            config = AppConfig(paths=PathsConfig(tdx_export=export_dir))
            with patch("tdx_stocks.commands.strategy.load_config", return_value=config):
                with patch("tdx_stocks.strategy.run_trend_strength_strategy", return_value=report):
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        cmd_strategy_run_trend_strength(args)

        rendered = stdout.getvalue()
        self.assertIn("名称", rendered)
        self.assertIn("测试银行", rendered)
        self.assertIn("突破观察", rendered)
        self.assertIn("趋势强", rendered)
        self.assertIn("近20日高位", rendered)
        self.assertIn("短线加速", rendered)
        self.assertIn("RSI偏高", rendered)

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
        with patch("tdx_stocks.commands.strategy.load_config", return_value=AppConfig()):
            with patch("tdx_stocks.strategy.run_trend_strength_strategy", return_value=report):
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
        with patch("tdx_stocks.commands.strategy.load_config", return_value=AppConfig()):
            with patch("tdx_stocks.strategies.registry.get_strategy") as get_strategy:
                get_strategy.return_value = SimpleNamespace(
                    name="trend-strength",
                    runner=lambda config, params: report,
                )
                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    cmd_strategy_run(args)

        self.assertIn("排名", stdout.getvalue())

    def test_missing_required_strategy_fields_raise_clear_error(self) -> None:
        con = duckdb.connect(":memory:")
        try:
            con.execute(
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
            with self.assertRaises(ValueError) as exc_info:
                fetch_strategy_rows(
                    con,
                    ("sh",),
                    date(2024, 1, 4),
                    required_fields=("ma120",),
                )
        finally:
            con.close()
        self.assertIn("strategy requires factors fields", str(exc_info.exception))
        self.assertIn("ma120", str(exc_info.exception))


class StrategyReportStorageTest(unittest.TestCase):
    def test_save_and_load_strategy_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            report = StrategyReport(
                summary={
                    "strategy": "trend-strength",
                    "trade_date": "2024-01-04",
                    "dataset_run_id": "run-1",
                    "factor_version": "v1",
                    "eligible": 1,
                    "excluded": 0,
                    "risk_flag_counts": {"ret_5_strong": 1},
                },
                picks=[
                    {
                        "market": "sh",
                        "symbol": "600000",
                        "display_symbol": "600000.SH",
                        "score": 88.5,
                        "candidate_type": "breakout_watch",
                        "tags": ["breakout_watch"],
                        "risk_flags": ["ret_5_strong"],
                        "watch_plan": "watch plan",
                    }
                ],
                excluded=[],
                explain=None,
            )
            document = save_report_document(
                data_root,
                "trend-strength",
                {
                    "schema_version": "strategy-report-v1",
                    "app_version": "0.1.0",
                    "strategy_name": "trend-strength",
                    "as_of": "2024-01-04",
                    "generated_at": "2024-01-05T09:00:00",
                    "data_run_id": "run-1",
                    "factor_version": "v1",
                    "params": StrategyParams(as_of=date(2024, 1, 4)).to_dict(),
                    "candidate_count": 1,
                    "excluded_count": 0,
                    "candidates": report.picks,
                    "excluded_summary": {"total": 0, "reasons": {}},
                    "risk_summary": {"ret_5_strong": 1},
                    "diagnostics": {"summary": report.summary, "explain": None},
                },
            )
            self.assertTrue((data_root / "reports" / "strategies" / "latest" / "trend-strength.json").exists())
            self.assertTrue((data_root / "reports" / "strategies" / "by_date" / "2024-01-04" / "trend-strength.json").exists())
            self.assertTrue((data_root / "reports" / "strategies" / "by_run_id" / "run-1" / "trend-strength.json").exists())
            loaded = load_saved_report(data_root, "trend-strength", as_of="2024-01-04")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["strategy_name"], "trend-strength")
            self.assertEqual(loaded["candidate_count"], 1)
            self.assertEqual(document["latest"], (data_root / "reports" / "strategies" / "latest" / "trend-strength.json").as_posix())

    def test_strategy_run_save_writes_all_report_copies(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            export_dir = Path(tmpdir) / "export"
            export_dir.mkdir(parents=True, exist_ok=True)
            (export_dir / "SH#600000.txt").write_text(
                "\n".join(
                    [
                        "600000 测试银行 日线 前复权",
                        "      日期\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额",
                        "2024/01/04\t12.00\t12.50\t11.90\t12.30\t100000\t1230000.00",
                    ]
                )
                + "\n",
                encoding="gbk",
            )
            report = StrategyReport(
                summary={
                    "strategy": "trend-strength",
                    "trade_date": "2024-01-04",
                    "dataset_run_id": "run-1",
                    "factor_version": "v1",
                    "eligible": 1,
                    "excluded": 0,
                    "risk_flag_counts": {"ret_5_strong": 1},
                },
                picks=[
                    {
                        "market": "sh",
                        "symbol": "600000",
                        "display_symbol": "600000.SH",
                        "score": 88.5,
                        "candidate_type": "breakout_watch",
                        "tags": ["breakout_watch"],
                        "risk_flags": ["ret_5_strong"],
                        "watch_plan": "watch plan",
                    }
                ],
                excluded=[],
                explain=None,
            )
            args = SimpleNamespace(
                config=None,
                limit=1,
                json=True,
                save=True,
                as_of=None,
                market=None,
                min_amount_ma20=50_000_000.0,
                min_score=60.0,
                candidate_type=None,
                include_excluded=False,
                show_excluded_limit=20,
                explain_symbol=None,
                to=None,
                strategy_name="trend-strength",
            )
            config = AppConfig(paths=PathsConfig(data_root=data_root, tdx_export=export_dir))
            with patch("tdx_stocks.commands.strategy.load_config", return_value=config):
                with patch("tdx_stocks.strategies.registry.get_strategy") as mocked_get_strategy:
                    mocked_get_strategy.return_value = SimpleNamespace(
                        name="trend-strength",
                        runner=lambda _config, _params: report,
                    )
                    stdout = io.StringIO()
                    with redirect_stdout(stdout):
                        cmd_strategy_run(args)

            self.assertTrue((data_root / "reports" / "strategies" / "latest" / "trend-strength.json").exists())
            self.assertTrue((data_root / "reports" / "strategies" / "by_date" / "2024-01-04" / "trend-strength.json").exists())
            self.assertTrue((data_root / "reports" / "strategies" / "by_run_id" / "run-1" / "trend-strength.json").exists())

    def test_compare_and_consensus_use_saved_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root))
            for strategy_name, score, symbol in (
                ("trend-strength", 90.0, "600000"),
                ("low-vol-breakout", 88.0, "600000"),
                ("ma-pullback", 80.0, "600001"),
            ):
                save_report_document(
                    data_root,
                    strategy_name,
                    {
                        "schema_version": "strategy-report-v1",
                        "app_version": "0.1.0",
                        "strategy_name": strategy_name,
                        "as_of": "2024-01-04",
                        "generated_at": "2024-01-05T09:00:00",
                        "data_run_id": "run-1",
                        "factor_version": "v1",
                        "params": {},
                        "candidate_count": 1,
                        "excluded_count": 0,
                        "candidates": [
                            {
                                "market": "sh",
                                "symbol": symbol,
                                "display_symbol": f"{symbol}.SH",
                                "score": score,
                                "candidate_type": "breakout_watch",
                                "tags": [strategy_name],
                                "risk_flags": ["ret_5_strong"] if strategy_name != "ma-pullback" else [],
                                "reasons": ["reason"],
                            }
                        ],
                        "excluded_summary": {"total": 0, "reasons": {}},
                        "risk_summary": {},
                        "diagnostics": {"summary": {}, "explain": None},
                    },
                )
            compare = compare_strategies(
                config,
                ["trend-strength", "low-vol-breakout", "ma-pullback"],
                as_of=None,
                use_saved_reports=True,
            )
            self.assertEqual(compare.strategies[0].candidate_count, 1)
            self.assertEqual(compare.overlaps[0]["overlap_count"], 1)
            self.assertEqual(compare.unique_stocks["trend-strength"], [])
            self.assertIn("600001.SH", compare.unique_stocks["ma-pullback"])
            consensus = build_consensus(
                config,
                ["trend-strength", "low-vol-breakout", "ma-pullback"],
                as_of=None,
                min_hit=2,
                use_saved_reports=True,
            )
            self.assertEqual(len(consensus.rows), 1)
            self.assertEqual(consensus.rows[0].symbol, "600000")
            self.assertEqual(consensus.rows[0].hit_count, 2)
            self.assertEqual(sorted(consensus.rows[0].strategies), ["low-vol-breakout", "trend-strength"])

    def test_compare_and_consensus_use_strategy_default_params(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root))
            candidate = {
                "market": "sh",
                "symbol": "600000",
                "display_symbol": "600000.SH",
                "score": 91.0,
                "candidate_type": "breakout_watch",
                "tags": ["multi-factor"],
                "risk_flags": [],
                "reasons": ["reason"],
                "risk_score": None,
            }
            report = SimpleNamespace(
                summary={"eligible": 1, "excluded": 0, "risk_flag_counts": {}},
                picks=[candidate],
                excluded=[],
                explain=None,
            )
            fake_definition = SimpleNamespace(
                default_params=MultiFactorParams(),
                runner=lambda _config, params: self.assertIsInstance(params, MultiFactorParams) or report,
            )
            with patch("tdx_stocks.strategies.compare.get_strategy", return_value=fake_definition):
                compare = compare_strategies(
                    config,
                    ["multi-factor"],
                    as_of=date(2024, 1, 4),
                    use_saved_reports=False,
                )
            with patch("tdx_stocks.strategies.consensus.get_strategy", return_value=fake_definition):
                consensus = build_consensus(
                    config,
                    ["multi-factor"],
                    as_of=date(2024, 1, 4),
                    min_hit=1,
                    use_saved_reports=False,
                )

        self.assertEqual(compare.strategies[0].candidate_count, 1)
        self.assertEqual(compare.strategies[0].strategy_name, "multi-factor")
        self.assertEqual(len(consensus.rows), 1)
        self.assertEqual(consensus.rows[0].symbol, "600000")
        self.assertEqual(consensus.rows[0].hit_count, 1)

    def test_backtest_mvp_returns_expected_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root))

            class FakeCon:
                def execute(self, sql: str, params=None):
                    if "SELECT DISTINCT trade_date" in sql:
                        return SimpleNamespace(fetchall=lambda: [(date(2024, 1, 2),), (date(2024, 1, 3),), (date(2024, 1, 4),), (date(2024, 1, 5),)])
                    if "FROM adj_daily" in sql:
                        market, symbol, trade_date = params
                        prices = {
                            ("sh", "600000", date(2024, 1, 3)): 10.0,
                            ("sh", "600000", date(2024, 1, 4)): 11.0,
                            ("sh", "600000", date(2024, 1, 5)): 12.0,
                        }
                        value = prices.get((market, symbol, trade_date))
                        return SimpleNamespace(fetchone=lambda: (value,) if value is not None else None)
                    raise AssertionError(sql)

            class FakeContext:
                def __init__(self) -> None:
                    self.con = FakeCon()
                    self.manifest = {"summary": {}}

                def close(self) -> None:
                    return None

            def fake_open_query_context(_config):
                return FakeContext()

            def fake_runner(_config, params):
                if params.as_of == date(2024, 1, 2):
                    return StrategyReport(
                        summary={"eligible": 1, "excluded": 0},
                        picks=[
                            {
                                "market": "sh",
                                "symbol": "600000",
                                "display_symbol": "600000.SH",
                                "score": 90.0,
                                "candidate_type": "breakout_watch",
                            }
                        ],
                        excluded=[],
                        explain=None,
                    )
                return StrategyReport(summary={"eligible": 0, "excluded": 0}, picks=[], excluded=[], explain=None)

            def fake_price_loader(con, market, symbol, trade_date):
                row = con.execute(
                    "SELECT adj_open FROM adj_daily WHERE market = ? AND symbol = ? AND trade_date = ?",
                    (market, symbol, trade_date),
                ).fetchone()
                return None if row is None else row[0]

            report = run_backtest(
                config,
                "trend-strength",
                BacktestParams(from_date=date(2024, 1, 2), to_date=date(2024, 1, 5), top=20, hold_days=1),
                open_query_context_fn=fake_open_query_context,
                strategy_runner_fn=fake_runner,
                price_loader_fn=fake_price_loader,
                trading_dates_fn=lambda con, from_date, to_date, market: [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)],
            )

            self.assertEqual(report.strategy_name, "trend-strength")
            self.assertEqual(report.trade_count, 1)
            self.assertGreater(report.total_return, 0.0)
            self.assertEqual(report.period_count, 4)
            self.assertEqual(report.empty_period_count, 3)

    def test_portfolio_sizing_and_stop_loss_helpers(self) -> None:
        params = PortfolioParams(initial_cash=1_000_000.0, max_positions=5, stop_loss_pct=0.08)
        self.assertEqual(calc_target_shares(available_cash=260_000.0, price=12.3, params=params), 16200)
        pos = SimpleNamespace(buy_price=10.0)
        self.assertEqual(check_exit_signal(pos, 9.3, params), None)
        self.assertEqual(check_exit_signal(pos, 9.0, params), "stop_loss")

    def test_portfolio_backtest_skips_limit_up_and_triggers_stop_loss(self) -> None:
        config = AppConfig()

        class FakeContext:
            con = object()
            manifest = {"summary": {}}

            def close(self) -> None:
                return None

        def fake_open_query_context(_config):
            return FakeContext()

        trading_dates = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
        ]

        def fake_runner(_config, params):
            if params.as_of == date(2024, 1, 2):
                return StrategyReport(
                    summary={},
                    picks=[
                        {
                            "market": "sh",
                            "symbol": "600000",
                            "display_symbol": "600000.SH",
                            "score": 88.0,
                            "candidate_type": "breakout_watch",
                        }
                    ],
                    excluded=[],
                    explain=None,
                )
            return StrategyReport(summary={}, picks=[], excluded=[], explain=None)

        prices = {
            ("sh", "600000", date(2024, 1, 3)): AdjDailyPrice(10.0, 10.0, 10.0, 10.0, is_limit_up=True),
            ("sh", "600000", date(2024, 1, 4)): AdjDailyPrice(9.0, 9.0, 9.0, 9.0),
        }

        def fake_daily_loader(_con, market, symbol, trade_date):
            return prices.get((market, symbol, trade_date))

        with patch("tdx_stocks.backtest.engine.load_adj_daily_price", side_effect=fake_daily_loader):
            report = run_backtest(
                config,
                "trend-strength",
                BacktestParams(
                    from_date=date(2024, 1, 2),
                    to_date=date(2024, 1, 5),
                    hold_days=5,
                    portfolio=PortfolioParams(initial_cash=1_000_000.0, max_positions=5, stop_loss_pct=0.08),
                ),
                open_query_context_fn=fake_open_query_context,
                strategy_runner_fn=fake_runner,
                trading_dates_fn=lambda con, from_date, to_date, market: trading_dates,
            )

        self.assertEqual(report.trade_count, 0)
        self.assertEqual(report.period_count, 4)
        self.assertIn("limit_up/suspended", report.periods[1]["skipped_reasons"])

        prices[("sh", "600000", date(2024, 1, 3))] = AdjDailyPrice(10.0, 10.0, 10.0, 10.0)
        report = run_portfolio_backtest(
            config,
            "trend-strength",
            BacktestParams(
                from_date=date(2024, 1, 2),
                to_date=date(2024, 1, 5),
                hold_days=5,
                portfolio=PortfolioParams(initial_cash=1_000_000.0, max_positions=5, stop_loss_pct=0.08),
            ),
            open_query_context_fn=fake_open_query_context,
            strategy_runner_fn=fake_runner,
            daily_price_loader_fn=fake_daily_loader,
            trading_dates_fn=lambda con, from_date, to_date, market: trading_dates,
        )
        self.assertEqual(report.trade_count, 1)
        self.assertEqual(report.total_return, pytest.approx(-0.02))
        self.assertEqual(report.trades[0]["sell_date"], "2024-01-04")
        self.assertEqual(report.trades[0]["gross_return"], pytest.approx(-0.1))
        self.assertEqual(report.trades[0]["shares"], 20000)

    def test_backtest_price_flags_skip_buy_and_delay_sell(self) -> None:
        config = AppConfig()

        class FakeContext:
            con = object()
            manifest = {"summary": {}}

            def close(self) -> None:
                return None

        def fake_open_query_context(_config):
            return FakeContext()

        def fake_runner(_config, params):
            if params.as_of == date(2024, 1, 2):
                return StrategyReport(
                    summary={"eligible": 1, "excluded": 0},
                    picks=[
                        {
                            "market": "sh",
                            "symbol": "600000",
                            "display_symbol": "600000.SH",
                            "score": 90.0,
                            "candidate_type": "breakout_watch",
                        }
                    ],
                    excluded=[],
                    explain=None,
                )
            return StrategyReport(summary={"eligible": 0, "excluded": 0}, picks=[], excluded=[], explain=None)

        trading_dates = [
            date(2024, 1, 2),
            date(2024, 1, 3),
            date(2024, 1, 4),
            date(2024, 1, 5),
            date(2024, 1, 6),
        ]

        def limit_up_loader(_con, _market, _symbol, trade_date):
            return {
                date(2024, 1, 3): AdjOpenPrice(10.0, is_limit_up=True),
                date(2024, 1, 4): AdjOpenPrice(11.0),
            }.get(trade_date)

        limit_up_report = run_backtest(
            config,
            "trend-strength",
            BacktestParams(from_date=trading_dates[0], to_date=trading_dates[-1], hold_days=1),
            open_query_context_fn=fake_open_query_context,
            strategy_runner_fn=fake_runner,
            price_loader_fn=limit_up_loader,
            trading_dates_fn=lambda con, from_date, to_date, market: trading_dates,
        )
        self.assertEqual(limit_up_report.trade_count, 0)
        self.assertEqual(limit_up_report.trades[0]["skipped_reason"], "limit_up/suspended")

        def limit_down_loader(_con, _market, _symbol, trade_date):
            return {
                date(2024, 1, 3): AdjOpenPrice(10.0),
                date(2024, 1, 4): AdjOpenPrice(9.0, is_limit_down=True),
                date(2024, 1, 5): AdjOpenPrice(12.0),
            }.get(trade_date)

        limit_down_report = run_backtest(
            config,
            "trend-strength",
            BacktestParams(from_date=trading_dates[0], to_date=trading_dates[-1], hold_days=1),
            open_query_context_fn=fake_open_query_context,
            strategy_runner_fn=fake_runner,
            price_loader_fn=limit_down_loader,
            trading_dates_fn=lambda con, from_date, to_date, market: trading_dates,
        )
        self.assertEqual(limit_down_report.trade_count, 1)
        self.assertEqual(limit_down_report.trades[0]["sell_date"], "2024-01-05")
        self.assertEqual(limit_down_report.trades[0]["gross_return"], pytest.approx(0.2))

        def short_loader(_con, _market, _symbol, trade_date):
            return {
                date(2024, 1, 3): AdjOpenPrice(10.0),
                date(2024, 1, 4): AdjOpenPrice(8.0),
            }.get(trade_date)

        def short_runner(_config, params):
            if params.as_of == date(2024, 1, 2):
                return StrategyReport(
                    summary={"eligible": 1, "excluded": 0},
                    picks=[
                        {
                            "market": "sh",
                            "symbol": "600001",
                            "display_symbol": "600001.SH",
                            "score": 88.0,
                            "candidate_type": "pair_short",
                            "direction": "SHORT",
                        }
                    ],
                    excluded=[],
                    explain=None,
                )
            return StrategyReport(summary={"eligible": 0, "excluded": 0}, picks=[], excluded=[], explain=None)

        short_report = run_backtest(
            config,
            "pairs-arb",
            BacktestParams(from_date=trading_dates[0], to_date=trading_dates[-1], hold_days=1),
            open_query_context_fn=fake_open_query_context,
            strategy_runner_fn=short_runner,
            price_loader_fn=short_loader,
            trading_dates_fn=lambda con, from_date, to_date, market: trading_dates,
        )
        self.assertEqual(short_report.trade_count, 1)
        self.assertEqual(short_report.trades[0]["direction"], "SHORT")
        self.assertGreater(short_report.trades[0]["net_return"], 0)

    def test_research_helpers_cover_compare_tune_forward_risk_and_consensus(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            data_root = Path(tmpdir) / "Database"
            config = AppConfig(paths=PathsConfig(data_root=data_root))
            con = duckdb.connect(":memory:")
            try:
                compare_reports = [
                    SimpleNamespace(
                        total_return=0.10,
                        annual_return=0.20,
                        max_drawdown=-0.05,
                        win_rate=0.60,
                        avg_period_return=0.01,
                        turnover=0.40,
                        period_count=10,
                        empty_period_count=1,
                    ),
                    SimpleNamespace(
                        total_return=0.15,
                        annual_return=0.25,
                        max_drawdown=-0.03,
                        win_rate=0.70,
                        avg_period_return=0.02,
                        turnover=0.50,
                        period_count=10,
                        empty_period_count=0,
                    ),
                ]
                with patch("tdx_stocks.backtest.research.run_backtest", side_effect=compare_reports * 3):
                    compare = compare_backtests(
                        config,
                        ["trend-strength", "low-vol-breakout"],
                        BacktestParams(from_date=date(2024, 1, 1), to_date=date(2024, 1, 31)),
                    )
                    self.assertEqual(compare["rows"][0]["strategy_name"], "low-vol-breakout")
                    tune = tune_strategy_parameters(
                        config,
                        "trend-strength",
                        BacktestParams(from_date=date(2024, 1, 1), to_date=date(2024, 1, 31)),
                        min_scores=[55.0, 60.0],
                        tops=[10],
                        hold_days=[5],
                    )
                    self.assertEqual(len(tune["rows"]), 2)
                    self.assertGreaterEqual(tune["rows"][0]["research_score"], tune["rows"][1]["research_score"])

                con.execute(
                    """
                    CREATE TABLE factors (
                        market VARCHAR,
                        symbol VARCHAR,
                        trade_date DATE
                    )
                    """
                )
                con.execute(
                    """
                    INSERT INTO factors VALUES
                        ('sh', '600000', DATE '2024-01-02'),
                        ('sh', '600000', DATE '2024-01-03'),
                        ('sh', '600000', DATE '2024-01-04'),
                        ('sh', '600000', DATE '2024-01-05')
                    """
                )
                con.execute(
                    """
                    CREATE TABLE adj_daily (
                        market VARCHAR,
                        symbol VARCHAR,
                        trade_date DATE,
                        adj_open DOUBLE
                    )
                    """
                )
                con.execute(
                    """
                    INSERT INTO adj_daily VALUES
                        ('sh', '600000', DATE '2024-01-03', 10.0),
                        ('sh', '600000', DATE '2024-01-04', 11.0),
                        ('sh', '600000', DATE '2024-01-05', 12.0)
                    """
                )

                class FakeContext:
                    def __init__(self, con):
                        self.con = con
                        self.manifest = {"summary": {}}

                    def close(self) -> None:
                        return None

                def fake_runner(_config, params):
                    if params.as_of == date(2024, 1, 2):
                        return StrategyReport(
                            summary={"eligible": 1, "excluded": 0},
                            picks=[
                                {
                                    "market": "sh",
                                    "symbol": "600000",
                                    "display_symbol": "600000.SH",
                                    "score": 90.0,
                                    "candidate_type": "breakout_watch",
                                    "tags": ["breakout_watch"],
                                    "risk_flags": ["rsi_high"],
                                    "reasons": ["reason"],
                                }
                            ],
                            excluded=[],
                            explain=None,
                        )
                    return StrategyReport(summary={"eligible": 0, "excluded": 0}, picks=[], excluded=[], explain=None)

                with patch("tdx_stocks.backtest.research.open_query_context", return_value=FakeContext(con)):
                    with patch(
                        "tdx_stocks.backtest.research.get_strategy",
                        side_effect=lambda _name: SimpleNamespace(runner=fake_runner),
                    ):
                        forward = analyze_forward_returns(
                            config,
                            "trend-strength",
                            BacktestParams(from_date=date(2024, 1, 2), to_date=date(2024, 1, 5), top=20),
                            horizons=[1, 2],
                        )
                        self.assertEqual([row["horizon"] for row in forward["rows"]], [1, 2])
                        self.assertGreaterEqual(forward["rows"][0]["sample_count"], 1)

                        risk = analyze_risk_tags(
                            config,
                            "trend-strength",
                            BacktestParams(from_date=date(2024, 1, 2), to_date=date(2024, 1, 5), top=20),
                            horizons=[1, 2],
                        )
                        self.assertTrue(any(row["risk_tag"] == "rsi_high" for row in risk["rows"]))

                        consensus = backtest_consensus(
                            config,
                            ["trend-strength", "low-vol-breakout"],
                            BacktestParams(from_date=date(2024, 1, 2), to_date=date(2024, 1, 5), top=20, hold_days=1),
                            min_hit=2,
                        )
                        self.assertEqual(consensus["trade_count"], 1)
                        self.assertEqual(consensus["period_count"], 4)
                        self.assertEqual(consensus["strategy_names"], ["trend-strength", "low-vol-breakout"])
            finally:
                con.close()


if __name__ == "__main__":
    unittest.main()
