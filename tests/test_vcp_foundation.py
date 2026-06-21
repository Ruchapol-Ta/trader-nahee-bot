import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from relative_strength import (
    calculate_rs_composite,
    evaluate_relative_strength,
    rank_universe_rs_percentiles,
)
from screener import compute_series, latest_snapshot
from setup_vcp import evaluate_trend_template


def _ohlcv_frame(rows: int) -> pd.DataFrame:
    closes = pd.Series([50.0 + i * 0.25 for i in range(rows)])
    return pd.DataFrame({
        "Open": closes * 0.995,
        "High": closes * 1.01,
        "Low": closes * 0.99,
        "Close": closes,
        "Volume": 1_250_000,
    })


def _trend_row(**overrides):
    data = {
        "close": 100.0,
        "sma50": 92.0,
        "sma150": 85.0,
        "sma200": 78.0,
        "sma200_20d_ago": 75.0,
        "high_52w": 110.0,
        "low_52w": 60.0,
    }
    data.update(overrides)
    return data


def test_snapshot_enrichment_with_full_data():
    series = compute_series(_ohlcv_frame(300))
    snapshot = latest_snapshot("FULL", series)

    assert snapshot["sma50"] == pytest.approx(series["close"].iloc[-50:].mean())
    assert snapshot["sma150"] == pytest.approx(series["close"].iloc[-150:].mean())
    assert snapshot["sma200"] == pytest.approx(series["close"].iloc[-200:].mean())
    assert snapshot["sma200_20d_ago"] == pytest.approx(series["sma200"].iloc[-21])
    assert snapshot["high_52w"] == pytest.approx(series["high"].iloc[-252:].max())
    assert snapshot["low_52w"] == pytest.approx(series["low"].iloc[-252:].min())
    assert snapshot["return_63d"] is not None
    assert snapshot["return_126d"] is not None
    assert snapshot["return_252d"] is not None
    assert "missing_vcp_foundation_data" not in snapshot["data_quality_flags"]


def test_snapshot_enrichment_marks_missing_252d_return():
    series = compute_series(_ohlcv_frame(250))
    snapshot = latest_snapshot("IPO", series)

    assert snapshot["sma50"] is not None
    assert snapshot["sma150"] is not None
    assert snapshot["sma200"] is not None
    assert snapshot["return_63d"] is not None
    assert snapshot["return_126d"] is not None
    assert snapshot["return_252d"] is None
    assert "missing_vcp_foundation_data" in snapshot["data_quality_flags"]
    assert any("return_252d unavailable" in reason for reason in snapshot["missing_data_reasons"])


def test_rs_percentile_ranking_uses_universe_composites():
    ranked = rank_universe_rs_percentiles([
        {"ticker": "AAA", "return_63d": 30.0, "return_126d": 60.0, "return_252d": 120.0},
        {"ticker": "BBB", "return_63d": 20.0, "return_126d": 40.0, "return_252d": 80.0},
        {"ticker": "CCC", "return_63d": 10.0, "return_126d": 20.0, "return_252d": 40.0},
        {"ticker": "DDD", "return_63d": -5.0, "return_126d": 5.0, "return_252d": 10.0},
        {"ticker": "EEE", "return_63d": -10.0, "return_126d": -10.0, "return_252d": -10.0},
    ])
    by_ticker = {row["ticker"]: row for row in ranked}

    assert by_ticker["AAA"]["rs_rank"] == 1
    assert by_ticker["AAA"]["rs_percentile"] == 100.0
    assert by_ticker["BBB"]["rs_percentile"] == 80.0
    assert by_ticker["CCC"]["rs_percentile"] == 60.0


def test_rs_composite_reweights_when_252d_return_is_missing():
    composite, coverage = calculate_rs_composite({
        "return_63d": 10.0,
        "return_126d": 20.0,
        "return_252d": None,
    })

    assert composite == pytest.approx(15.8333, abs=0.0001)
    assert coverage["return_252d"] is False
    assert coverage["weight_63d"] == pytest.approx(0.4167, abs=0.0001)
    assert coverage["weight_126d"] == pytest.approx(0.5833, abs=0.0001)
    assert coverage["weight_252d"] == 0.0


def test_rs_percentile_threshold_pass_and_fail():
    passing = evaluate_relative_strength(
        {"ticker": "PASS", "return_20d": -1.0, "rs_percentile": 80.0, "rs_composite": 25.0, "rs_rank": 10},
        spy_return_20d=5.0,
        qqq_return_20d=6.0,
    )
    failing = evaluate_relative_strength(
        {"ticker": "FAIL", "return_20d": 20.0, "rs_percentile": 79.0, "rs_composite": 24.0, "rs_rank": 11},
        spy_return_20d=5.0,
        qqq_return_20d=6.0,
        log_lagging=False,
    )

    assert passing["passed"] is True
    assert passing["benchmark_context"]["outperformed_spy"] is False
    assert failing["passed"] is False
    assert "RS percentile 79.0 < 80" in failing["reject_reasons"][0]


def test_trend_template_pass():
    result = evaluate_trend_template(_trend_row())

    assert result["trend_template_pass"] is True
    assert result["trend_template_score"] == 100.0
    assert result["trend_template_failures"] == []
    assert result["distance_from_52w_high_pct"] == pytest.approx(9.09)
    assert result["distance_above_52w_low_pct"] == pytest.approx(66.67)


def test_trend_template_fails_when_ma_stack_is_wrong():
    result = evaluate_trend_template(_trend_row(sma50=82.0, sma150=85.0))

    assert result["trend_template_pass"] is False
    assert "SMA50 <= SMA150 or SMA150 <= SMA200" in result["trend_template_failures"]


def test_trend_template_fails_when_price_is_too_far_from_52w_high():
    result = evaluate_trend_template(_trend_row(high_52w=150.0))

    assert result["trend_template_pass"] is False
    assert "close more than 25% below 52-week high" in result["trend_template_failures"]


def test_trend_template_fails_when_price_is_not_sufficiently_above_52w_low():
    result = evaluate_trend_template(_trend_row(low_52w=80.0))

    assert result["trend_template_pass"] is False
    assert "close < 30% above 52-week low" in result["trend_template_failures"]
