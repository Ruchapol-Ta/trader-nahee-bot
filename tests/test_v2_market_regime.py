import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from market_regime import evaluate_market_regime


def _market_row(**overrides):
    data = {
        "close": 500.0,
        "ema50": 475.0,
        "ema200": 430.0,
        "return_20d": 4.0,
    }
    data.update(overrides)
    return data


def test_market_regime_is_valid_when_spy_and_qqq_are_above_bullish_ema_stack():
    result = evaluate_market_regime({
        "SPY": _market_row(),
        "QQQ": _market_row(close=450.0, ema50=420.0, ema200=390.0),
    })

    assert result["is_valid"] is True
    assert result["score"] == 10
    assert result["invalid_reasons"] == []
    assert "bullish" in result["summary"].lower()


def test_market_regime_reports_each_failed_hard_gate_condition():
    result = evaluate_market_regime({
        "SPY": _market_row(close=410.0, ema50=420.0, ema200=430.0),
        "QQQ": _market_row(close=380.0, ema50=390.0, ema200=400.0),
    })

    assert result["is_valid"] is False
    assert result["score"] == 0
    assert "SPY close <= 50EMA" in result["invalid_reasons"]
    assert "SPY close <= 200EMA" in result["invalid_reasons"]
    assert "SPY 50EMA <= 200EMA" in result["invalid_reasons"]
    assert "QQQ close <= 50EMA" in result["invalid_reasons"]
    assert "QQQ close <= 200EMA" in result["invalid_reasons"]
    assert "QQQ 50EMA <= 200EMA" in result["invalid_reasons"]
