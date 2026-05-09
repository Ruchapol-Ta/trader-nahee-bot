# message_formatter.py - concise V2 Telegram messages.
import logging
from datetime import datetime

import pytz

from config import MARKET_TIMEZONE

logger = logging.getLogger(__name__)
_MARKET_TZ = pytz.timezone(MARKET_TIMEZONE)


def _timestamp() -> str:
    """Return the current market-time timestamp for Telegram messages."""
    try:
        return datetime.now(_MARKET_TZ).strftime("%Y-%m-%d %H:%M %Z")
    except Exception as e:
        logger.warning(f"[FormatterV2] Timestamp failed: {e}")
        return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def format_market_summary(market_regime: dict, stats: dict | None = None) -> str:
    """Format the V2 market-regime summary message."""
    try:
        is_valid = bool(market_regime.get("is_valid"))
        status = "🟢 Valid" if is_valid else "⚠️ Invalid"
        lines = [
            "Signal Bot V2",
            f"🏛 Market regime: {status}",
            f"Summary: {market_regime.get('summary', 'Unknown')}",
        ]
        invalid_reasons = market_regime.get("invalid_reasons") or []
        if invalid_reasons:
            lines.append("⚠️ Invalid reasons: " + "; ".join(invalid_reasons[:4]))
        if stats:
            lines.append(
                f"Scanned: {stats.get('scanned', 0)} | "
                f"Liquidity: {stats.get('liquidity_passed', 0)} | "
                f"Setups: {stats.get('setup_passed', 0)}"
            )
        lines.append(f"Timestamp: {_timestamp()}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[FormatterV2] Market summary failed: {e}", exc_info=True)
        return "Signal Bot V2\nMarket regime: Invalid\nSummary: formatter error"


def format_trade_signal_message(signal: dict) -> str:
    """Format one concise A+/A V2 trade setup alert."""
    try:
        if _valid_v3_decision(signal.get("v3_decision")):
            return _format_v3_trade_signal_message(signal)

        plan = signal["trade_plan"]
        reasons = signal.get("pass_reasons", [])[:4]
        reason_lines = [f"• {reason}" for reason in reasons] or ["• No reason supplied"]
        lines = [
            f"📈 {signal['ticker']} - {signal.get('setup_type', 'VCP Breakout')}",
            f"🏛 Market: {signal.get('market_regime', 'Unknown')}",
            f"🏅 {signal['grade']} | Score {signal['score']}",
            f"Price: ${float(signal['close']):.2f}",
            "",
            f"🟢 Entry: ${float(plan['entry']):.2f} | Buy stop: ${float(plan['buy_stop']):.2f}",
            f"🔴 Stop: ${float(plan['stop_loss']):.2f}",
            f"🎯 T1: ${float(plan['target_1']):.2f} | T2: ${float(plan['target_2']):.2f}",
            f"⚖️ R:R: {float(plan['expected_rr']):.1f}R",
            f"Position size: {plan.get('position_size', 'Portfolio size required')}",
            "",
            "Key reasons:",
            *reason_lines,
            "",
            f"⚠️ Invalid: {signal.get('invalid_condition', 'None')}",
            f"Holding: {plan.get('holding_style', 'Swing: 3 trading days to 8 weeks')}",
            f"Timestamp: {_timestamp()}",
        ]
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[FormatterV2] Trade signal failed: {e}", exc_info=True)
        return f"Signal Bot V2\nFormatter error: {type(e).__name__}"


def _valid_v3_decision(decision: object) -> bool:
    """Return True when a V3 decision has the required display fields."""
    if not isinstance(decision, dict):
        return False
    required = {
        "decision",
        "confidence",
        "main_reason",
        "supporting_reasons",
        "risk_warnings",
        "next_action",
    }
    return required.issubset(decision)


def _telegram_markdown_text(value: object) -> str:
    """Escape dynamic text for Telegram's legacy Markdown parse mode."""
    text = str(value)
    for char in ["\\", "_", "*", "[", "`"]:
        text = text.replace(char, f"\\{char}")
    return text


def _display_decision(value: object) -> str:
    """Return trader-facing decision labels before Markdown escaping."""
    text = str(value)
    if text == "WATCHLIST_ONLY":
        return "WATCHLIST ONLY"
    return _telegram_markdown_text(text)


def _v2_reason_lines(signal: dict) -> list[str]:
    """Return non-empty V2 reason bullets for V3 display."""
    reasons = []
    for reason in signal.get("pass_reasons", [])[:4]:
        text = str(reason).strip() if reason is not None else ""
        if text:
            reasons.append(f"• {_telegram_markdown_text(text)}")
    return reasons


def _format_v3_section(signal: dict) -> list[str]:
    """Format optional V3 decision guidance without changing plain V2 output."""
    decision = signal.get("v3_decision")
    if not _valid_v3_decision(decision):
        return []

    position = signal.get("v3_position_size") or {}
    lines = [
        f"Trade decision: {_display_decision(decision.get('decision'))}",
        f"Confidence: {_telegram_markdown_text(decision.get('confidence'))}",
    ]
    if position:
        lines.append(f"Risk mode: {_telegram_markdown_text(position.get('risk_mode', 'normal'))}")
        if position.get("valid"):
            lines.append(
                f"Position size: {position.get('suggested_shares')} shares | "
                f"Max loss: ${float(position.get('max_loss', 0.0)):.2f}"
            )
        else:
            reason = _telegram_markdown_text(position.get("reason", "invalid inputs"))
            lines.append(f"Position size: unavailable ({reason})")
    lines.append(f"Main reason: {_telegram_markdown_text(decision.get('main_reason'))}")
    warnings = decision.get("risk_warnings") or []
    if warnings:
        lines.append("Risk warnings: " + "; ".join(_telegram_markdown_text(item) for item in warnings[:3]))
    lines.append(f"What to do next: {_telegram_markdown_text(decision.get('next_action'))}")
    return lines


def _format_v3_trade_signal_message(signal: dict) -> str:
    """Format a V3-first trade decision alert while preserving V2 source context."""
    plan = signal["trade_plan"]
    reason_lines = _v2_reason_lines(signal)
    decision = signal["v3_decision"]

    lines = [
        f"📈 {signal['ticker']} - {signal.get('setup_type', 'VCP Breakout')}",
        *_format_v3_section(signal),
        "",
        f"🏛 Market: {signal.get('market_regime', 'Unknown')}",
        f"🏅 {signal['grade']} | Score {signal['score']}",
        f"Price: ${float(signal['close']):.2f}",
        "",
    ]

    if decision.get("decision") == "AVOID":
        lines.append("V2 setup levels, not an entry recommendation.")

    lines.extend([
        f"🟢 Entry: ${float(plan['entry']):.2f} | Buy stop: ${float(plan['buy_stop']):.2f}",
        f"🔴 Stop: ${float(plan['stop_loss']):.2f}",
        f"⚖️ R:R: {float(plan['expected_rr']):.1f}R",
        (
            f"🎯 Upside scenario 1: ${float(plan['target_1']):.2f} | "
            f"Upside scenario 2: ${float(plan['target_2']):.2f}"
        ),
        f"Position size: {plan.get('position_size', 'Portfolio size required')}",
    ])

    if reason_lines:
        lines.extend(["", "Why V2 liked it:", *reason_lines])

    invalid_condition = signal.get("invalid_condition")
    if invalid_condition and str(invalid_condition).strip().lower() != "none":
        lines.extend(["", f"⚠️ Invalid: {_telegram_markdown_text(invalid_condition)}"])

    lines.extend([
        f"Holding: {plan.get('holding_style', 'Swing: 3 trading days to 8 weeks')}",
        f"Timestamp: {_timestamp()}",
    ])
    return "\n".join(lines)


def format_watchlist_summary(watchlist: list[dict], market_regime: dict) -> str:
    """Format B-grade setups as a compact watchlist summary."""
    try:
        lines = [
            "📋 Signal Bot V2 - B Watchlist",
            f"🏛 Market: {market_regime.get('summary', 'Unknown')}",
        ]
        if not watchlist:
            lines.append("No B setups today.")
        else:
            for item in sorted(watchlist, key=lambda value: value.get("score", 0), reverse=True):
                marker = "👀" if item.get("is_near_breakout") else "📈"
                lines.append(f"{marker} {item['ticker']} | {item['grade']} | {item['score']}")
        lines.append(f"Timestamp: {_timestamp()}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"[FormatterV2] Watchlist summary failed: {e}", exc_info=True)
        return "Signal Bot V2 - B watchlist\nFormatter error"
