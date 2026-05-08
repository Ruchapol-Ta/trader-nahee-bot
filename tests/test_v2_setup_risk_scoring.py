import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from risk_engine import build_trade_plan
from scoring import grade_for_score, score_candidate
from setup_vcp import evaluate_vcp_setup


def _setup_row(**overrides):
    data = {
        "ticker": "AAPL",
        "close": 100.0,
        "high": 101.0,
        "ema50": 92.0,
        "ema200": 80.0,
        "high_52w": 102.0,
        "range_5d_pct": 0.035,
        "range_10d_pct": 0.050,
        "range_20d_pct": 0.080,
        "atr": 2.0,
        "atr_sma20": 2.5,
        "consolidation_volume": 800_000.0,
        "avg_volume": 1_200_000.0,
        "volume": 1_500_000.0,
        "pivot": 99.0,
        "contraction_low": 94.0,
        "pivot_low": 95.0,
    }
    data.update(overrides)
    return data


def test_vcp_setup_passes_a_simple_breakout_with_contraction_and_volume():
    result = evaluate_vcp_setup(_setup_row())

    assert result["passed"] is True
    assert result["checks"]["trend"] is True
    assert result["checks"]["near_high"] is True
    assert result["checks"]["range_tightening"] is True
    assert result["checks"]["atr_contraction"] is True
    assert result["checks"]["volume_dry_up"] is True
    assert result["checks"]["breakout"] is True
    assert result["reject_reasons"] == []


def test_vcp_setup_uses_only_trend_and_breakout_proximity_as_hard_gates():
    result = evaluate_vcp_setup(_setup_row(
        close=93.0,
        ema50=95.0,
        pivot=99.0,
        range_5d_pct=0.090,
        atr=3.0,
        consolidation_volume=1_300_000.0,
        volume=900_000.0,
    ))

    assert result["passed"] is False
    assert "price not above 50EMA/200EMA with 50EMA > 200EMA" in result["reject_reasons"]
    assert "close is not above or within near-breakout range of pivot/resistance" in result["reject_reasons"]
    assert "ATR is not contracting" not in result["reject_reasons"]
    assert "volume has not dried up in consolidation" not in result["reject_reasons"]


def test_soft_scoring_does_not_hard_reject_atr_contraction_failure():
    result = evaluate_vcp_setup(_setup_row(atr=3.0, atr_sma20=2.5))

    assert result["passed"] is True
    assert result["checks"]["atr_contraction"] is False
    assert result["quality_scores"]["atr_contraction"] < 10
    assert result["reject_reasons"] == []


def test_soft_scoring_does_not_hard_reject_volume_dry_up_failure():
    result = evaluate_vcp_setup(_setup_row(consolidation_volume=1_300_000.0))

    assert result["passed"] is True
    assert result["checks"]["volume_dry_up"] is False
    assert result["quality_scores"]["volume_quality"] < 10
    assert result["reject_reasons"] == []


def test_trade_plan_uses_breakout_close_stop_below_contraction_low_and_r_targets():
    plan = build_trade_plan(_setup_row(close=100.0, high=101.0, contraction_low=94.0))

    assert plan["entry"] == 100.0
    assert plan["buy_stop"] == 101.1
    assert plan["stop_loss"] == 93.53
    assert plan["risk_per_share"] == 6.47
    assert plan["target_1"] == 116.18
    assert plan["target_2"] == 125.88
    assert plan["expected_rr"] == 2.5
    assert plan["position_size"] == "Portfolio size required"


def test_trade_plan_rejects_non_positive_risk():
    result = build_trade_plan(_setup_row(close=94.0, contraction_low=95.0, pivot_low=95.0))

    assert result is None


def test_grade_boundaries_are_configurable_style_bands():
    assert grade_for_score(90) == "A+"
    assert grade_for_score(75) == "A"
    assert grade_for_score(65) == "B"
    assert grade_for_score(50) == "C"
    assert grade_for_score(49) == "Reject"


def test_score_candidate_sums_required_category_scores():
    setup = evaluate_vcp_setup(_setup_row())
    score = score_candidate(
        market_regime={"is_valid": True},
        liquidity={"passed": True},
        relative_strength={"passed": True},
        setup=setup,
        trade_plan={"expected_rr": 2.5},
    )

    assert score["score"] == 100
    assert score["grade"] == "A+"
    assert set(score["category_scores"]) == {
        "market_regime",
        "liquidity",
        "trend_structure",
        "relative_strength",
        "high_52w_proximity",
        "consolidation_tightness",
        "atr_contraction",
        "volume_quality",
        "risk_reward",
    }
