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
from telegram_sender import send_error_alert
from v2_engine import run_v2_scan

setup_logging()
logger = logging.getLogger(__name__)


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
      --run-now : execute once and exit.
      default   : schedule daily at SCHEDULE_HOUR:SCHEDULE_MINUTE (TIMEZONE).
    """
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
