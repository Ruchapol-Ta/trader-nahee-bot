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

from formatter import format_signal_message, format_summary_message

load_dotenv()
logger = logging.getLogger(__name__)

_TELEGRAM_API_BASE = "https://api.telegram.org"


def _get_credentials() -> tuple[str | None, str | None]:
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN"),
        os.environ.get("TELEGRAM_CHAT_ID"),
    )


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
        logger.error("[Telegram] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID in .env")
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
