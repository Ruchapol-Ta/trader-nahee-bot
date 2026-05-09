import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine import evaluate_signal_decision


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "grade": "A",
        "score": 82,
        "close": 100.0,
        "ema20": 96.0,
        "ema50": 90.0,
        "volume": 1_250_000.0,
        "avg_volume": 1_000_000.0,
        "is_actual_breakout": True,
        "is_near_breakout": False,
        "market_regime": "Bullish market regime",
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 94.0,
            "expected_rr": 2.5,
        },
        "category_scores": {"relative_strength": 15},
        "pass_reasons": ["trend structure bullish", "breakout above pivot"],
    }
    data.update(overrides)
    return data


def _assert_decision_shape(result):
    assert set(result) == {
        "decision",
        "confidence",
        "main_reason",
        "supporting_reasons",
        "risk_warnings",
        "next_action",
    }
    assert isinstance(result["supporting_reasons"], list)
    assert isinstance(result["risk_warnings"], list)


def test_decision_layer_returns_none_when_disabled():
    assert evaluate_signal_decision(_signal(), enabled=False) is None


def test_actual_a_breakout_with_valid_risk_returns_enter():
    result = evaluate_signal_decision(_signal(), enabled=True)

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"
    assert result["confidence"] == "HIGH"


def test_near_breakout_returns_wait():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, is_actual_breakout=False, is_near_breakout=True),
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert "breakout" in result["next_action"].lower()


def test_b_actual_breakout_with_valid_market_decent_risk_and_volume_returns_wait():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, is_actual_breakout=True, is_near_breakout=False),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert "B-grade" in result["main_reason"]


def test_b_actual_breakout_with_bad_volume_returns_avoid():
    result = evaluate_signal_decision(
        _signal(
            grade="B",
            score=70,
            is_actual_breakout=True,
            is_near_breakout=False,
            volume=800_000.0,
            avg_volume=1_000_000.0,
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert any("volume" in warning.lower() for warning in result["risk_warnings"])


def test_promising_signal_in_unsupportive_market_returns_watchlist_only():
    result = evaluate_signal_decision(
        _signal(grade="B", score=70, market_regime="Invalid market regime"),
        market_regime={"is_valid": False, "summary": "Invalid market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"


def test_relative_strength_can_be_confirmed_from_category_scores_without_benchmark_data():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 15}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_realistic_a_plus_v2_trade_alert_remains_enter():
    result = evaluate_signal_decision(
        _signal(
            grade="A+",
            score=91,
            close=100.0,
            ema20=97.0,
            ema50=92.0,
            volume=1_400_000.0,
            avg_volume=1_000_000.0,
            category_scores={
                "market_regime": 10,
                "liquidity": 10,
                "trend_structure": 15,
                "relative_strength": 15,
                "high_52w_proximity": 10,
                "consolidation_tightness": 10,
                "atr_contraction": 10,
                "volume_quality": 10,
                "risk_reward": 10,
            },
            pass_reasons=[
                "SPY bullish EMA stack",
                "trend structure bullish",
                "outperformed SPY",
                "breakout above pivot",
            ],
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_actual_breakout_without_relative_strength_confirmation_returns_wait():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 0}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("relative strength" in warning.lower() for warning in result["risk_warnings"])


def test_negative_relative_strength_category_score_does_not_confirm_rs():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": -1}, pass_reasons=[]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("relative strength" in warning.lower() for warning in result["risk_warnings"])


def test_pass_reasons_relative_strength_evidence_still_confirms_rs():
    result = evaluate_signal_decision(
        _signal(category_scores={"relative_strength": 0}, pass_reasons=["outperformed QQQ"]),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "ENTER"


def test_malformed_inputs_do_not_crash_and_degrade_to_avoid_or_wait():
    result = evaluate_signal_decision(
        _signal(
            score="not-a-number",
            trade_plan=["not", "a", "dict"],
            pass_reasons="outperformed SPY",
            category_scores=["not", "a", "dict"],
        ),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] in {"AVOID", "WAIT"}


def test_missing_ema_and_volume_fields_do_not_crash_and_degrade_safely():
    signal = _signal()
    for key in ["ema20", "ema50", "volume", "avg_volume"]:
        signal.pop(key)

    result = evaluate_signal_decision(
        signal,
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("unavailable" in warning.lower() for warning in result["risk_warnings"])


def test_risk_reward_between_watchlist_and_entry_threshold_returns_wait():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "stop_loss": 94.0, "expected_rr": 2.2}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WAIT"
    assert any("risk/reward" in warning.lower() for warning in result["risk_warnings"])


def test_excessive_stop_distance_returns_avoid():
    result = evaluate_signal_decision(
        _signal(trade_plan={"entry": 100.0, "stop_loss": 86.0, "expected_rr": 2.5}),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert any("stop distance" in warning.lower() for warning in result["risk_warnings"])


def test_severe_extension_returns_avoid():
    result = evaluate_signal_decision(
        _signal(close=100.0, ema20=72.0, ema50=70.0),
        market_regime={"is_valid": True, "summary": "Bullish market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert any("extended" in warning.lower() for warning in result["risk_warnings"])


def test_invalid_risk_or_weak_grade_returns_avoid():
    result = evaluate_signal_decision(
        _signal(grade="C", score=55, trade_plan={"entry": 100.0, "stop_loss": 101.0, "expected_rr": 0.5}),
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert result["risk_warnings"]
