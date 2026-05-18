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
import v2_engine as v2_runtime
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


def _format_decision_counts(counts: dict) -> str:
    ordered = ["ENTER", "WAIT", "WATCHLIST_ONLY", "AVOID", "none"]
    return " | ".join(f"{key}: {counts.get(key, 0)}" for key in ordered)


def _format_key_counts(values: dict | None, limit: int | None = None) -> str:
    if not values:
        return "none"
    items = [
        (str(key), value)
        for key, value in values.items()
        if value not in (None, 0, {}, [])
    ]
    if not items:
        return "none"
    items.sort(key=lambda item: (-int(item[1]) if isinstance(item[1], int) else 0, item[0]))
    if limit is not None:
        items = items[:limit]
    return " | ".join(f"{key}: {value}" for key, value in items)


def _format_v3_blockers(values: dict | None) -> list[str]:
    if not values:
        return ["- none: 0"]
    return [f"- {key}: {values.get(key, 0)}" for key in values]


def format_v3_dry_run_review(result: dict) -> str:
    """Format a compact V3 dry-run review without exposing credentials."""
    lines = [
        "V3 Dry Run Review",
        f"Market regime: {result.get('market_regime') or 'Unknown'}",
        f"Market valid: {_yes_no(result.get('market_regime_valid'))}",
        f"Scanned: {result.get('scanned', 0)}",
        (
            "Selected: "
            f"{result.get('trade_signals', 0)} trade alerts | "
            f"{result.get('watchlist', 0)} watchlist"
        ),
        f"V2 funnel: {_format_key_counts(result.get('funnel'))}",
        f"Reject aggregation: {_format_key_counts(result.get('reject_reasons'), limit=5)}",
        f"V3 decisions: {_format_decision_counts(result.get('v3_decision_counts') or {})}",
        f"Telegram delivery: {'skipped' if result.get('telegram_skipped') else 'enabled'}",
        f"Journal writes: {'skipped' if result.get('journal_skipped') else 'enabled'}",
        "V3 blockers:",
        *_format_v3_blockers(result.get("v3_blockers")),
    ]

    samples = result.get("v3_sample_decisions") or []
    if samples:
        lines.append("Sample decisions:")
        for sample in samples:
            line = (
                f"- {sample.get('ticker') or 'UNKNOWN'} | "
                f"{sample.get('grade') or 'n/a'} | "
                f"{sample.get('decision') or 'none'} | "
                f"{sample.get('confidence') or 'n/a'}"
            )
            reason = sample.get("main_reason")
            if reason:
                line += f" | {reason}"
            if sample.get("v3_error"):
                line += f" | V3 error: {sample.get('v3_error')}"
            lines.append(line)
            supporting = sample.get("supporting_reasons") or []
            if supporting:
                lines.append("  Reasons: " + "; ".join(str(item) for item in supporting[:2]))
            warnings = sample.get("risk_warnings") or []
            if warnings:
                lines.append("  Warnings: " + "; ".join(str(item) for item in warnings[:2]))
    else:
        lines.append("Sample decisions: none")

    return "\n".join(lines)


def run_v3_dry_run_review() -> dict:
    """Run scan logic with V3 decisions enabled and Telegram delivery disabled."""
    previous_decision_layer = v2_runtime.ENABLE_V3_DECISION_LAYER
    try:
        v2_runtime.ENABLE_V3_DECISION_LAYER = True
        return run_v2_scan(
            debug="--debug-v2" in sys.argv,
            send_telegram=False,
            write_journal=False,
            log_rejects=False,
            log_relative_strength=False,
        )
    finally:
        v2_runtime.ENABLE_V3_DECISION_LAYER = previous_decision_layer


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
      --v3-dry-run-review : run scan review with V3 decisions and no Telegram.
      --run-now : execute once and exit.
      default   : schedule daily at SCHEDULE_HOUR:SCHEDULE_MINUTE (TIMEZONE).
    """
    if "--telegram-rollout-check" in sys.argv:
        print(format_telegram_rollout_checklist(build_telegram_rollout_dry_run_checklist()))
        return

    if "--v3-dry-run-review" in sys.argv:
        print(format_v3_dry_run_review(run_v3_dry_run_review()))
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
