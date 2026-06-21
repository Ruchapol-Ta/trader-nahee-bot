import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import v2_engine
from setup_vcp import (
    detect_final_contraction_pivot,
    detect_vcp_contractions,
    evaluate_new_vcp_engine,
    evaluate_vcp_setup,
)


def _interpolated_series(points: list[tuple[int, float]]) -> list[float]:
    values: list[float | None] = [None] * (points[-1][0] + 1)
    for (start_index, start_value), (end_index, end_value) in zip(points, points[1:]):
        span = end_index - start_index
        for offset in range(span + 1):
            ratio = offset / span if span else 0
            values[start_index + offset] = start_value + ((end_value - start_value) * ratio)
    return [float(value) for value in values if value is not None]


def _history_from_points(
    points: list[tuple[int, float]],
    final_dry_volume: bool = True,
    high_overrides: dict[int, float] | None = None,
    low_overrides: dict[int, float] | None = None,
) -> dict:
    close = _interpolated_series(points)
    high = close[:]
    low = close[:]
    for index, value in (high_overrides or {}).items():
        high[index] = value
    for index, value in (low_overrides or {}).items():
        low[index] = value

    volume = [1_200_000.0] * len(close)
    if final_dry_volume:
        for index in range(max(0, len(volume) - 20), max(0, len(volume) - 12)):
            volume[index] = 550_000.0
        for index in range(max(0, len(volume) - 12), len(volume)):
            volume[index] = 900_000.0
    return {
        "dates": [f"2026-01-{(index % 28) + 1:02d}" for index in range(len(close))],
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _valid_two_contraction_history() -> dict:
    return _history_from_points([
        (0, 55.0),
        (75, 100.0),
        (87, 80.0),
        (105, 96.0),
        (113, 88.32),
        (128, 97.0),
    ])


def _valid_three_contraction_history() -> dict:
    return _history_from_points([
        (0, 50.0),
        (80, 100.0),
        (90, 75.0),
        (105, 98.0),
        (113, 84.3),
        (126, 96.0),
        (132, 88.32),
        (145, 97.0),
    ])


def _non_monotonic_uptrend_history() -> dict:
    return _history_from_points([
        (0, 60.0),
        (15, 76.0),
        (30, 68.0),
        (50, 86.0),
        (65, 78.0),
        (80, 100.0),
        (90, 75.0),
        (105, 98.0),
        (113, 84.3),
        (126, 96.0),
        (132, 88.32),
        (145, 97.0),
    ])


def _imperfect_middle_contraction_history() -> dict:
    return _history_from_points([
        (0, 55.0),
        (80, 100.0),
        (90, 80.0),
        (105, 96.0),
        (116, 72.96),
        (130, 95.0),
        (138, 85.5),
        (150, 96.0),
    ])


def _random_chop_history() -> dict:
    close = [
        100.0, 101.0, 99.7, 100.8, 99.4, 100.5, 101.2, 100.1, 99.8, 100.9,
        100.2, 99.6, 100.7, 101.1, 99.9, 100.3, 100.8, 99.7, 100.4, 100.0,
        100.6, 99.8, 100.9, 100.1, 99.5, 100.5, 100.8, 99.9, 100.2, 100.6,
    ]
    return {
        "dates": [f"2026-02-{(index % 28) + 1:02d}" for index in range(len(close))],
        "high": [value * 1.003 for value in close],
        "low": [value * 0.997 for value in close],
        "close": close,
        "volume": [1_000_000.0] * len(close),
    }


def _long_downtrend_history() -> dict:
    return _history_from_points([
        (0, 130.0),
        (40, 110.0),
        (80, 92.0),
        (120, 74.0),
        (145, 70.0),
    ], final_dry_volume=False)


def _one_day_spike_history() -> dict:
    history = _history_from_points([
        (0, 62.0),
        (75, 100.0),
        (90, 96.0),
        (105, 99.0),
        (120, 95.5),
        (140, 98.0),
    ], high_overrides={75: 128.0})
    history["close"][75] = 100.0
    return history


def _loose_quality_history() -> dict:
    return _history_from_points([
        (0, 50.0),
        (80, 100.0),
        (95, 68.0),
        (112, 95.0),
        (124, 82.0),
        (145, 94.0),
    ])


def _legacy_setup_row(**overrides):
    data = {
        "ticker": "TEST",
        "close": 100.0,
        "high": 101.0,
        "ema50": 92.0,
        "ema200": 80.0,
        "sma50": 92.0,
        "sma150": 85.0,
        "sma200": 80.0,
        "sma200_20d_ago": 78.0,
        "high_52w": 102.0,
        "low_52w": 60.0,
        "range_5d_pct": 0.035,
        "range_10d_pct": 0.050,
        "range_20d_pct": 0.080,
        "atr": 2.0,
        "atr_sma20": 2.5,
        "consolidation_volume": 800_000.0,
        "avg_volume": 1_200_000.0,
        "avg_volume_50": 1_000_000.0,
        "avg_dollar_volume": 120_000_000.0,
        "volume": 1_500_000.0,
        "pivot": 99.0,
        "contraction_low": 94.0,
        "pivot_low": 95.0,
        "return_20d": 6.0,
        "market_cap": 3_000_000_000.0,
    }
    data.update(overrides)
    return data


def test_no_contractions_in_random_chop():
    result = detect_vcp_contractions(_legacy_setup_row(close=100.0, _history=_random_chop_history()))

    assert result["passed"] is False
    assert result["contraction_count"] == 0
    assert any(
        reason in result["reject_reasons"]
        for reason in ["contraction count 0 < 2", "no candidate VCP base window", "base depth 2.3% < 8%"]
    )


def test_no_contractions_in_long_downtrend():
    result = detect_vcp_contractions(_legacy_setup_row(close=70.0, _history=_long_downtrend_history()))

    assert result["passed"] is False
    assert result["contraction_count"] < 2
    assert any(
        reason in result["reject_reasons"]
        for reason in ["prior uptrend not confirmed", "base window resembles long downtrend", "no candidate VCP base window"]
    )


def test_detects_valid_two_contraction_vcp():
    result = detect_vcp_contractions(_legacy_setup_row(close=97.0, _history=_valid_two_contraction_history()))

    assert result["passed"] is True
    assert result["contraction_count"] == 2
    assert result["contraction_depths"] == pytest.approx([20.0, 8.0])
    assert result["final_contraction_depth"] == pytest.approx(8.0)
    assert "preferred_contractions_missing" in result["warning_flags"]


def test_detects_valid_three_contraction_vcp():
    result = detect_vcp_contractions(_legacy_setup_row(close=97.0, _history=_valid_three_contraction_history()))

    assert result["passed"] is True
    assert result["contraction_count"] == 3
    assert result["contraction_depths"] == pytest.approx([25.0, 13.98, 8.0])
    assert result["base_depth"] == pytest.approx(25.0)
    assert result["volume_quality"] == "dry_up"
    assert result["prior_uptrend_pass"] is True


def test_noisy_one_day_spike_does_not_create_fake_contraction():
    result = detect_vcp_contractions(_legacy_setup_row(close=98.0, _history=_one_day_spike_history()))

    assert result["passed"] is False
    assert result["contraction_count"] < 2
    assert 28.0 not in result["contraction_depths"]


def test_prior_uptrend_passes_for_realistic_non_monotonic_uptrend():
    result = detect_vcp_contractions(_legacy_setup_row(close=97.0, _history=_non_monotonic_uptrend_history()))

    assert result["passed"] is True
    assert result["prior_uptrend_pass"] is True
    assert result["prior_uptrend_pct"] > 20.0
    assert "pre-base advance" in result["prior_uptrend_reason"]


def test_tightening_allows_one_imperfect_middle_contraction():
    result = detect_vcp_contractions(_legacy_setup_row(close=96.0, _history=_imperfect_middle_contraction_history()))

    assert result["passed"] is True
    assert result["contraction_count"] == 3
    assert result["contraction_depths"] == pytest.approx([20.0, 24.0, 10.0])
    assert result["tightening_pass"] is True
    assert result["tightening_warning"] == "middle contraction is imperfect but final contraction tightened"


def test_pivot_uses_final_contraction_or_handle_shelf():
    contraction_result = detect_vcp_contractions(_legacy_setup_row(close=97.0, _history=_valid_three_contraction_history()))

    breakout = detect_final_contraction_pivot(_legacy_setup_row(close=97.0), contraction_result)
    extended = detect_final_contraction_pivot(_legacy_setup_row(close=103.0), contraction_result)

    assert breakout["pivot_price"] == 97.0
    assert breakout["pivot_source"] == "handle_shelf_high_cluster"
    assert breakout["pivot_status"] == "near_pivot"
    assert extended["pivot_status"] == "extended"
    assert "price more than 5% above final-contraction pivot" in extended["reject_reasons"]


def test_shadow_engine_does_not_hard_filter_current_vcp_logic():
    result = evaluate_vcp_setup(_legacy_setup_row(close=100.0, _history=_random_chop_history()))

    assert result["passed"] is True
    assert result["new_vcp_engine"]["passed"] is False
    assert result["vcp_engine_comparison"]["agreement"] == "current_only"
    assert result["reject_reasons"] == []


def test_v2_diagnostics_compare_current_logic_to_new_engine(monkeypatch):
    monkeypatch.setattr(v2_engine, "enrich_with_market_metadata", lambda data, **kwargs: data)
    diagnostics = v2_engine._new_diagnostics(scanned=1)
    snapshot = _legacy_setup_row(close=97.0, pivot=96.0, _history=_valid_three_contraction_history())

    candidate = v2_engine.qualify_snapshot(
        snapshot,
        {"is_valid": True, "reasons": ["market regime bullish"], "summary": "Bullish"},
        spy_return=4.0,
        qqq_return=5.0,
        diagnostics=diagnostics,
        fetch_liquidity_metadata=False,
        log_liquidity_metadata_warnings=False,
    )
    summary = v2_engine._vcp_shadow_summary(diagnostics)

    assert candidate is not None
    assert candidate["new_vcp_engine"]["passed"] is True
    assert candidate["vcp_engine_comparison"]["agreement"] == "both_passed"
    assert summary["agreement_counts"]["both_passed"] == 1
    assert summary["current_logic_passed"] == 1
    assert summary["new_engine_passed"] == 1
    assert summary["new_engine_contractions_3plus"] == 1
    assert summary["new_engine_pivot_identified"] == 1
    assert candidate["new_vcp_engine"]["shadow_vcp_quality_score"] >= 90
    assert candidate["new_vcp_engine"]["shadow_vcp_quality_grade"] == "Elite"
    assert summary["shadow_quality_grades"]["Elite"] == 1
    assert summary["shadow_quality_score_buckets"]["90-100"] == 1
    assert summary["shadow_quality_average"] >= 90


def test_elite_vcp_structure_scores_90_plus():
    result = evaluate_new_vcp_engine(_legacy_setup_row(close=97.0, _history=_valid_three_contraction_history()))

    assert result["passed"] is True
    assert result["shadow_vcp_quality_score"] >= 90
    assert result["shadow_vcp_quality_grade"] == "Elite"
    assert result["vcp_quality_score"] == result["shadow_vcp_quality_score"]
    assert set(result["shadow_vcp_quality_components"]) == {
        "prior_uptrend_quality",
        "base_depth_quality",
        "base_duration_quality",
        "contraction_count_quality",
        "tightening_quality",
        "final_contraction_quality",
        "pivot_quality",
        "extension_penalty",
    }


def test_strong_vcp_structure_scores_80_to_89():
    result = evaluate_new_vcp_engine(_legacy_setup_row(close=97.0, _history=_valid_two_contraction_history()))

    assert result["passed"] is True
    assert 80 <= result["shadow_vcp_quality_score"] <= 89
    assert result["shadow_vcp_quality_grade"] == "Strong"


def test_weak_loose_structure_scores_below_70():
    result = evaluate_new_vcp_engine(_legacy_setup_row(close=88.0, _history=_loose_quality_history()))

    assert result["shadow_vcp_quality_score"] < 70
    assert result["shadow_vcp_quality_grade"] in {"Weak", "Poor"}
    assert result["shadow_vcp_quality_components"]["base_depth_quality"] < 10


def test_failed_no_pivot_structure_scores_low():
    result = evaluate_new_vcp_engine(_legacy_setup_row(close=100.0, _history=_random_chop_history()))

    assert result["passed"] is False
    assert result["pivot_price"] is None
    assert result["shadow_vcp_quality_score"] < 60
    assert result["shadow_vcp_quality_grade"] == "Poor"
    assert any("no identifiable pivot" in item for item in result["shadow_vcp_quality_penalties"])


def test_overextended_setup_receives_quality_penalty():
    normal = evaluate_new_vcp_engine(_legacy_setup_row(close=97.0, _history=_valid_three_contraction_history()))
    extended = evaluate_new_vcp_engine(_legacy_setup_row(close=103.0, _history=_valid_three_contraction_history()))

    assert extended["passed"] is False
    assert extended["is_extended"] is True
    assert extended["shadow_vcp_quality_components"]["extension_penalty"] < 0
    assert extended["shadow_vcp_quality_score"] < normal["shadow_vcp_quality_score"]


def test_rs_and_trend_template_do_not_affect_shadow_vcp_quality_score():
    base = evaluate_new_vcp_engine(_legacy_setup_row(
        close=97.0,
        rs_percentile=99.0,
        _history=_valid_three_contraction_history(),
    ))
    weak_context = evaluate_new_vcp_engine(_legacy_setup_row(
        close=97.0,
        rs_percentile=5.0,
        sma50=130.0,
        sma150=125.0,
        sma200=120.0,
        sma200_20d_ago=121.0,
        high_52w=160.0,
        low_52w=95.0,
        _history=_valid_three_contraction_history(),
    ))

    assert weak_context["shadow_vcp_quality_score"] == base["shadow_vcp_quality_score"]
    assert weak_context["shadow_vcp_quality_components"] == base["shadow_vcp_quality_components"]
