# signal_bot.py — Main entry point + Scheduler.
#
# Fix #9  — removed unused `format_signal_message` / `format_summary_message`
#   imports; send_signals now owns formatter access internally.
# Fix #13 — every failure path sends a Telegram alert so silent breakage
#   can't cost us days of signals.
# Fix #18 — file logging with daily rotation (see logging_config).
# Fix #19 — misfire grace lifted to MISFIRE_GRACE_SEC (1 h) with coalesce=True.
import csv
import json
import logging
import math
import sys
import os
from datetime import datetime
from pathlib import Path

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
from research_ledger import write_research_ledger_for_shadow_reports

setup_logging()
logger = logging.getLogger(__name__)
DAILY_REVIEW_REPORT_DIR = Path("reports/daily_review")
RESEARCH_LEDGER_ROOT = Path("reports/research_ledger")
_SHADOW_GRADE_CAP_CSV_COLUMNS = [
    "ticker",
    "current_grade",
    "simulated_grade",
    "simulated_grade_reason",
    "current_score",
    "shadow_score",
    "shadow_grade",
    "shadow_passed",
    "trend_template_pass",
    "rs_percentile",
    "contraction_count",
    "base_depth",
    "final_contraction_depth",
    "pivot_status",
    "distance_to_pivot_pct",
]


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


def _format_grade_counts(values: dict | None) -> str:
    if not values:
        return "none"
    ordered = ["A+", "A", "B", "C", "Reject"]
    parts = [
        f"{grade}: {values.get(grade, 0)}"
        for grade in ordered
        if values.get(grade, 0)
    ]
    return " | ".join(parts) if parts else "none"


def _format_v3_blockers(values: dict | None) -> list[str]:
    if not values:
        return ["- none: 0"]
    return [f"- {key}: {values.get(key, 0)}" for key in values]


def _format_vcp_shadow(values: dict | None) -> list[str]:
    if not values:
        return ["- comparison unavailable"]
    return [
        f"- agreement: {_format_key_counts(values.get('agreement_counts'))}",
        (
            "- pass counts: "
            f"current {values.get('current_logic_passed', 0)} | "
            f"new {values.get('new_engine_passed', 0)} | "
            f"2+ contractions {values.get('new_engine_contractions_2plus', 0)} | "
            f"3+ contractions {values.get('new_engine_contractions_3plus', 0)} | "
            f"pivots {values.get('new_engine_pivot_identified', 0)} | "
            f"extended {values.get('new_engine_extended', 0)}"
        ),
        f"- quality grades: {_format_key_counts(values.get('shadow_quality_grades'))}",
        (
            "- quality scores: "
            f"{_format_key_counts(values.get('shadow_quality_score_buckets'))} | "
            f"avg {_format_score(values.get('shadow_quality_average'))}"
        ),
        f"- new reject reasons: {_format_key_counts(values.get('new_engine_reject_reasons'), limit=5)}",
        f"- new warning flags: {_format_key_counts(values.get('new_engine_warning_flags'), limit=5)}",
    ]


def _format_score(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"
    return str(int(number)) if number.is_integer() else f"{number:.1f}"


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, str):
        return value
    try:
        return _json_safe(value.item())
    except AttributeError:
        return str(value)


def export_shadow_grade_cap_reports(
    result: dict,
    report_dir: Path | str | None = None,
    now: datetime | None = None,
) -> dict:
    """Write dry-run-only Shadow VCP grade-cap CSV/JSON reports."""
    simulation = result.get("shadow_grade_cap_simulation")
    if not isinstance(simulation, dict):
        return {}
    rows = simulation.get("rows") or []
    generated_at = now or datetime.now()
    report_root = Path(report_dir or DAILY_REVIEW_REPORT_DIR)
    report_root.mkdir(parents=True, exist_ok=True)
    base_name = f"shadow_grade_cap_{generated_at.strftime('%Y%m%d_%H%M%S')}"
    json_path = report_root / f"{base_name}.json"
    csv_path = report_root / f"{base_name}.csv"

    payload = {
        "report_type": "shadow_grade_cap_simulation",
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "simulation": simulation,
    }
    json_path.write_text(
        json.dumps(_json_safe(payload), allow_nan=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=_SHADOW_GRADE_CAP_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                column: _json_safe(row.get(column))
                for column in _SHADOW_GRADE_CAP_CSV_COLUMNS
            })
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "row_count": len(rows),
    }


def _format_pct(value: object) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "n/a"


def _format_ratio(value: object) -> str:
    try:
        return f"{float(value):.2f}x"
    except (TypeError, ValueError):
        return "n/a"


_WAIT_SUBTYPE_LABELS = {
    "WAIT_VOLUME_CONFIRMATION": "wait_volume",
    "WAIT_TIGHTER_STOP": "wait_stop",
    "WAIT_TIGHTER_STOP_AND_VOLUME": "wait_stop+volume",
}


def _format_wait_subtype(value: object) -> str:
    return _WAIT_SUBTYPE_LABELS.get(str(value), str(value))


def _format_selected_v3_review(rows: list[dict] | None) -> list[str]:
    if not rows:
        return ["- none"]
    lines = []
    for row in rows:
        blockers = ", ".join(str(item) for item in row.get("blockers") or ["none"])
        line = (
            f"- {row.get('ticker') or 'UNKNOWN'} | "
            f"{row.get('grade') or 'n/a'} | "
            f"{row.get('decision') or 'none'} | "
            f"{row.get('confidence') or 'n/a'} | "
            f"score {_format_score(row.get('score'))} | "
            f"stop {_format_pct(row.get('stop_distance_pct'))} | "
            f"vol {_format_ratio(row.get('volume_ratio'))} | "
            f"{blockers}"
        )
        if row.get("decision_subtype"):
            line += f" | subtype {_format_wait_subtype(row.get('decision_subtype'))}"
        if row.get("v3_error"):
            line += f" | V3 error: {row.get('v3_error')}"
        lines.append(line)
    return lines


def _format_shadow_grade_cap_rows(
    rows: list[dict] | None,
    limit: int = 5,
    empty: str = "none",
) -> list[str]:
    if not rows:
        return [f"- {empty}"]
    lines = []
    for row in rows[:limit]:
        lines.append(
            f"- {row.get('ticker') or 'UNKNOWN'} | "
            f"{row.get('current_grade') or 'n/a'}->{row.get('simulated_grade') or 'n/a'} | "
            f"shadow {_format_score(row.get('shadow_score'))} | "
            f"{row.get('simulated_grade_reason') or 'no reason'}"
        )
    return lines


def _format_shadow_grade_cap(values: dict | None, files: dict | None = None) -> list[str]:
    if not values:
        return ["Shadow grade-cap simulation:", "- unavailable"]
    promotions = values.get("promotions") or []
    demotions = values.get("demotions") or []
    lines = [
        "Shadow grade-cap simulation:",
        f"- current grades: {_format_grade_counts(values.get('current_distribution'))}",
        f"- simulated grades: {_format_grade_counts(values.get('simulated_distribution'))}",
        f"- promotions: {len(promotions)}",
        f"- demotions: {len(demotions)}",
        "Promotions:",
        *_format_shadow_grade_cap_rows(
            promotions,
            empty="none; cap-only simulation cannot promote grades",
        ),
        "Demotions:",
        *_format_shadow_grade_cap_rows(demotions),
        "Biggest A->C changes:",
        *_format_shadow_grade_cap_rows(values.get("biggest_a_to_c_changes")),
        "Biggest B->A/A+ changes:",
        *_format_shadow_grade_cap_rows(
            values.get("biggest_b_to_a_or_a_plus_changes"),
            empty="none; cap-only simulation cannot promote B candidates",
        ),
        "Top simulated A+ candidates:",
        *_format_shadow_grade_cap_rows(values.get("top_simulated_a_plus_candidates")),
    ]
    if files:
        lines.extend([
            f"CSV export: {files.get('csv') or 'not written'}",
            f"JSON export: {files.get('json') or 'not written'}",
        ])
    return lines


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
        "VCP shadow comparison:",
        *_format_vcp_shadow(result.get("vcp_shadow")),
        *_format_shadow_grade_cap(
            result.get("shadow_grade_cap_simulation"),
            result.get("shadow_grade_cap_report_files"),
        ),
        f"V3 decisions: {_format_decision_counts(result.get('v3_decision_counts') or {})}",
        f"Telegram delivery: {'skipped' if result.get('telegram_skipped') else 'enabled'}",
        f"Journal writes: {'skipped' if result.get('journal_skipped') else 'enabled'}",
        "V3 blockers:",
        *_format_v3_blockers(result.get("v3_blockers")),
        "Selected V3 review:",
        *_format_selected_v3_review(result.get("v3_selected_review")),
    ]

    samples = result.get("v3_sample_decisions") or []
    if samples:
        lines.append("Detailed examples:")
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
        lines.append("Detailed examples: none")

    return "\n".join(lines)


def run_v3_dry_run_review() -> dict:
    """Run scan logic with V3 decisions enabled and Telegram delivery disabled."""
    previous_decision_layer = v2_runtime.ENABLE_V3_DECISION_LAYER
    try:
        v2_runtime.ENABLE_V3_DECISION_LAYER = True
        result = run_v2_scan(
            debug="--debug-v2" in sys.argv,
            send_telegram=False,
            write_journal=False,
            log_rejects=False,
            log_relative_strength=False,
            fetch_liquidity_metadata=False,
            log_liquidity_metadata_warnings=False,
        )
        result["shadow_grade_cap_report_files"] = export_shadow_grade_cap_reports(result)
        result["research_ledger_files"] = write_research_ledger_for_shadow_reports(
            result,
            result["shadow_grade_cap_report_files"],
            ledger_root=RESEARCH_LEDGER_ROOT,
            repo_root=Path(__file__).resolve().parent,
        )
        return result
    finally:
        v2_runtime.ENABLE_V3_DECISION_LAYER = previous_decision_layer


def run_scan() -> bool:
    """Run the full EOD pipeline. Returns False when the scan failed or
    when Telegram delivered zero messages despite having a report to send.

    Failures are alerted via Telegram and swallowed here so the scheduler
    daemon survives a bad day; one-off runners (--run-now / CI) use the
    return value to decide the process exit code.
    """
    start = datetime.now()
    logger.info("=" * 50)
    logger.info("[Bot] Starting EOD scan...")
    logger.info("=" * 50)

    try:
        result = run_v2_scan(debug="--debug-v2" in sys.argv)
    except Exception as e:
        logger.error(f"[Bot] Scan pipeline error: {e}", exc_info=True)
        send_error_alert(f"Scan pipeline error: {type(e).__name__}: {e}")
        return False

    elapsed = (datetime.now() - start).total_seconds()
    messages_sent = result.get("messages_sent", 0)
    logger.info(
        f"[Bot] V2 scan complete in {elapsed:.1f}s — "
        f"{messages_sent} messages sent"
    )

    # The market summary is always attempted when Telegram is enabled, so a
    # zero-delivery run means every send failed (wrong target mode, missing
    # chat id, or API rejections) — regardless of test/prod routing. Fail the
    # run so CI turns red instead of reporting silent delivery failure.
    had_report_to_send = (
        not result.get("telegram_skipped", False)
        and (
            result.get("trade_signals", 0) > 0
            or result.get("watchlist", 0) > 0
            or "market_regime" in result
        )
    )
    if messages_sent == 0 and had_report_to_send:
        logger.error(
            "[CI] Zero messages delivered despite signals present — "
            f"trade_signals={result.get('trade_signals', 0)} "
            f"watchlist={result.get('watchlist', 0)} "
            f"market_regime_valid={result.get('market_regime_valid')}"
        )
        return False
    return True


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
        if not run_scan():
            # Non-zero exit so CI (GitHub Actions) marks failed scans red.
            sys.exit(1)
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
