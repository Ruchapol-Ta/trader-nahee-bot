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
    assert result["sizing_mode"] == "mock_config"
    assert result["trade_risk_mode"] == "NORMAL"


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
    assert result["sizing_mode"] == "invalid_input"
    assert result["suggested_shares"] == 0
    assert "stop must be below entry" in result["reason"]


def test_position_size_rejects_invalid_portfolio_or_risk_percent():
    bad_portfolio = calculate_position_size(100.0, 95.0, 0.0, 0.01)
    bad_risk = calculate_position_size(100.0, 95.0, 10_000.0, 0.0)

    assert bad_portfolio["valid"] is False
    assert bad_portfolio["sizing_mode"] == "invalid_input"
    assert bad_risk["valid"] is False
    assert bad_risk["sizing_mode"] == "invalid_input"


def test_signal_position_size_handles_missing_trade_plan_values():
    result = calculate_signal_position_size({"trade_plan": {"entry": 100.0}})

    assert result["valid"] is False
    assert result["sizing_mode"] == "invalid_input"
    assert result["suggested_shares"] == 0


def test_no_trade_returns_disabled_zero_position():
    result = calculate_position_size(
        entry=100.0,
        stop=95.0,
        portfolio_size=10_000.0,
        trade_risk_mode="NO_TRADE",
    )

    assert result["valid"] is False
    assert result["sizing_mode"] == "disabled"
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["risk_pct"] == 0.0
    assert result["suggested_shares"] == 0
    assert result["max_capital_risk"] == 0.0
    assert result["max_loss"] == 0.0


def test_position_size_rejects_missing_entry_and_non_numeric_values():
    missing_entry = calculate_position_size(None, 95.0)
    non_numeric = calculate_position_size("bad", 95.0)

    assert missing_entry["valid"] is False
    assert missing_entry["sizing_mode"] == "invalid_input"
    assert non_numeric["valid"] is False
    assert non_numeric["sizing_mode"] == "invalid_input"


def test_trade_risk_modes_produce_different_risk_budgets():
    tiny = calculate_position_size(100.0, 95.0, portfolio_size=10_000.0, trade_risk_mode="TINY")
    small = calculate_position_size(100.0, 95.0, portfolio_size=10_000.0, trade_risk_mode="SMALL")
    normal = calculate_position_size(100.0, 95.0, portfolio_size=10_000.0, trade_risk_mode="NORMAL")
    aggressive = calculate_position_size(100.0, 95.0, portfolio_size=10_000.0, trade_risk_mode="AGGRESSIVE")

    assert tiny["max_capital_risk"] == 25.0
    assert small["max_capital_risk"] == 50.0
    assert normal["max_capital_risk"] == 100.0
    assert aggressive["max_capital_risk"] == 200.0
    assert tiny["suggested_shares"] < small["suggested_shares"] < normal["suggested_shares"] < aggressive["suggested_shares"]


def test_position_sizing_does_not_decide_trade_outcome():
    result = calculate_position_size(100.0, 95.0, trade_risk_mode="NORMAL")

    assert "decision" not in result
    assert "confidence" not in result


def test_signal_position_size_uses_decision_trade_risk_mode():
    signal = {
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 95.0,
        },
        "v3_decision": {
            "trade_risk_mode": "SMALL",
        },
    }

    result = calculate_signal_position_size(signal, portfolio_size=10_000.0)

    assert result["trade_risk_mode"] == "SMALL"
    assert result["max_capital_risk"] == 50.0
    assert result["suggested_shares"] == 10


def test_signal_position_size_uses_decision_sizing_input_when_present():
    signal = {
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 80.0,
        },
        "v3_decision": {
            "trade_risk_mode": "NORMAL",
            "sizing_input": {
                "decision_entry": 101.0,
                "decision_stop": 96.0,
            },
        },
    }

    result = calculate_signal_position_size(signal, portfolio_size=10_000.0)

    assert result["valid"] is True
    assert result["risk_per_share"] == 5.0
    assert result["suggested_shares"] == 20
    assert result["estimated_position_value"] == 2020.0


def test_signal_position_size_no_trade_decision_returns_disabled_zero_position():
    signal = {
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 95.0,
        },
        "v3_decision": {
            "trade_risk_mode": "NO_TRADE",
        },
    }

    result = calculate_signal_position_size(signal, portfolio_size=10_000.0)

    assert result["sizing_mode"] == "disabled"
    assert result["trade_risk_mode"] == "NO_TRADE"
    assert result["suggested_shares"] == 0
    assert result["max_capital_risk"] == 0.0
    assert result["max_loss"] == 0.0


def test_signal_position_size_unknown_trade_risk_mode_does_not_create_position():
    signal = {
        "trade_plan": {
            "entry": 100.0,
            "stop_loss": 95.0,
        },
        "v3_decision": {
            "trade_risk_mode": "OVERSIZED",
        },
    }

    result = calculate_signal_position_size(signal, portfolio_size=10_000.0)

    assert result["valid"] is False
    assert result["sizing_mode"] in {"invalid_input", "disabled"}
    assert result["suggested_shares"] == 0
    assert result["max_capital_risk"] == 0.0
    assert result["max_loss"] == 0.0
