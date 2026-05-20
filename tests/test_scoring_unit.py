from __future__ import annotations

import pytest

from tdx_stocks.strategies.base import ScoreWeights
from tdx_stocks.strategies.scoring import build_trend_score_breakdown, calculate_multi_factor_score


def test_build_trend_score_breakdown_dispatches_low_vol_breakout() -> None:
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

    breakdown = build_trend_score_breakdown(row, 50_000_000.0, [], strategy_name="low-vol-breakout")

    assert breakdown["trend"] == pytest.approx(31.0)
    assert breakdown["breakout"] == pytest.approx(22.89)
    assert breakdown["low_volatility"] == pytest.approx(12.5)
    assert breakdown["liquidity"] == pytest.approx(16.0)
    assert breakdown["risk_penalty"] == pytest.approx(-2.0)


def test_build_trend_score_breakdown_dispatches_mean_reversion() -> None:
    row = {
        "adj_close": 9.0,
        "ma20": 10.0,
        "ma60": 11.0,
        "std_pctchg_20": 0.12,
        "ret_20": -0.20,
        "rsi_14": 20.0,
        "amount_ma20": 120_000_000.0,
        "bb_lower_20": 9.5,
    }

    breakdown = build_trend_score_breakdown(row, 50_000_000.0, [], strategy_name="mean-reversion")

    assert breakdown["trend"] == pytest.approx(0.0)
    assert breakdown["oversold"] == pytest.approx(30.0)
    assert breakdown["band_reclaim"] == pytest.approx(1.05)
    assert breakdown["liquidity"] == pytest.approx(9.6)
    assert breakdown["risk_penalty"] == pytest.approx(2.0)


def test_build_trend_score_breakdown_rewards_lower_volatility() -> None:
    row = {
        "adj_close": 9.0,
        "ma20": 10.0,
        "ma60": 11.0,
        "std_pctchg_20": 0.03,
        "ret_20": -0.20,
        "rsi_14": 20.0,
        "amount_ma20": 120_000_000.0,
        "bb_lower_20": 9.5,
    }

    breakdown = build_trend_score_breakdown(row, 50_000_000.0, [], strategy_name="mean-reversion")

    assert breakdown["band_reclaim"] == pytest.approx(5.05)


@pytest.mark.parametrize(
    "strategy_name",
    [
        "trend-strength",
        "low-vol-breakout",
        "ma-pullback",
        "relative-strength",
        "volume-breakout",
        "mean-reversion",
        "smart-money",
    ],
)
def test_build_trend_score_breakdown_caps_risk_penalty(strategy_name: str) -> None:
    row = {
        "adj_close": 100.0,
        "ma20": 90.0,
        "ma60": 80.0,
        "ret_5": 0.5,
        "ret_20": 0.5,
        "ret_60": 0.5,
        "amount_ma20": 1_000_000_000.0,
        "pos_20": 1.0,
        "pos_60": 1.0,
        "dd_20": 0.0,
        "vol_ratio_20": 0.0,
        "rsi_14": 90.0,
        "atr_pct_14": 0.2,
        "vol_20": 0.2,
        "vol_ratio_5_60": 0.0,
        "price_vol_corr_20": 1.0,
        "std_pctchg_20": 0.2,
        "bb_lower_20": 90.0,
    }

    breakdown = build_trend_score_breakdown(row, 50_000_000.0, ["risk_factor_missing"], strategy_name=strategy_name)

    assert -30.0 <= breakdown["risk_penalty"] <= 0.0


def test_build_trend_score_breakdown_handles_none_inputs() -> None:
    breakdown = build_trend_score_breakdown(
        {
            "adj_close": None,
            "ma20": None,
            "ma60": None,
            "ret_5": None,
            "ret_20": None,
            "ret_60": None,
            "amount_ma20": None,
            "pos_20": None,
            "pos_60": None,
            "dd_20": None,
            "vol_ratio_20": None,
            "rsi_14": None,
            "atr_pct_14": None,
            "vol_20": None,
            "vol_ratio_5_60": None,
            "price_vol_corr_20": None,
            "std_pctchg_20": None,
            "bb_lower_20": None,
        },
        50_000_000.0,
        [],
        strategy_name="mean-reversion",
    )

    assert breakdown["trend"] == 0.0
    assert breakdown["band_reclaim"] >= 0.0
    assert breakdown["risk_penalty"] == 0.0


def test_calculate_multi_factor_score_uses_weights() -> None:
    weights = ScoreWeights(momentum=0.5, volatility=-0.2, liquidity=0.3, relative_strength=0.1, trend=0.1)
    score_breakdown = calculate_multi_factor_score(
        {
            "rs_score": 0.8,
            "vol_20_pct_rank": 0.9,
            "amount_ma20_pct_rank": 0.7,
            "atr_pct_14_pct_rank": 0.6,
            "pct_rank_ret_20": 0.75,
            "pct_rank_ret_60": 0.70,
            "ma_cross_20_60": 0.65,
        },
        weights,
    )

    assert score_breakdown["momentum"] == pytest.approx(0.4)
    assert score_breakdown["volatility"] == pytest.approx(-0.02)
    assert score_breakdown["liquidity"] == pytest.approx(0.21)
    assert score_breakdown["relative_strength"] == pytest.approx(0.0725)
    assert score_breakdown["trend"] == pytest.approx(0.0625)
    assert score_breakdown["total"] == pytest.approx(0.725)


@pytest.mark.parametrize(
    ("strategy_name", "row", "expected_key"),
    [
        (
            "relative-strength",
            {
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
            },
            "momentum",
        ),
        (
            "volume-breakout",
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
                "vol_ratio_20": 0.4,
                "rsi_14": 60.0,
                "atr_pct_14": 0.03,
                "vol_20": 0.02,
            },
            "volume",
        ),
        (
            "smart-money",
            {
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
            },
            "smart_volume",
        ),
    ],
)
def test_build_trend_score_breakdown_covers_additional_strategy_modes(strategy_name: str, row: dict[str, object], expected_key: str) -> None:
    breakdown = build_trend_score_breakdown(row, 50_000_000.0, [], strategy_name=strategy_name)
    assert expected_key in breakdown
