from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tdx_stocks.cli import build_parser
from tdx_stocks.config import AppConfig
from tdx_stocks.portfolio import (
    Holding,
    build_portfolio,
    build_portfolio_weights,
    build_rebalance_plan,
    check_portfolio_risk,
    load_current_holdings_csv,
    run_portfolio_backtest,
)
from tdx_stocks.portfolio.models import PortfolioBacktestReport, RebalancePlan
from tdx_stocks.portfolio.store import save_portfolio_backtest_report, save_rebalance_plan
from tdx_stocks.strategies.base import StrategyParams


class PortfolioWeightsTest(unittest.TestCase):
    def test_equal_weights(self) -> None:
        weights = build_portfolio_weights([{"score": 1}, {"score": 2}], "equal", max_weight=0.8)
        self.assertAlmostEqual(sum(weights), 1.0)
        self.assertEqual(weights, [0.5, 0.5])

    def test_score_weights_fallback_to_equal_when_zero(self) -> None:
        weights = build_portfolio_weights([{"score": 0}, {"score": 0}], "score", max_weight=0.8)
        self.assertEqual(weights, [0.5, 0.5])

    def test_risk_adjusted_weights_degrade_without_risk_score(self) -> None:
        score_weights = build_portfolio_weights([{"score": 2}, {"score": 1}], "score", max_weight=0.8)
        risk_weights = build_portfolio_weights([{"score": 2}, {"score": 1}], "risk-adjusted", max_weight=0.8)
        self.assertEqual(score_weights, risk_weights)


class PortfolioRiskTest(unittest.TestCase):
    def test_risk_summary_counts(self) -> None:
        holdings = [
            Holding(
                market="sh",
                symbol="600000",
                weight=0.6,
                score=80,
                risk_flags=["risk_factor_missing"],
                factor_values={"amount_ma20": 10_000_000},
                risk_score=0.8,
            ),
            Holding(
                market="sz",
                symbol="000001",
                weight=0.4,
                score=70,
                risk_flags=[],
                factor_values={"amount_ma20": 100_000_000},
                risk_score=0.2,
            ),
        ]
        result = check_portfolio_risk(holdings, max_weight=0.5)
        self.assertFalse(result.passed)
        self.assertIn("单票权重超限", result.violations)
        self.assertGreater(result.summary["avg_risk_score"], 0.0)
        self.assertEqual(result.summary["low_liquidity_stock_count"], 1)


class PortfolioRebalanceTest(unittest.TestCase):
    def test_rebalance_actions(self) -> None:
        current = [
            Holding(market="sh", symbol="600000", weight=0.1),
            Holding(market="sz", symbol="000001", weight=0.2),
        ]
        target = [
            Holding(market="sh", symbol="600000", weight=0.15),
            Holding(market="sh", symbol="600010", weight=0.25),
        ]
        plan = build_rebalance_plan(current, target, as_of="2024-01-01", min_trade_weight=0.01)
        actions = {row["symbol"]: row["action"] for row in plan.weight_changes}
        self.assertEqual(actions["600000"], "INCREASE")
        self.assertEqual(actions["000001"], "SELL")
        self.assertEqual(actions["600010"], "BUY")

    def test_load_current_holdings_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "holdings.csv"
            path.write_text("market,symbol,weight\nsh,600000,0.05\n", encoding="utf-8")
            rows = load_current_holdings_csv(path)
        self.assertEqual(rows[0].symbol, "600000")
        self.assertAlmostEqual(rows[0].weight, 0.05)


class PortfolioBuilderTest(unittest.TestCase):
    def test_build_portfolio_from_strategy_filters_and_weights(self) -> None:
        report = SimpleNamespace(
            picks=[
                {"market": "sh", "symbol": "600000", "score": 90, "risk_score": 0.2, "risk_flags": [], "tags": ["trend"], "candidate_type": "strong_trend", "reason": "x", "factor_values": {"amount_ma20": 100}},
                {"market": "sz", "symbol": "000001", "score": 80, "risk_score": 0.9, "risk_flags": ["risk_factor_missing"], "tags": ["risk"], "candidate_type": "strong_trend", "reason": "y", "factor_values": {"amount_ma20": 50}},
                {"market": "sh", "symbol": "600010", "score": 70, "risk_score": 0.1, "risk_flags": [], "tags": ["trend"], "candidate_type": "pullback_watch", "reason": "z", "factor_values": {"amount_ma20": 120}},
            ],
            summary={"dataset_run_id": "run-1"},
        )
        with patch("tdx_stocks.portfolio.builder.get_strategy") as mocked_get_strategy:
            mocked_get_strategy.return_value = SimpleNamespace(default_params=StrategyParams(), runner=lambda config, params: report)
            portfolio = build_portfolio(
                AppConfig(),
                source="strategy",
                strategy="trend-strength",
                top=2,
                weighting="score",
                max_weight=0.7,
                max_risk_score=0.8,
                exclude_risk_tags=("risk_factor_missing",),
                market="sh",
            )
        self.assertEqual(len(portfolio.holdings), 2)
        self.assertTrue(all(row["market"] == "sh" for row in portfolio.holdings))
        self.assertAlmostEqual(sum(row["weight"] for row in portfolio.holdings), 1.0)

    def test_build_portfolio_from_consensus(self) -> None:
        consensus_row = SimpleNamespace(
            market="sh",
            symbol="600000",
            avg_score=88.0,
            risk_score=0.2,
            candidate_types=["strong_trend"],
            tags=["trend"],
            risk_flags=["mild_volatility"],
            reasons=["consensus"],
            strategies=["trend-strength", "relative-strength"],
        )
        fake_result = SimpleNamespace(rows=[consensus_row], as_of="latest")
        with patch("tdx_stocks.portfolio.builder.build_consensus", return_value=fake_result):
            portfolio = build_portfolio(AppConfig(), source="consensus", top=1)
        self.assertEqual(portfolio.summary["source"], "consensus")
        self.assertEqual(portfolio.holdings[0]["symbol"], "600000")

    def test_build_portfolio_consensus_skips_pair_strategies(self) -> None:
        fake_defs = [
            SimpleNamespace(name="trend-strength", group="momentum"),
            SimpleNamespace(name="pairs-arb", group="pair"),
            SimpleNamespace(name="relative-strength", group="momentum"),
        ]
        captured: dict[str, object] = {}

        def fake_build_consensus(_config, strategy_names, **kwargs):
            captured["strategy_names"] = list(strategy_names)
            captured["kwargs"] = kwargs
            return SimpleNamespace(rows=[], as_of="latest")

        with patch("tdx_stocks.portfolio.builder.list_strategies", return_value=fake_defs):
            with patch("tdx_stocks.portfolio.builder.build_consensus", side_effect=fake_build_consensus):
                build_portfolio(AppConfig(), source="consensus", top=1)

        self.assertEqual(captured["strategy_names"], ["trend-strength", "relative-strength"])
        self.assertEqual(captured["kwargs"]["min_hit"], 2)

    def test_build_portfolio_from_report_accepts_latest(self) -> None:
        fake_doc = {
            "candidates": [
                {"market": "sh", "symbol": "600000", "score": 88, "candidate_type": "trend", "risk_flags": [], "tags": []}
            ],
            "data_run_id": "run-1",
            "as_of": "2024-01-31",
        }
        with patch("tdx_stocks.portfolio.builder.load_saved_report", return_value=fake_doc):
            portfolio = build_portfolio(AppConfig(), source="report", strategy="trend-strength")
        self.assertEqual(portfolio.as_of, "2024-01-31")
        self.assertEqual(portfolio.holdings[0]["symbol"], "600000")


class PortfolioBacktestTest(unittest.TestCase):
    def test_backtest_runs_with_mocked_prices(self) -> None:
        holdings_by_signal = {
            date(2024, 1, 1): [Holding(market="sh", symbol="600000", weight=0.5), Holding(market="sz", symbol="000001", weight=0.5)],
            date(2024, 1, 2): [Holding(market="sh", symbol="600000", weight=1.0)],
            date(2024, 1, 3): [Holding(market="sh", symbol="600010", weight=1.0)],
        }
        price_map = {
            ("sh", "600000", date(2024, 1, 2)): 10.0,
            ("sh", "600000", date(2024, 1, 3)): 11.0,
            ("sh", "600000", date(2024, 1, 4)): 12.0,
            ("sz", "000001", date(2024, 1, 2)): 20.0,
            ("sz", "000001", date(2024, 1, 3)): 21.0,
            ("sh", "600010", date(2024, 1, 3)): 5.0,
            ("sh", "600010", date(2024, 1, 4)): 5.5,
        }

        def fake_build_portfolio(config, **kwargs):
            return SimpleNamespace(holdings=[holding.to_dict() for holding in holdings_by_signal[kwargs["as_of"]]], risk_summary={})

        def fake_load_adj_daily_price(con, market, symbol, trade_date):
            price = price_map.get((market, symbol, trade_date))
            if price is None:
                return None
            return SimpleNamespace(open_price=price)

        fake_ctx = SimpleNamespace(con=object(), manifest={"run_id": "r1"}, close=lambda: None)
        with patch("tdx_stocks.portfolio.backtest.open_query_context", return_value=fake_ctx):
            with patch("tdx_stocks.portfolio.backtest.load_trading_dates", return_value=[date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]):
                with patch("tdx_stocks.portfolio.backtest.build_portfolio", side_effect=fake_build_portfolio):
                    with patch("tdx_stocks.portfolio.backtest.load_adj_daily_price", side_effect=fake_load_adj_daily_price):
                        report = run_portfolio_backtest(
                            AppConfig(),
                            source="strategy",
                            strategy="trend-strength",
                            from_date=date(2024, 1, 1),
                            to_date=date(2024, 1, 4),
                            top=2,
                            rebalance_days=1,
                        )
        self.assertGreaterEqual(report.total_return, 0.0)
        self.assertGreater(len(report.periods), 0)

    def test_save_rebalance_plan_keeps_json_when_csv_replace_fails(self) -> None:
        plan = RebalancePlan(
            schema_version="rebalance-plan-v1",
            as_of="2024-01-01",
            current_holdings=[],
            target_holdings=[],
            buy=[],
            sell=[],
            hold=[],
            increase=[],
            reduce=[],
            weight_changes=[
                {
                    "market": "sh",
                    "symbol": "600000",
                    "current_weight": 0.1,
                    "target_weight": 0.2,
                    "delta_weight": 0.1,
                    "action": "BUY",
                    "reason": "test",
                }
            ],
            turnover=0.1,
            risk_summary={},
            diagnostics={},
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            json_path = data_root / "reports" / "rebalance" / "2024-01-01" / "rebalance_plan.json"
            csv_path = data_root / "reports" / "rebalance" / "2024-01-01" / "rebalance_plan.csv"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            json_path.write_text('{"old": true}', encoding="utf-8")
            csv_path.write_text("old,csv\n", encoding="utf-8")
            original_replace = Path.replace
            calls = {"count": 0}

            def failing_replace(self, target):
                calls["count"] += 1
                if calls["count"] == 2:
                    raise RuntimeError("boom")
                return original_replace(self, target)

            with patch.object(Path, "replace", failing_replace):
                with self.assertRaises(RuntimeError):
                    save_rebalance_plan(data_root, plan)

            self.assertIn('"schema_version": "rebalance-plan-v1"', json_path.read_text(encoding="utf-8"))
            self.assertEqual(csv_path.read_text(encoding="utf-8"), "old,csv\n")

    def test_save_portfolio_backtest_report_is_atomic(self) -> None:
        report = PortfolioBacktestReport(
            schema_version="portfolio-backtest-v1",
            app_version="0.6.0",
            generated_at="2024-02-01T10:00:00",
            as_of="2024-01-01",
            data_run_id="run-1",
            source="strategy",
            params={},
            total_return=0.1,
            annual_return=0.2,
            max_drawdown=-0.05,
            volatility=0.12,
            win_rate=0.6,
            turnover=0.3,
            avg_holdings=2.0,
            max_single_weight=0.5,
            market_exposure={"sh": 1.0},
            equity_curve=[],
            periods=[],
            diagnostics={},
        )
        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp)
            path = data_root / "reports" / "portfolios" / "backtests" / "2024-01-01" / "portfolio_backtest.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"old": true}', encoding="utf-8")

            def failing_replace(self, target):
                raise RuntimeError("boom")

            with patch.object(Path, "replace", failing_replace):
                with self.assertRaises(RuntimeError):
                    save_portfolio_backtest_report(data_root, report)

            self.assertEqual(path.read_text(encoding="utf-8"), '{"old": true}')


class PortfolioCliParserTest(unittest.TestCase):
    def test_new_commands_are_registered(self) -> None:
        args = build_parser().parse_args(["strategy", "groups"])
        self.assertEqual(args.strategy_command, "groups")
        args = build_parser().parse_args(["strategy", "describe", "trend-strength"])
        self.assertEqual(args.strategy_command, "describe")
        args = build_parser().parse_args(["strategy", "explain", "trend-strength", "000001", "--as-of", "latest"])
        self.assertEqual(args.strategy_command, "explain")
        args = build_parser().parse_args(["portfolio", "build", "--from", "consensus", "--top", "20"])
        self.assertEqual(args.portfolio_command, "build")
        args = build_parser().parse_args(["portfolio", "risk", "--portfolio", "latest"])
        self.assertEqual(args.portfolio_command, "risk")
        args = build_parser().parse_args(["portfolio", "rebalance-plan", "--current", "holdings.csv", "--from", "consensus"])
        self.assertEqual(args.portfolio_command, "rebalance-plan")
        args = build_parser().parse_args(["portfolio", "backtest", "--from", "consensus", "--from-date", "2024-01-01", "--to-date", "2024-01-31"])
        self.assertEqual(args.portfolio_command, "backtest")


if __name__ == "__main__":
    unittest.main()
