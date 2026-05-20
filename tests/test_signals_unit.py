from __future__ import annotations

import pytest

from tdx_stocks.strategies.base import StrategyParams
from tdx_stocks.strategies.presets.mean_reversion import MeanReversionParams
from tdx_stocks.strategies.signals import (
    build_trend_risk_flags,
    build_trend_watch_plan,
    classify_trend_candidate,
)


def test_classify_trend_candidate_identifies_breakout_watch() -> None:
    row = {
        "adj_close": 12.0,
        "ma20": 10.0,
        "ma60": 9.0,
        "ret_5": 0.03,
        "ret_20": 0.12,
        "amount_ma20": 200_000_000.0,
        "pos_20": 0.9,
        "dd_20": -0.01,
        "vol_ratio_20": 0.2,
        "rsi_14": 60.0,
        "atr_pct_14": 0.03,
        "vol_20": 0.02,
    }

    candidate_type, tags, reasons = classify_trend_candidate(row, StrategyParams())

    assert candidate_type == "breakout_watch"
    assert "breakout_watch" in tags
    assert "near_20d_high" in tags
    assert "趋势延续" in reasons
    assert build_trend_watch_plan(candidate_type, build_trend_risk_flags(row)) == "放量突破前高才确认，尾盘回落不追"


def test_classify_trend_candidate_identifies_mean_reversion_and_risk_flags() -> None:
    row = {
        "adj_close": 9.0,
        "ma20": 10.0,
        "std_pctchg_20": 0.12,
        "ret_20": -0.20,
        "rsi_14": 20.0,
        "amount_ma20": 120_000_000.0,
        "bb_lower_20": 9.5,
    }

    candidate_type, tags, reasons = classify_trend_candidate(row, MeanReversionParams())
    risk_flags = build_trend_risk_flags(row, strategy_name="mean-reversion")
    watch_plan = build_trend_watch_plan(candidate_type, risk_flags, strategy_name="mean-reversion")

    assert candidate_type == "oversold_rebound"
    assert "oversold_rebound" in tags
    assert "RSI 超卖" in reasons
    assert "risk_factor_missing" in risk_flags
    assert watch_plan == "超跌反弹先等止跌确认，继续放量下杀则放弃"


def test_classify_trend_candidate_identifies_smart_money() -> None:
    row = {
        "adj_close": 12.0,
        "ma20": 11.0,
        "ret_20": 0.10,
        "amount_ma20": 150_000_000.0,
        "vol_ratio_5_60": 3.0,
        "price_vol_corr_20": 0.7,
        "atr_pct_14_pct_rank": 0.9,
        "vol_20_pct_rank": 0.7,
        "atr_pct_14": 0.03,
        "vol_20": 0.02,
        "rsi_14": 60.0,
    }

    candidate_type, tags, reasons = classify_trend_candidate(row, StrategyParams(), strategy_name="smart-money")
    risk_flags = build_trend_risk_flags(row, strategy_name="smart-money")
    watch_plan = build_trend_watch_plan(candidate_type, risk_flags, strategy_name="smart-money")

    assert candidate_type == "smart_money"
    assert "smart_money" in tags
    assert "量价齐升" in reasons
    assert "risk_factor_missing" not in risk_flags
    assert watch_plan == "放量且量价同步上行时观察，异动衰减则放弃"


@pytest.mark.parametrize(
    ("strategy_name", "row", "expected_type", "expected_tag"),
    [
        (
            "low-vol-breakout",
            {
                "adj_close": 12.0,
                "ma20": 10.0,
                "ma60": 9.0,
                "ret_5": 0.03,
                "ret_20": 0.12,
                "amount_ma20": 200_000_000.0,
                "pos_20": 0.9,
                "pos_60": 0.8,
                "dd_20": -0.01,
                "vol_ratio_20": 0.2,
                "rsi_14": 60.0,
                "atr_pct_14": 0.03,
                "vol_20": 0.02,
            },
            "breakout_watch",
            "low_volatility",
        ),
        (
            "relative-strength",
            {
                "adj_close": 12.0,
                "ma20": 10.0,
                "ma60": 9.0,
                "ret_5": 0.02,
                "ret_20": 0.10,
                "ret_60": 0.14,
                "amount_ma20": 200_000_000.0,
                "pos_20": 0.8,
            },
            "strong_trend",
            "relative_strength",
        ),
        (
            "volume-breakout",
            {
                "adj_close": 12.0,
                "ma20": 10.0,
                "pos_20": 0.9,
                "dd_20": -0.01,
                "vol_ratio_20": 0.4,
                "ret_5": 0.02,
                "rsi_14": 60.0,
                "vol_20": 0.02,
                "amount_ma20": 150_000_000.0,
            },
            "breakout_watch",
            "volume_breakout",
        ),
    ],
)
def test_classify_trend_candidate_covers_additional_strategy_modes(strategy_name: str, row: dict[str, object], expected_type: str, expected_tag: str) -> None:
    candidate_type, tags, reasons = classify_trend_candidate(row, StrategyParams(), strategy_name=strategy_name)
    assert candidate_type == expected_type
    assert expected_tag in tags
    assert reasons
