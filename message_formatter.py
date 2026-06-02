# message_formatter.py - concise V2 Telegram messages.
import logging
from datetime import datetime, timezone

import pytz

from config import ENABLE_V3_TELEGRAM_FORMAT, MARKET_TIMEZONE

logger = logging.getLogger(__name__)
_MARKET_TZ = pytz.timezone(MARKET_TIMEZONE)


def _timestamp() -> str:
    """Return the current market-time timestamp for Telegram messages."""
    try:
        return datetime.now(_MARKET_TZ).strftime("%Y-%m-%d %H:%M %Z")
    except Exception as e:
        logger.warning(f"[FormatterV2] Timestamp failed: {e}")
        return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_market_summary(market_regime: dict, stats: dict | None = None) -> str:
    """Format the V2 market-regime summary message."""
    try:
        is_valid = bool(market_regime.get("is_valid"))
        status = "🟢 Valid" if is_valid else "⚠️ Invalid"
        title = "Signal Bot V3 Preview" if ENABLE_V3_TELEGRAM_FORMAT else "Signal Bot V2"
        lines = [
            title,
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
        if ENABLE_V3_TELEGRAM_FORMAT and _valid_v3_decision(signal.get("v3_decision")):
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
        "action_label",
        "main_reason",
        "supporting_reasons",
        "risk_warnings",
        "risk_flags",
        "wait_conditions",
        "invalidation",
        "next_action",
        "sizing_mode",
        "trade_risk_mode",
        "sizing_input",
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


def _number(value: object) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number
    except (TypeError, ValueError):
        return None


def _money(value: object) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return f"${number:.2f}"


def _pct(value: object) -> str | None:
    number = _number(value)
    if number is None:
        return None
    return f"{number * 100:.2f}%"


def _clean_mode(value: object) -> str:
    text = str(value or "").strip()
    labels = {
        "NO_TRADE": "No trade",
        "TINY": "Tiny",
        "SMALL": "Small",
        "NORMAL": "Normal",
        "AGGRESSIVE": "Aggressive",
        "mock_config": "configured sizing",
        "disabled": "disabled",
        "invalid_input": "invalid input",
    }
    return labels.get(text, text.replace("_", " ").strip().title() if text else "Unknown")


def _v2_reason_lines(signal: dict) -> list[str]:
    """Return non-empty V2 reason bullets for V3 display."""
    reasons = []
    for reason in signal.get("pass_reasons", [])[:4]:
        text = str(reason).strip() if reason is not None else ""
        if text:
            reasons.append(f"• {_telegram_markdown_text(text)}")
    return reasons


def _telegram_bullets(items: object, limit: int = 4) -> list[str]:
    """Return escaped bullet lines for non-empty list-like values."""
    if not isinstance(items, list):
        return []
    lines = []
    for item in items[:limit]:
        text = str(item).strip() if item is not None else ""
        if text:
            lines.append(f"• {_telegram_markdown_text(text)}")
    return lines


def _risk_flag_label(value: object) -> str:
    labels = {
        "POOR_RISK_REWARD": "R:R below V3 minimum",
        "NO_VOLUME_CONFIRMATION": "Volume confirmation missing",
        "GENERIC_SETUP_EVIDENCE": "Setup evidence is generic",
        "UNFAVORABLE_MARKET_REGIME": "Market regime not supportive",
        "WEAK_RELATIVE_STRENGTH": "Relative strength not confirmed",
        "WIDE_STOP": "Stop distance is wide",
        "STRUCTURAL_STOP_WIDE": "Structural base is deep; trading stop uses tactical risk.",
        "EXTENDED_ENTRY": "Entry is extended",
        "MISSING_ENTRY": "Entry missing",
        "MISSING_STOP": "Stop missing",
        "INVALID_STOP": "Stop is invalid",
        "MISSING_TARGETS": "Targets missing",
    }
    text = str(value)
    return labels.get(text, text.replace("_", " ").title())


def _risk_flag_labels(items: object, limit: int = 4) -> list[str]:
    if not isinstance(items, list):
        return []
    return [_telegram_markdown_text(_risk_flag_label(item)) for item in items[:limit] if item]


def _v3_risk_mode(decision: dict, position: dict) -> object:
    """Return the risk mode supplied by V3 sizing or decision output."""
    return (
        position.get("trade_risk_mode")
        or position.get("risk_mode")
        or decision.get("trade_risk_mode")
        or "normal"
    )


def _format_v3_position_line(decision: dict, position: dict) -> str | None:
    """Render sizing output only when position_sizing.py provided complete values."""
    if decision.get("trade_risk_mode") == "NO_TRADE":
        return None
    if position:
        if position.get("valid"):
            shares = position.get("suggested_shares")
            max_loss = position.get("max_loss")
            if shares is None or max_loss is None:
                return "Position size: unavailable (incomplete sizing result)"
            share_label = "share" if shares == 1 else "shares"
            return f"Position size: {shares} {share_label} | Max loss: ${float(max_loss):.2f}"
        reason = _telegram_markdown_text(position.get("reason", "invalid inputs"))
        return f"Position size: unavailable ({reason})"
    if decision.get("sizing_mode") == "disabled":
        return "Position size: unavailable"
    return None


def _format_v3_header(decision: dict) -> list[str]:
    """Format V3 decision headline fields."""
    lines = [
        f"Trade decision: {_display_decision(decision.get('decision'))}",
        f"Action: {_telegram_markdown_text(decision.get('action_label'))}",
        f"Confidence: {_telegram_markdown_text(decision.get('confidence'))}",
    ]
    if decision.get("risk_profile"):
        lines.append(f"Risk profile: {_telegram_markdown_text(decision.get('risk_profile'))}")
    return lines


def _format_v3_guidance(decision: dict) -> list[str]:
    """Format V3 explanation fields without inventing missing decision content."""
    decision_name = decision.get("decision")
    warnings = decision.get("risk_warnings") or []

    if decision_name == "WATCHLIST_ONLY":
        lines = ["Main reason: Setup is promising but not actionable yet."]
        lines.append(f"What to do next: {_telegram_markdown_text(decision.get('next_action'))}")
        return lines

    lines = [f"Main reason: {_telegram_markdown_text(decision.get('main_reason'))}"]

    if decision_name == "AVOID":
        invalidation_lines = _telegram_bullets(decision.get("invalidation"))
        if invalidation_lines:
            lines.extend(["Invalidation:", *invalidation_lines])
        return lines

    supporting_limit = 2 if decision_name == "WAIT" else 4
    supporting_reason_lines = _telegram_bullets(decision.get("supporting_reasons"), limit=supporting_limit)
    if supporting_reason_lines:
        lines.extend(["Supporting reasons:", *supporting_reason_lines])

    if warnings:
        lines.append("Risk warnings: " + "; ".join(_telegram_markdown_text(item) for item in warnings[:3]))
    else:
        flag_labels = _risk_flag_labels(decision.get("risk_flags") or [])
        if flag_labels:
            lines.append("Risk flags: " + "; ".join(flag_labels))

    wait_condition_lines = _telegram_bullets(decision.get("wait_conditions"))
    if wait_condition_lines:
        lines.extend(["Wait conditions:", *wait_condition_lines])

    invalidation_lines = _telegram_bullets(decision.get("invalidation"))
    if invalidation_lines:
        lines.extend(["Invalidation:", *invalidation_lines])

    lines.append(f"What to do next: {_telegram_markdown_text(decision.get('next_action'))}")
    return lines


def _format_v3_decision_levels(signal: dict, decision: dict) -> list[str]:
    plan = signal.get("trade_plan") or {}
    decision_name = decision.get("decision")
    if decision_name in {"WATCHLIST_ONLY", "AVOID"}:
        return []

    decision_entry = _money(decision.get("decision_entry") or decision.get("sizing_input", {}).get("decision_entry") or plan.get("buy_stop") or plan.get("entry"))
    buy_stop = _money(plan.get("buy_stop"))
    decision_stop = _money(decision.get("decision_stop") or decision.get("sizing_input", {}).get("decision_stop"))
    stop_distance = _pct(decision.get("decision_stop_distance_pct"))
    source = decision.get("decision_stop_source")
    source_text = f" ({_telegram_markdown_text(source)})" if source else ""

    if decision_name == "WAIT":
        lines = []
        if buy_stop or decision_entry:
            lines.append(f"Reference trigger: {buy_stop or decision_entry}")
        if decision_stop:
            distance_text = f" | {stop_distance}" if stop_distance else ""
            lines.append(f"Trading stop: {decision_stop}{source_text}{distance_text}")
        if stop_distance:
            lines.append(f"Stop distance: {stop_distance}")
        return lines

    lines = []
    if decision_entry or buy_stop:
        if buy_stop:
            lines.append(f"Decision entry: {decision_entry or buy_stop} | Buy stop: {buy_stop}")
        else:
            lines.append(f"Decision entry: {decision_entry}")
    if decision_stop:
        distance_text = f" | {stop_distance}" if stop_distance else ""
        lines.append(f"Trading stop: {decision_stop}{source_text}{distance_text}")
    structural_stop = _money(plan.get("structural_stop"))
    if structural_stop:
        structural_distance = _pct(plan.get("structural_stop_distance_pct"))
        suffix = f" | {structural_distance}" if structural_distance else ""
        lines.append(f"Structural stop: {structural_stop} (context only){suffix}")
    if stop_distance:
        lines.append(f"Stop distance: {stop_distance}")
    return lines


def _format_v3_section(signal: dict) -> list[str]:
    """Format optional V3 decision guidance without changing plain V2 output."""
    decision = signal.get("v3_decision")
    if not _valid_v3_decision(decision):
        return []
    return _format_v3_header(decision) + _format_v3_guidance(decision)


def _format_v3_trade_signal_message(signal: dict) -> str:
    """Format a V3-first trade decision alert while preserving V2 source context."""
    plan = signal["trade_plan"]
    decision = signal["v3_decision"]

    lines = [
        f"📈 {signal['ticker']} - {signal.get('setup_type', 'VCP Breakout')}",
        *_format_v3_header(decision),
        "",
        f"🏛 Market: {signal.get('market_regime', 'Unknown')}",
        f"🏅 {signal['grade']} | Score {signal['score']}",
        f"Price: ${float(signal['close']):.2f}",
        "",
    ]

    decision_name = decision.get("decision")
    level_lines = _format_v3_decision_levels(signal, decision)
    if level_lines:
        lines.extend(level_lines)
    if decision_name == "ENTER":
        lines.append(f"⚖️ R:R: {float(plan['expected_rr']):.1f}R")

    if decision.get("decision") == "ENTER":
        lines.append(
            f"🎯 Upside scenario 1: ${float(plan['target_1']):.2f} | "
            f"Upside scenario 2: ${float(plan['target_2']):.2f}"
        )

    position = signal.get("v3_position_size") or {}
    lines.append(f"Risk mode: {_telegram_markdown_text(_clean_mode(_v3_risk_mode(decision, position)))}")
    position_line = _format_v3_position_line(decision, position)
    if position_line:
        lines.append(position_line)

    lines.extend(["", *_format_v3_guidance(decision)])

    invalid_condition = signal.get("invalid_condition")
    if invalid_condition and str(invalid_condition).strip().lower() != "none":
        lines.extend(["", f"⚠️ Invalid: {_telegram_markdown_text(invalid_condition)}"])

    if decision_name == "ENTER":
        lines.append(f"Holding: {plan.get('holding_style', 'Swing: 3 trading days to 8 weeks')}")
    lines.append(f"Timestamp: {_timestamp()}")
    return "\n".join(lines)


def format_watchlist_summary(watchlist: list[dict], market_regime: dict) -> str:
    """Format B-grade setups as a compact watchlist summary."""
    try:
        title = (
            "📋 Signal Bot V3 Preview - B Watchlist"
            if ENABLE_V3_TELEGRAM_FORMAT
            else "📋 Signal Bot V2 - B Watchlist"
        )
        lines = [
            title,
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
