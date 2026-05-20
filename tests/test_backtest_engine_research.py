from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tdx_stocks.backtest.engine import _build_report_from_matches, _build_trade_from_match, _strategy_params
from tdx_stocks.backtest.models import BacktestParams
from tdx_stocks.backtest.research import validate_monte_carlo, validate_stress_tests, validate_walk_forward


def test_strategy_params_copies_core_fields() -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
        fee_rate=0.001,
        slippage=0.002,
        market="sh",
        candidate_type="strong_trend",
        min_score=65.0,
        min_amount_ma20=1_000_000.0,
    )

    strategy_params = _strategy_params(params, date(2024, 1, 4))

    assert strategy_params.limit == 8
    assert strategy_params.min_score == 65.0
    assert strategy_params.market == "sh"
    assert strategy_params.candidate_type == "strong_trend"
    assert strategy_params.as_of == date(2024, 1, 4)


def test_build_trade_from_match_covers_long_short_and_missing_price() -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
        fee_rate=0.001,
        slippage=0.002,
    )
    long_signal = {
        "signal_date": date(2024, 1, 4),
        "market": "sh",
        "symbol": "600519",
        "display_symbol": "600519.SH",
        "score": 88.0,
        "candidate_type": "strong_trend",
        "direction": "LONG",
    }
    short_signal = dict(long_signal, direction="SHORT", symbol="600001", display_symbol="600001.SH")

    long_trade, long_return = _build_trade_from_match(
        long_signal,
        {"buy_date": date(2024, 1, 5), "sell_date": date(2024, 1, 10), "buy_price": 10.0, "sell_price": 12.0},
        params,
    )
    short_trade, short_return = _build_trade_from_match(
        short_signal,
        {"buy_date": date(2024, 1, 5), "sell_date": date(2024, 1, 10), "buy_price": 10.0, "sell_price": 8.0},
        params,
    )
    missing_trade, missing_return = _build_trade_from_match(long_signal, None, params)

    assert long_trade.net_return is not None
    assert long_return is not None and long_return > 0
    assert short_trade.net_return is not None
    assert short_return is not None and short_return > 0
    assert missing_trade.skipped_reason == "missing_price"
    assert missing_return is None


@pytest.mark.parametrize(
    ("direction", "match", "expected_reason"),
    [
        ("LONG", {"buy_date": date(2024, 1, 5), "buy_price": 10.0, "sell_date": date(2024, 1, 10), "sell_price": 11.0, "buy_is_limit_up": True}, "limit_up/suspended"),
        ("LONG", {"buy_date": date(2024, 1, 5), "buy_price": 10.0, "sell_date": date(2024, 1, 10), "sell_price": 11.0, "buy_is_suspended": True}, "limit_up/suspended"),
        ("SHORT", {"buy_date": date(2024, 1, 5), "buy_price": 10.0, "sell_date": date(2024, 1, 10), "sell_price": 9.0, "buy_is_limit_down": True}, "limit_down/suspended"),
        ("SHORT", {"buy_date": date(2024, 1, 5), "buy_price": 10.0, "sell_date": date(2024, 1, 10), "sell_price": 9.0, "buy_is_suspended": True}, "limit_down/suspended"),
    ],
)
def test_build_trade_from_match_skips_limit_and_suspension(direction: str, match: dict[str, object], expected_reason: str) -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
        fee_rate=0.001,
        slippage=0.002,
    )
    signal = {
        "signal_date": date(2024, 1, 4),
        "market": "sh",
        "symbol": "600519",
        "display_symbol": "600519.SH",
        "score": 88.0,
        "candidate_type": "strong_trend",
        "direction": direction,
    }

    trade, net_return = _build_trade_from_match(signal, match, params)

    assert trade.skipped_reason == expected_reason
    assert net_return is None
    assert trade.sell_date is None


def test_build_report_from_matches_aggregates_periods() -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
        fee_rate=0.0,
        slippage=0.0,
    )
    trading_dates = [date(2024, 1, 4), date(2024, 1, 5), date(2024, 1, 10)]
    periods_input = [
        {
            "signal_date": trading_dates[0],
            "buy_date": trading_dates[1],
            "sell_date": trading_dates[2],
            "signals": [
                {
                    "signal_date": trading_dates[0],
                    "signal_rank": 0,
                    "market": "sh",
                    "symbol": "600519",
                    "display_symbol": "600519.SH",
                    "score": 88.0,
                    "candidate_type": "strong_trend",
                    "direction": "LONG",
                }
            ],
            "skipped_reasons": [],
        }
    ]
    matches = {
        ("2024-01-04", 0): {
            "buy_date": trading_dates[1],
            "sell_date": trading_dates[2],
            "buy_price": 10.0,
            "sell_price": 12.0,
            "buy_is_limit_up": False,
            "buy_is_suspended": False,
            "buy_is_limit_down": False,
            "sell_is_limit_down": False,
            "sell_is_suspended": False,
        }
    }

    report = _build_report_from_matches("trend-strength", params, trading_dates, periods_input, matches)

    assert report.period_count == 1
    assert report.trade_count == 1
    assert report.total_return > 0
    assert report.empty_period_count == 0


def test_build_report_from_matches_handles_empty_candidate_sets() -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
        fee_rate=0.0,
        slippage=0.0,
    )
    trading_dates = [date(2024, 1, 4), date(2024, 1, 5)]
    periods_input = [
        {
            "signal_date": trading_dates[0],
            "buy_date": trading_dates[1],
            "sell_date": None,
            "signals": [],
            "skipped_reasons": ["insufficient_future_dates"],
        }
    ]

    report = _build_report_from_matches("trend-strength", params, trading_dates, periods_input, {})

    assert report.trade_count == 0
    assert report.empty_period_count == 1
    assert report.periods[0]["empty"] is True


def test_research_wrappers_delegate_to_underlying_helpers() -> None:
    params = BacktestParams(
        from_date=date(2024, 1, 1),
        to_date=date(2024, 1, 31),
        top=8,
        hold_days=5,
    )
    config = SimpleNamespace()
    with (
        patch("tdx_stocks.backtest.research.run_monte_carlo_simulation", return_value={"runs": 1}) as mocked_mc,
        patch("tdx_stocks.backtest.research.run_stress_test_suite", return_value={"stress": True}) as mocked_stress,
        patch("tdx_stocks.backtest.research.run_walk_forward_validation", return_value={"walk": True}) as mocked_walk,
    ):
        monte_carlo = validate_monte_carlo({"params": {"portfolio": {"initial_cash": 2.0}}, "trades": []}, iterations=10, seed=7)
        stress = validate_stress_tests(config, "trend-strength", params, {"stress": ("2024-01-01", "2024-01-31")})
        walk = validate_walk_forward(config, "trend-strength", params, train_years=2, test_years=1)

    assert monte_carlo == {"runs": 1}
    assert stress == {"stress": True}
    assert walk == {"walk": True}
    mocked_mc.assert_called_once()
    mocked_stress.assert_called_once()
    mocked_walk.assert_called_once()
