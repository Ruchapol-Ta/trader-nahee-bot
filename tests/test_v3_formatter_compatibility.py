import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from message_formatter import format_trade_signal_message


def _signal(**overrides):
    data = {
        "ticker": "AAPL",
        "setup_type": "VCP Breakout",
        "grade": "A+",
        "score": 91,
        "close": 100.0,
        "trade_plan": {
            "entry": 100.0,
            "buy_stop": 101.1,
            "stop_loss": 93.53,
            "target_1": 116.18,
            "target_2": 125.88,
            "expected_rr": 2.5,
            "position_size": "Portfolio size required",
            "holding_style": "Swing: 3 trading days to 8 weeks; trail with 10EMA/20EMA",
        },
        "pass_reasons": [
            "market regime bullish",
            "trend structure bullish",
            "outperformed SPY",
            "breakout above pivot",
        ],
        "invalid_condition": "None",
        "market_regime": "Bullish market regime",
    }
    data.update(overrides)
    return data


def test_v2_trade_message_is_exactly_unchanged_without_v3_decision(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")

    message = format_trade_signal_message(_signal())

    assert message == "\n".join([
        "📈 AAPL - VCP Breakout",
        "🏛 Market: Bullish market regime",
        "🏅 A+ | Score 91",
        "Price: $100.00",
        "",
        "🟢 Entry: $100.00 | Buy stop: $101.10",
        "🔴 Stop: $93.53",
        "🎯 T1: $116.18 | T2: $125.88",
        "⚖️ R:R: 2.5R",
        "Position size: Portfolio size required",
        "",
        "Key reasons:",
        "• market regime bullish",
        "• trend structure bullish",
        "• outperformed SPY",
        "• breakout above pivot",
        "",
        "⚠️ Invalid: None",
        "Holding: Swing: 3 trading days to 8 weeks; trail with 10EMA/20EMA",
        "Timestamp: 2026-05-09 16:00 EDT",
    ])


def test_v3_section_renders_only_when_valid_v3_decision_exists(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    signal = _signal(
        v3_decision={
            "decision": "ENTER",
            "confidence": "HIGH",
            "main_reason": "High-quality breakout with acceptable risk.",
            "supporting_reasons": ["A+ grade", "Actual breakout"],
            "risk_warnings": ["Respect the stop"],
            "next_action": "Place buy stop above trigger.",
        },
        v3_position_size={
            "valid": True,
            "suggested_shares": 15,
            "max_loss": 96.75,
            "risk_mode": "normal",
        },
    )

    message = format_trade_signal_message(signal)

    assert "Decision: ENTER" in message
    assert "Confidence: HIGH" in message
    assert "Risk mode: normal" in message
    assert "Position size: 15 shares | Max loss: $96.75" in message
    assert "Why: High-quality breakout with acceptable risk." in message
    assert "Watch out: Respect the stop" in message
    assert "Next action: Place buy stop above trigger." in message


def test_invalid_v3_decision_does_not_render_section(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")

    message = format_trade_signal_message(_signal(v3_decision={"decision": "ENTER"}))

    assert "Decision: ENTER" not in message


def test_v3_free_text_is_escaped_for_telegram_markdown(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        v3_decision={
            "decision": "WAIT",
            "confidence": "MEDIUM",
            "main_reason": "Needs _clean_ trigger with *volume* and [news] clear.",
            "supporting_reasons": [],
            "risk_warnings": ["Avoid `gap` chase"],
            "next_action": "Wait for pivot_100 confirmation.",
        },
    ))

    assert "Needs \\_clean\\_ trigger with \\*volume\\* and \\[news] clear." in message
    assert "Avoid \\`gap\\` chase" in message
    assert "pivot\\_100" in message
