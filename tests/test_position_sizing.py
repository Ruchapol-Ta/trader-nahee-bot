import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from position_sizing import calculate_position_size, calculate_signal_position_size


def test_position_size_uses_entry_stop_and_risk_percent():
    result = calculate_position_size(
        entry=100.0,
        stop=95.0,
        portfolio_size=10_000.0,
        risk_pct=0.01,
    )

    assert result["valid"] is True
    assert result["risk_per_share"] == 5.0
    assert result["max_capital_risk"] == 100.0
    assert result["suggested_shares"] == 20
    assert result["estimated_position_value"] == 2000.0
    assert result["max_loss"] == 100.0


def test_signal_position_size_reads_v2_trade_plan_stop_loss():
    signal = {
        "trade_plan": {
            "entry": 50.0,
            "stop_loss": 47.5,
        }
    }

    result = calculate_signal_position_size(signal, portfolio_size=10_000.0, risk_pct=0.01)

    assert result["valid"] is True
    assert result["risk_per_share"] == 2.5
    assert result["suggested_shares"] == 40


def test_position_size_rejects_stop_at_or_above_entry():
    result = calculate_position_size(
        entry=100.0,
        stop=100.0,
        portfolio_size=10_000.0,
        risk_pct=0.01,
    )

    assert result["valid"] is False
    assert result["suggested_shares"] == 0
    assert "stop must be below entry" in result["reason"]


def test_position_size_rejects_invalid_portfolio_or_risk_percent():
    assert calculate_position_size(100.0, 95.0, 0.0, 0.01)["valid"] is False
    assert calculate_position_size(100.0, 95.0, 10_000.0, 0.0)["valid"] is False


def test_signal_position_size_handles_missing_trade_plan_values():
    result = calculate_signal_position_size({"trade_plan": {"entry": 100.0}})

    assert result["valid"] is False
    assert result["suggested_shares"] == 0
