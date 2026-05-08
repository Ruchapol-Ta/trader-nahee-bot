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
from universe import get_full_universe, UniverseLoadError
from screener import screen_universe
from signals import filter_signals
from telegram_sender import send_signals, send_error_alert

setup_logging()
logger = logging.getLogger(__name__)


def run_scan() -> None:
    """Run the full EOD pipeline. Any failure is surfaced via Telegram."""
    start = datetime.now()
    logger.info("=" * 50)
    logger.info("[Bot] Starting EOD scan...")
    logger.info("=" * 50)

    try:
        tickers = get_full_universe()
    except UniverseLoadError as e:
        logger.error(f"[Bot] Universe load failed: {e}", exc_info=True)
        send_error_alert(f"Universe load failed: {e}")
        return
    except Exception as e:
        logger.error(f"[Bot] Unexpected universe error: {e}", exc_info=True)
        send_error_alert(f"Unexpected universe error: {type(e).__name__}: {e}")
        return

    try:
        logger.info(f"[Bot] Screening {len(tickers)} tickers...")
        screener_results = screen_universe(tickers)
        signals = filter_signals(screener_results)
        send_signals(signals)
    except Exception as e:
        logger.error(f"[Bot] Scan pipeline error: {e}", exc_info=True)
        send_error_alert(f"Scan pipeline error: {type(e).__name__}: {e}")
        return

    elapsed = (datetime.now() - start).total_seconds()
    logger.info(f"[Bot] Scan complete in {elapsed:.1f}s — {len(signals)} signals sent")


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
