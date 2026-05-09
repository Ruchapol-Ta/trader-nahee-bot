import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decision_engine import evaluate_signal_decision


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "grade": "A",
        "score": 82,
        "is_actual_breakout": True,
        "is_near_breakout": False,
        "market_regime": "Bullish market regime",
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 94.0,
            "expected_rr": 2.5,
        },
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


def test_promising_signal_in_unsupportive_market_returns_watchlist_only():
    result = evaluate_signal_decision(
        _signal(market_regime="Invalid market regime"),
        market_regime={"is_valid": False, "summary": "Invalid market regime"},
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "WATCHLIST_ONLY"


def test_invalid_risk_or_weak_grade_returns_avoid():
    result = evaluate_signal_decision(
        _signal(grade="C", score=55, trade_plan={"entry": 100.0, "stop_loss": 101.0, "expected_rr": 0.5}),
        enabled=True,
    )

    _assert_decision_shape(result)
    assert result["decision"] == "AVOID"
    assert result["risk_warnings"]
