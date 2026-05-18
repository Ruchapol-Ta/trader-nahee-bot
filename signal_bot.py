# signal_bot.py — Main entry point + Scheduler.
#
# Fix #9  — removed unused `format_signal_message` / `format_summary_message`
#   imports; send_signals now owns formatter access internally.
# Fix #13 — every failure path sends a Telegram alert so silent breakage
#   can't cost us days of signals.
# Fix #18 — file logging with daily rotation (see logging_config).
# Fix #19 — misfire grace lifted to MISFIRE_GRACE_SEC (1 h) with coalesce=True.
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

from config import (
    SCHEDULE_HOUR, SCHEDULE_MINUTE, TIMEZONE, MISFIRE_GRACE_SEC,
)
from logging_config import setup_logging
from telegram_sender import build_telegram_rollout_dry_run_checklist, send_error_alert
from v2_engine import run_v2_scan

setup_logging()
logger = logging.getLogger(__name__)


def _yes_no(value: object) -> str:
    return "yes" if bool(value) else "no"


def format_telegram_rollout_checklist(checklist: dict) -> str:
    """Format the Telegram dry-run checklist without including secret values."""
    lines = [
        "Telegram Rollout Dry Run",
        f"Current mode: {checklist.get('mode') or 'legacy'}",
        f"Token present: {_yes_no(checklist.get('required_token_present'))}",
        f"Required chat id key: {checklist.get('required_chat_id_name') or 'none'}",
        f"Required chat id present: {_yes_no(checklist.get('required_chat_id_present'))}",
        f"Legacy fallback active: {_yes_no(checklist.get('legacy_fallback_active'))}",
        f"Prod fallback blocked: {_yes_no(checklist.get('explicit_prod_blocks_legacy_fallback'))}",
        f"Test mode requires prod chat id: {_yes_no(checklist.get('test_mode_requires_telegram_prod_chat_id'))}",
        f"Preview mode requires prod chat id: {_yes_no(checklist.get('preview_mode_requires_telegram_prod_chat_id'))}",
        f"V3 preview formatting available: {_yes_no(checklist.get('v3_preview_format_available_without_prod_rollout'))}",
        f"Overall readiness: {'ready' if checklist.get('ready') else 'not ready'}",
    ]
    errors = checklist.get("errors") or []
    if errors:
        lines.append("Errors:")
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines)


def run_scan() -> None:
    """Run the full EOD pipeline. Any failure is surfaced via Telegram."""
    start = datetime.now()
    logger.info("=" * 50)
    logger.info("[Bot] Starting EOD scan...")
    logger.info("=" * 50)

    try:
        result = run_v2_scan(debug="--debug-v2" in sys.argv)
    except Exception as e:
        logger.error(f"[Bot] Scan pipeline error: {e}", exc_info=True)
        send_error_alert(f"Scan pipeline error: {type(e).__name__}: {e}")
        return

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(
        f"[Bot] V2 scan complete in {elapsed:.1f}s — "
        f"{result.get('messages_sent', 0)} messages sent"
    )


def main() -> None:
    """
    Entry point.
      --telegram-rollout-check : print Telegram rollout dry-run checklist.
      --run-now : execute once and exit.
      default   : schedule daily at SCHEDULE_HOUR:SCHEDULE_MINUTE (TIMEZONE).
    """
    if "--telegram-rollout-check" in sys.argv:
        print(format_telegram_rollout_checklist(build_telegram_rollout_dry_run_checklist()))
        return

    if "--run-now" in sys.argv:
        logger.info("[Bot] --run-now flag detected, executing immediately")
        run_scan()
        return

    tz = pytz.timezone(TIMEZONE)
    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_scan,
        trigger=CronTrigger(
            hour=SCHEDULE_HOUR, minute=SCHEDULE_MINUTE, timezone=tz
        ),
        id="eod_scan",
        name="EOD Signal Scan",
        misfire_grace_time=MISFIRE_GRACE_SEC,
        coalesce=True,
    )

    logger.info(
        f"[Bot] Scheduler started — daily at "
        f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} {TIMEZONE}"
    )
    logger.info("[Bot] Press Ctrl+C to stop")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("[Bot] Scheduler stopped")


if __name__ == "__main__":
    main()
