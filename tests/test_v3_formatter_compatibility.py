import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from message_formatter import format_market_summary, format_trade_signal_message


def _full_v3_decision(**overrides):
    data = {
        "decision": "ENTER",
        "confidence": "HIGH",
        "action_label": "Enter only on planned trigger",
        "main_reason": "High-quality breakout with acceptable risk.",
        "supporting_reasons": ["A+ grade", "Actual breakout"],
        "risk_warnings": ["Respect the stop"],
        "risk_flags": [],
        "wait_conditions": [],
        "invalidation": ["Exit or avoid if price violates the trading stop."],
        "next_action": "Enter only if the planned buy stop triggers and the trading stop remains valid.",
        "sizing_mode": "mock_config",
        "trade_risk_mode": "NORMAL",
        "sizing_input": {
            "entry": 101.1,
            "stop": 96.5,
            "decision_entry": 101.1,
            "decision_stop": 96.5,
        },
        "decision_entry": 101.1,
        "decision_stop": 96.5,
        "decision_stop_source": "tactical",
        "decision_stop_distance_pct": 0.0455,
        "risk_profile": "balanced",
        "enter_max_stop_pct": 0.10,
        "threshold_result": {
            "within_enter_stop": True,
            "within_balanced_tactical_enter_limit": True,
            "blocked_no_volume_confirmation": False,
            "blocked_extended_entry": False,
        },
    }
    data.update(overrides)
    return data


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
            "structural_stop": 93.53,
            "structural_stop_source": "pivot_low",
            "structural_stop_distance_pct": 0.065,
            "tactical_stop": 96.5,
            "tactical_stop_source": "contraction_low",
            "tactical_stop_distance_pct": 0.035,
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


def test_v3_market_summary_header_uses_v3_preview_label(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)

    message = format_market_summary(
        {"is_valid": True, "summary": "Bullish market regime", "invalid_reasons": []},
        {"scanned": 10, "liquidity_passed": 8, "setup_passed": 2},
    )

    assert message.startswith("Signal Bot V3 Preview")
    assert not message.startswith("Signal Bot V2")


def test_v2_market_summary_header_is_unchanged_when_v3_format_disabled(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", False)

    message = format_market_summary(
        {"is_valid": True, "summary": "Bullish market regime", "invalid_reasons": []},
        {"scanned": 10, "liquidity_passed": 8, "setup_passed": 2},
    )

    assert message == "\n".join([
        "Signal Bot V2",
        "🏛 Market regime: 🟢 Valid",
        "Summary: Bullish market regime",
        "Scanned: 10 | Liquidity: 8 | Setups: 2",
        "Timestamp: 2026-05-09 16:00 EDT",
    ])


def test_v3_section_renders_only_when_valid_v3_decision_exists(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    signal = _signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "suggested_shares": 15,
            "max_loss": 96.75,
            "trade_risk_mode": "NORMAL",
            "risk_mode": "normal",
        },
    )

    message = format_trade_signal_message(signal)

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: ENTER")
    assert "Decision: ENTER" not in message
    assert "Trade decision: ENTER" in message
    assert "Action: Enter only on planned trigger" in message
    assert "Confidence: HIGH" in message
    assert "Risk profile: balanced" in message
    assert "Risk mode: Normal" in message
    assert "Position size: 15 shares | Max loss: $96.75" in message
    assert "Main reason: High-quality breakout with acceptable risk." in message
    assert "Supporting reasons:" in message
    assert "• A+ grade" in message
    assert "Invalidation:" in message
    assert "• Exit or avoid if price violates the trading stop." in message
    assert "Risk warnings: Respect the stop" in message
    assert "What to do next: Enter only if the planned buy stop triggers and the trading stop remains valid." in message
    assert "Decision entry: $101.10 | Buy stop: $101.10" in message
    assert "Trading stop: $96.50 (tactical) | 4.55%" in message
    assert "Structural stop: $93.53 (context only) | 6.50%" in message
    assert "Stop distance: 4.55%" in message
    assert message.index("Decision entry: $101.10") < message.index("Position size: 15 shares")
    assert message.index("Trading stop: $96.50") < message.index("Position size: 15 shares")
    assert message.index("⚖️ R:R: 2.5R") < message.index("🎯 Upside scenario 1")
    assert "Upside scenario 1: $116.18 | Upside scenario 2: $125.88" in message
    assert "🎯 T1:" not in message
    assert "Why V2 liked it:" not in message
    assert "Key reasons:" not in message
    assert "⚠️ Invalid: None" not in message
    assert message.index("Trade decision: ENTER") < message.index("🏅 A+ | Score 91")


def test_v3_enter_shows_levels_before_sizing(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    signal = _signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "trade_risk_mode": "NORMAL",
            "suggested_shares": 15,
            "max_loss": 96.75,
        },
    )

    message = format_trade_signal_message(signal)

    assert "Action: Consider entry" not in message
    assert "Action: Enter only on planned trigger" in message
    assert message.index("Decision entry: $101.10 | Buy stop: $101.10") < message.index("Position size: 15 shares | Max loss: $96.75")
    assert message.index("Trading stop: $96.50 (tactical) | 4.55%") < message.index("Position size: 15 shares | Max loss: $96.75")
    assert message.index("Risk mode: Normal") < message.index("Position size: 15 shares | Max loss: $96.75")


def test_v3_malformed_valid_position_size_does_not_show_misleading_sizing(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "trade_risk_mode": "NORMAL",
        },
    ))

    assert "Position size: unavailable (incomplete sizing result)" in message
    assert "Position size: None shares" not in message
    assert "Max loss: $0.00" not in message


def test_v3_position_display_uses_trade_risk_mode_without_legacy_alias(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    signal = _signal(
        v3_decision=_full_v3_decision(trade_risk_mode="SMALL"),
        v3_position_size={
            "valid": True,
            "trade_risk_mode": "SMALL",
            "suggested_shares": 10,
            "max_loss": 50.0,
        },
    )

    message = format_trade_signal_message(signal)

    assert "Risk mode: Small" in message
    assert "Risk mode: normal" not in message
    assert "Position size: 10 shares | Max loss: $50.00" in message


def test_v3_position_size_uses_singular_share_for_one_share(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    signal = _signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "trade_risk_mode": "SMALL",
            "suggested_shares": 1,
            "max_loss": 38.63,
        },
    )

    message = format_trade_signal_message(signal)

    assert "Position size: 1 share | Max loss: $38.63" in message
    assert "Position size: 1 shares" not in message


def test_v3_enter_contextualizes_structural_stop_wide_flag(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            risk_flags=["STRUCTURAL_STOP_WIDE"],
            risk_warnings=[],
        ),
    ))

    assert "Structural base is deep; trading stop uses tactical risk." in message
    assert "Structural Stop Wide" not in message
    assert "Stop distance is wide" not in message


def test_v3_enter_does_not_show_raw_sizing_mode(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(v3_decision=_full_v3_decision()))

    assert "mock_config" not in message
    assert "disabled" not in message


def test_v3_wait_with_stop_inside_enter_limit_does_not_say_stop_is_wide(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup is near the breakout trigger but has not confirmed.",
            risk_flags=["NO_VOLUME_CONFIRMATION"],
            risk_warnings=[],
            wait_conditions=["Wait for breakout confirmation.", "Wait for volume confirmation."],
            next_action="Wait for breakout confirmation with acceptable volume.",
            trade_risk_mode="NO_TRADE",
            decision_stop_distance_pct=0.0455,
            threshold_result={
                "within_enter_stop": True,
                "blocked_no_volume_confirmation": True,
                "blocked_extended_entry": False,
            },
        ),
    ))

    assert "stop distance is wide" not in message.lower()
    assert "Stop distance is wide" not in message
    assert "Wait for volume confirmation." in message
    assert "Volume confirmation missing" in message


def test_v3_stop_display_omits_structural_percent_when_missing(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    signal = _signal(v3_decision=_full_v3_decision())
    signal["trade_plan"] = {
        **signal["trade_plan"],
        "structural_stop": 93.53,
        "structural_stop_distance_pct": None,
    }

    message = format_trade_signal_message(signal)

    assert "Trading stop: $96.50 (tactical) | 4.55%" in message
    assert "Structural stop: $93.53 (context only)" in message
    assert "Structural stop: $93.53 (context only) |" not in message


def test_v3_enter_includes_invalidation_and_next_action(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            invalidation=["Exit if price violates the tactical stop."],
            next_action="Place buy stop only if trigger remains valid.",
        ),
    ))

    assert "Invalidation:" in message
    assert "• Exit if price violates the tactical stop." in message
    assert "What to do next: Place buy stop only if trigger remains valid." in message


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


def test_partial_old_shape_v3_decision_does_not_render_when_v3_telegram_format_enabled(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)

    message = format_trade_signal_message(_signal(
        v3_decision={
            "decision": "ENTER",
            "confidence": "HIGH",
            "main_reason": "High-quality breakout with acceptable risk.",
            "supporting_reasons": ["A+ grade", "Actual breakout"],
            "risk_warnings": [],
            "next_action": "Place buy stop above trigger.",
        },
    ))

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


def test_full_shape_v3_decision_renders_when_v3_telegram_format_enabled(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)

    message = format_trade_signal_message(_signal(v3_decision=_full_v3_decision()))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: ENTER")
    assert "Main reason: High-quality breakout with acceptable risk." in message
    assert "What to do next: Enter only if the planned buy stop triggers and the trading stop remains valid." in message


def test_full_shape_v3_decision_does_not_render_when_v3_telegram_format_disabled(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", False)

    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "suggested_shares": 15,
            "max_loss": 96.75,
            "risk_mode": "normal",
        },
    ))

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
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Needs _clean_ trigger with *volume* and [news] clear.",
            supporting_reasons=[],
            risk_warnings=["Avoid `gap` chase"],
            wait_conditions=["Wait for pivot_100 confirmation."],
            next_action="Wait for pivot_100 confirmation.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert "Needs \\_clean\\_ trigger with \\*volume\\* and \\[news] clear." in message
    assert "Avoid \\`gap\\` chase" in message
    assert "pivot\\_100" in message


def test_v3_reason_bullets_are_escaped_for_telegram_markdown(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup is constructive.",
            supporting_reasons=[
                "clean_breakout",
                "volume *expansion*",
                "relative [strength] confirmed",
            ],
            risk_warnings=[],
            wait_conditions=["Wait for confirmation."],
            next_action="Wait for confirmation.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert "• clean\\_breakout" in message
    assert "• volume \\*expansion\\*" in message
    assert "relative \\[strength] confirmed" not in message


def test_v3_wait_trade_alert_uses_trader_friendly_labels(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup is near the breakout trigger but has not confirmed.",
            supporting_reasons=["near breakout", "constructive base"],
            risk_warnings=[],
            wait_conditions=["Breakout above pivot.", "Acceptable volume."],
            next_action="Wait for breakout above pivot with acceptable volume.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: WAIT")
    assert "Action: Wait for confirmation" in message
    assert "Risk mode: No trade" in message
    assert "Position size:" not in message
    assert "Decision entry:" not in message
    assert "Reference trigger: $101.10" in message
    assert "Trading stop: $96.50 (tactical) | 4.55%" in message
    assert "Wait conditions:" in message
    assert "• Breakout above pivot." in message
    assert "• Acceptable volume." in message
    assert "Main reason: Setup is near the breakout trigger but has not confirmed." in message
    assert "Risk warnings:" not in message
    assert "What to do next: Wait for breakout above pivot with acceptable volume." in message
    assert "Why V2 liked it:" not in message


def test_v3_watchlist_only_trade_alert_is_primary(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WATCHLIST_ONLY",
            confidence="MEDIUM",
            action_label="Keep on watchlist",
            main_reason="Setup is promising, but market regime is not supportive.",
            supporting_reasons=["relative strength remains constructive"],
            risk_warnings=["market regime is not supportive"],
            risk_flags=["UNFAVORABLE_MARKET_REGIME"],
            invalidation=["Avoid entries while market regime is unsupportive."],
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: WATCHLIST ONLY")
    assert "WATCHLIST\\_ONLY" not in message
    assert "Main reason: Setup is promising but not actionable yet." in message
    assert "Risk warnings:" not in message
    assert "What to do next: Keep on watchlist until the setup confirms a cleaner trigger." in message
    assert "market regime improves" not in message
    assert message.index("Trade decision: WATCHLIST ONLY") < message.index("🏅 A+ | Score 91")
    assert "Upside scenario 1:" not in message
    assert "🎯 T1:" not in message
    assert "🟢 Entry:" not in message
    assert "Decision entry:" not in message
    assert "Trading stop:" not in message
    assert "Buy stop:" not in message
    assert "🔴 Stop:" not in message
    assert "⚖️ R:R:" not in message
    assert "Holding:" not in message
    assert "Supporting reasons:" not in message
    assert "Why V2 liked it:" not in message


def test_v3_watchlist_only_uses_neutral_wording_when_market_text_conflicts(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        market_regime="Bullish market regime",
        pass_reasons=["market regime bullish", "trend structure bullish"],
        v3_decision=_full_v3_decision(
            decision="WATCHLIST_ONLY",
            confidence="MEDIUM",
            action_label="Keep on watchlist",
            main_reason="Setup is promising, but market regime is not supportive.",
            supporting_reasons=["market regime bullish", "trend structure bullish"],
            risk_warnings=["market regime is not supportive"],
            risk_flags=["UNFAVORABLE_MARKET_REGIME"],
            invalidation=["Avoid entries while market regime is unsupportive."],
            next_action="Keep on watchlist until the setup confirms a cleaner trigger.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert "🏛 Market: Bullish market regime" in message
    assert "Main reason: Setup is promising but not actionable yet." in message
    assert "market regime is not supportive" not in message
    assert "market regime bullish" not in message
    assert "Supporting reasons:" not in message
    assert "market regime improves" not in message


def test_v3_enter_next_action_no_longer_says_consider_entry(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            next_action="Enter only if the planned buy stop triggers and the defined stop remains valid.",
        ),
    ))

    assert "Consider entry" not in message
    assert "What to do next: Enter only if the planned buy stop triggers and the defined stop remains valid." in message


def test_v3_wait_labels_reference_levels_without_tradable_targets(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup is near the breakout trigger but has not confirmed.",
            supporting_reasons=["near breakout", "constructive base", "extra duplicate"],
            risk_warnings=[],
            risk_flags=["POOR_RISK_REWARD", "NO_VOLUME_CONFIRMATION"],
            wait_conditions=["Breakout above pivot.", "Acceptable volume."],
            invalidation=[],
            next_action="Wait for breakout above pivot with acceptable volume.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert "🎯 Upside scenario 1:" not in message
    assert "Reference upside:" not in message
    assert "Decision entry:" not in message
    assert "Reference trigger: $101.10" in message
    assert "Supporting reasons:" in message
    assert "• near breakout" in message
    assert "• constructive base" in message
    assert "extra duplicate" not in message
    assert "Risk flags: R:R below V3 minimum; Volume confirmation missing" in message
    assert "POOR\\_RISK\\_REWARD" not in message
    assert "NO\\_VOLUME\\_CONFIRMATION" not in message
    assert "Why V2 liked it:" not in message


def test_v3_normal_message_length_stays_reasonable(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(),
        v3_position_size={
            "valid": True,
            "trade_risk_mode": "NORMAL",
            "suggested_shares": 15,
            "max_loss": 96.75,
        },
    ))

    assert len(message) < 1800


def test_v3_avoid_trade_alert_demotes_v2_levels(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="AVOID",
            confidence="LOW",
            action_label="Avoid setup",
            main_reason="Stop distance is too wide for the V3 risk rules.",
            supporting_reasons=["trend structure bullish"],
            risk_warnings=["stop distance is excessive (13.0%)"],
            risk_flags=["WIDE_STOP"],
            invalidation=["The current stop distance exceeds V3 avoid limits."],
            next_action="Avoid unless price tightens or a closer valid stop forms.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert message.startswith("📈 AAPL - VCP Breakout\nTrade decision: AVOID")
    assert "V2 setup levels, not an entry recommendation." not in message
    assert "Risk warnings:" not in message
    assert "Invalidation:" in message
    assert "• The current stop distance exceeds V3 avoid limits." in message
    assert "⚠️ Invalid: None" not in message
    assert "Upside scenario 1:" not in message
    assert "🎯 T1:" not in message
    assert "Decision entry:" not in message
    assert "Trading stop:" not in message
    assert "Position size:" not in message
    assert "Holding:" not in message
    assert "Supporting reasons:" not in message
    assert "Why V2 liked it:" not in message


def test_v3_formatter_does_not_generate_missing_wait_or_invalidation_fields(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup needs cleaner confirmation.",
            supporting_reasons=[],
            risk_warnings=[],
            wait_conditions=[],
            invalidation=[],
            next_action="Wait for confirmation from the decision engine.",
            trade_risk_mode="NO_TRADE",
        ),
        v3_position_size={
            "valid": False,
            "trade_risk_mode": "NO_TRADE",
            "suggested_shares": 0,
            "max_loss": 0.0,
            "reason": "no trade recommended",
        },
    ))

    assert "Wait conditions:" not in message
    assert "Invalidation:" not in message
    assert "• Breakout above pivot." not in message


def test_v3_trade_alert_omits_v2_reason_heading_when_reasons_are_empty(monkeypatch):
    monkeypatch.setattr("message_formatter._timestamp", lambda: "2026-05-09 16:00 EDT")
    monkeypatch.setattr("message_formatter.ENABLE_V3_TELEGRAM_FORMAT", True)
    message = format_trade_signal_message(_signal(
        pass_reasons=["", "   ", None],
        v3_decision=_full_v3_decision(
            decision="WAIT",
            confidence="MEDIUM",
            action_label="Wait for confirmation",
            main_reason="Setup needs cleaner confirmation.",
            supporting_reasons=[],
            risk_warnings=[],
            wait_conditions=["Wait for better confirmation."],
            next_action="Wait for better confirmation.",
            trade_risk_mode="NO_TRADE",
        ),
    ))

    assert "Why V2 liked it:" not in message
    assert "• No reason supplied" not in message
