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

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: ENTER")
    assert "Decision: ENTER" not in message
    assert "Trade decision: ENTER" in message
    assert "Confidence: HIGH" in message
    assert "Risk mode: normal" in message
    assert "Position size: 15 shares | Max loss: $96.75" in message
    assert "Main reason: High-quality breakout with acceptable risk." in message
    assert "Risk warnings: Respect the stop" in message
    assert "What to do next: Place buy stop above trigger." in message
    assert message.index("🟢 Entry: $100.00 | Buy stop: $101.10") < message.index("🎯 Upside scenario 1")
    assert message.index("🔴 Stop: $93.53") < message.index("🎯 Upside scenario 1")
    assert message.index("⚖️ R:R: 2.5R") < message.index("🎯 Upside scenario 1")
    assert "Upside scenario 1: $116.18 | Upside scenario 2: $125.88" in message
    assert "🎯 T1:" not in message
    assert "Why V2 liked it:" in message
    assert "Key reasons:" not in message
    assert "⚠️ Invalid: None" not in message
    assert message.index("Trade decision: ENTER") < message.index("🏅 A+ | Score 91")


def test_invalid_v3_decision_does_not_render_section(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")

    message = format_trade_signal_message(_signal(v3_decision={"decision": "ENTER"}))

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


def test_v3_reason_bullets_are_escaped_for_telegram_markdown(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        pass_reasons=[
            "clean_breakout",
            "volume *expansion*",
            "relative [strength] confirmed",
            "avoid `gap` chase",
        ],
        v3_decision={
            "decision": "WAIT",
            "confidence": "MEDIUM",
            "main_reason": "Setup is constructive.",
            "supporting_reasons": [],
            "risk_warnings": [],
            "next_action": "Wait for confirmation.",
        },
    ))

    assert "• clean\\_breakout" in message
    assert "• volume \\*expansion\\*" in message
    assert "• relative \\[strength] confirmed" in message
    assert "• avoid \\`gap\\` chase" in message


def test_v3_wait_trade_alert_uses_trader_friendly_labels(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        v3_decision={
            "decision": "WAIT",
            "confidence": "MEDIUM",
            "main_reason": "Setup is near the breakout trigger but has not confirmed.",
            "supporting_reasons": ["near breakout", "constructive base"],
            "risk_warnings": [],
            "next_action": "Wait for breakout above pivot with acceptable volume.",
        },
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: WAIT")
    assert "Main reason: Setup is near the breakout trigger but has not confirmed." in message
    assert "Risk warnings:" not in message
    assert "What to do next: Wait for breakout above pivot with acceptable volume." in message
    assert "Why V2 liked it:" in message


def test_v3_watchlist_only_trade_alert_is_primary(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        v3_decision={
            "decision": "WATCHLIST_ONLY",
            "confidence": "MEDIUM",
            "main_reason": "Setup is promising, but market regime is not supportive.",
            "supporting_reasons": ["relative strength remains constructive"],
            "risk_warnings": ["market regime is not supportive"],
            "next_action": "Keep on watchlist until market regime improves.",
        },
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: WATCHLIST ONLY")
    assert "WATCHLIST\\_ONLY" not in message
    assert "Main reason: Setup is promising, but market regime is not supportive." in message
    assert "Risk warnings: market regime is not supportive" in message
    assert "What to do next: Keep on watchlist until market regime improves." in message
    assert message.index("Trade decision: WATCHLIST ONLY") < message.index("🏅 A+ | Score 91")


def test_v3_avoid_trade_alert_demotes_v2_levels(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        v3_decision={
            "decision": "AVOID",
            "confidence": "LOW",
            "main_reason": "Stop distance is too wide for the V3 risk rules.",
            "supporting_reasons": ["trend structure bullish"],
            "risk_warnings": ["stop distance is excessive (13.0%)"],
            "next_action": "Avoid unless price tightens or a closer valid stop forms.",
        },
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: AVOID")
    assert "V2 setup levels, not an entry recommendation." in message
    assert "V2 setup levels, not an entry recommendation." in message.splitlines()
    assert "Risk warnings: stop distance is excessive (13.0%)" in message
    assert "⚠️ Invalid: None" not in message
    assert "Upside scenario 1: $116.18 | Upside scenario 2: $125.88" in message


def test_v3_trade_alert_omits_v2_reason_heading_when_reasons_are_empty(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    message = format_trade_signal_message(_signal(
        pass_reasons=["", "   ", None],
        v3_decision={
            "decision": "WAIT",
            "confidence": "MEDIUM",
            "main_reason": "Setup needs cleaner confirmation.",
            "supporting_reasons": [],
            "risk_warnings": [],
            "next_action": "Wait for better confirmation.",
        },
    ))

    assert "Why V2 liked it:" not in message
    assert "• No reason supplied" not in message
