# telegram_sender.py — Telegram Bot API integration.
#
# Fix #1  (Critical) — never log the bot token. The token is redacted in any
#   exception/response text before it reaches the logger.
# Fix #10 — send_signals imports the formatter directly instead of having the
#   caller pass a module object.
# Fix #12 — empty-signals branch returns 1 when the placeholder was delivered
#   (consistent with "messages actually sent").
# Fix #16 — credentials and URL are read at call time so .env changes and
#   deferred loading both work correctly.
# Additional: transient 5xx / timeout retries with exponential backoff.
import logging
import os
import time

import requests
from dotenv import load_dotenv

import config as runtime_config
from formatter import format_signal_message, format_summary_message
from message_formatter import (
    format_market_summary,
    format_trade_signal_message,
    format_watchlist_summary,
)

load_dotenv()
logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"


def _target_mode() -> str:
    return (os.environ.get("TELEGRAM_TARGET_MODE") or "").strip().lower()


def check_limited_live_rollout_readiness() -> dict:
    """Validate Telegram routing prerequisites without sending anything."""
    target_mode = _target_mode()
    errors: list[str] = []

    if target_mode == "prod":
        if not os.environ.get("TELEGRAM_BOT_TOKEN"):
            errors.append("TELEGRAM_BOT_TOKEN is required for prod target mode")
        if not os.environ.get("TELEGRAM_PROD_CHAT_ID"):
            errors.append(
                "TELEGRAM_PROD_CHAT_ID is required when TELEGRAM_TARGET_MODE=prod; "
                "TELEGRAM_CHAT_ID is not used as fallback"
            )
        return {
            "ready": not errors,
            "target_mode": target_mode,
            "is_live_rollout": True,
            "errors": errors,
        }

    if target_mode in {"test", "preview"}:
        return {
            "ready": True,
            "target_mode": target_mode,
            "is_live_rollout": False,
            "errors": [],
        }

    if target_mode:
        return {
            "ready": False,
            "target_mode": target_mode,
            "is_live_rollout": False,
            "errors": ["TELEGRAM_TARGET_MODE must be 'test', 'preview', or 'prod'"],
        }

    return {
        "ready": False,
        "target_mode": "",
        "is_live_rollout": False,
        "errors": ["TELEGRAM_TARGET_MODE=prod is required for limited live rollout"],
    }


def build_telegram_rollout_dry_run_checklist() -> dict:
    """Build a safe Telegram rollout checklist without sending anything."""
    target_mode = _target_mode()
    mode = target_mode or "legacy"
    token_present = bool(os.environ.get("TELEGRAM_BOT_TOKEN"))
    legacy_chat_present = bool(os.environ.get("TELEGRAM_CHAT_ID"))
    test_chat_present = bool(os.environ.get("TELEGRAM_TEST_CHAT_ID"))
    prod_chat_present = bool(os.environ.get("TELEGRAM_PROD_CHAT_ID"))

    required_chat_id_name = None
    required_chat_id_present = False
    errors: list[str] = []

    if not token_present:
        errors.append("TELEGRAM_BOT_TOKEN is missing")

    if target_mode == "prod":
        required_chat_id_name = "TELEGRAM_PROD_CHAT_ID"
        required_chat_id_present = prod_chat_present
        if not prod_chat_present:
            errors.append("TELEGRAM_PROD_CHAT_ID is required for explicit prod mode")
    elif target_mode in {"test", "preview"}:
        required_chat_id_name = "TELEGRAM_TEST_CHAT_ID"
        required_chat_id_present = test_chat_present
        if not test_chat_present:
            errors.append(f"TELEGRAM_TEST_CHAT_ID is required for {target_mode} mode")
    elif target_mode:
        errors.append("TELEGRAM_TARGET_MODE must be 'test', 'preview', or 'prod'")
    else:
        required_chat_id_name = "TELEGRAM_CHAT_ID"
        required_chat_id_present = legacy_chat_present
        if not legacy_chat_present:
            errors.append("TELEGRAM_CHAT_ID is required when TELEGRAM_TARGET_MODE is unset")

    return {
        "ready": not errors,
        "target_mode": target_mode,
        "mode": mode,
        "required_token_present": token_present,
        "required_chat_id_name": required_chat_id_name,
        "required_chat_id_present": required_chat_id_present,
        "legacy_mode_active": target_mode == "",
        "legacy_fallback_allowed": target_mode == "",
        "legacy_fallback_active": target_mode == "" and legacy_chat_present,
        "explicit_prod_requires_telegram_prod_chat_id": target_mode == "prod",
        "explicit_prod_blocks_legacy_fallback": target_mode == "prod",
        "test_mode_requires_telegram_prod_chat_id": False,
        "preview_mode_requires_telegram_prod_chat_id": False,
        "v3_preview_format_available_without_prod_rollout": bool(
            hasattr(runtime_config, "ENABLE_V3_TELEGRAM_FORMAT")
            and callable(format_market_summary)
            and callable(format_trade_signal_message)
            and callable(format_watchlist_summary)
        ),
        "errors": errors,
    }


def _get_credentials() -> tuple[str | None, str | None]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    target_mode = _target_mode()

    if target_mode in {"test", "preview"}:
        return token, os.environ.get("TELEGRAM_TEST_CHAT_ID")
    if target_mode == "prod":
        return token, os.environ.get("TELEGRAM_PROD_CHAT_ID")
    if target_mode:
        return token, None

    return token, os.environ.get("TELEGRAM_CHAT_ID")


def _missing_credentials_message() -> str:
    target_mode = _target_mode()
    if target_mode in {"test", "preview"}:
        return f"[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_TEST_CHAT_ID for {target_mode} target mode"
    if target_mode == "prod":
        return "[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_PROD_CHAT_ID for prod target mode"
    if target_mode:
        return "[Telegram] TELEGRAM_TARGET_MODE must be 'test', 'preview', or 'prod'"
    return "[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env"


def _redact(text: str, token: str | None) -> str:
    """Strip the token from any string before logging it."""
    if not token:
        return text
    return text.replace(token, "***TOKEN_REDACTED***")


def send_message(
    text: str,
    parse_mode: str = "Markdown",
    max_retries: int = 3,
) -> bool:
    """
    Send one message to the configured chat. Retries transient failures
    (5xx, 429, timeouts) with exponential backoff. Token never appears in
    logs — not even indirectly via exception messages.
    """
    token, chat_id = _get_credentials()
    if not token or not chat_id:
        logger.error(_missing_credentials_message())
        return False

    url = f"{_TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200 and resp.json().get("ok"):
                return True
            # 4xx other than 429 — permanent client error, don't retry
            if 400 <= resp.status_code < 500 and resp.status_code != 429:
                logger.error(
                    f"[Telegram] HTTP {resp.status_code}: "
                    f"{_redact(resp.text[:200], token)}"
                )
                return False
            logger.warning(
                f"[Telegram] Attempt {attempt}/{max_retries}: "
                f"HTTP {resp.status_code}"
            )
        except requests.exceptions.Timeout:
            logger.warning(
                f"[Telegram] Attempt {attempt}/{max_retries}: request timeout"
            )
        except requests.exceptions.RequestException as e:
            logger.warning(
                f"[Telegram] Attempt {attempt}/{max_retries}: "
                f"{_redact(str(e), token)}"
            )

        if attempt < max_retries:
            time.sleep(0.5 * (2 ** (attempt - 1)))

    logger.error("[Telegram] Failed after retries")
    return False


def send_error_alert(summary: str) -> bool:
    """Convenience wrapper for scheduled-run failure notifications (Fix #13)."""
    return send_message(f"🚨 *Scan Failed*\n\n`{summary}`")


def send_signals(signals: list[dict]) -> int:
    """
    Send the summary header + one message per signal.
    Returns the number of messages successfully delivered.
    """
    if not signals:
        logger.info("[Telegram] No signals to send")
        ok = send_message(
            "📊 *Signal Bot*\n\n"
            "No signals found today. Market may be ranging. 💤"
        )
        return 1 if ok else 0

    sent = 0
    if send_message(format_summary_message(signals)):
        sent += 1

    for signal in signals:
        if send_message(format_signal_message(signal)):
            sent += 1
        else:
            logger.warning(
                f"[Telegram] Failed to send signal for {signal['ticker']}"
            )

    logger.info(f"[Telegram] Delivered {sent}/{len(signals) + 1} messages")
    return sent


def send_v2_market_summary(market_regime: dict, stats: dict | None = None) -> int:
    """Send only the V2 market-regime summary."""
    try:
        ok = send_message(format_market_summary(market_regime, stats))
        logger.info(f"[Telegram] V2 market summary delivered={ok}")
        return 1 if ok else 0
    except Exception as e:
        logger.error(f"[Telegram] V2 market summary failed: {e}", exc_info=True)
        return 0


def send_v2_report(
    market_regime: dict,
    trade_signals: list[dict],
    watchlist: list[dict],
    stats: dict,
) -> int:
    """Send the V2 scan summary, A+/A trade alerts, and B watchlist summary."""
    try:
        sent = 0
        if send_message(format_market_summary(market_regime, stats)):
            sent += 1

        for signal in trade_signals:
            if send_message(format_trade_signal_message(signal)):
                sent += 1
            else:
                logger.warning(
                    f"[Telegram] Failed to send V2 signal for {signal.get('ticker')}"
                )

        if watchlist:
            if send_message(format_watchlist_summary(watchlist, market_regime)):
                sent += 1

        expected = 1 + len(trade_signals) + (1 if watchlist else 0)
        logger.info(f"[Telegram] V2 delivered {sent}/{expected} messages")
        return sent
    except Exception as e:
        logger.error(f"[Telegram] V2 report failed: {e}", exc_info=True)
        return 0
