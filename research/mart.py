"""Read-only SQLite research mart rebuilt from research ledger JSONL events.

The mart is disposable derived state: every build rebuilds the database from
scratch out of the append-only ledger event files, so no incremental-ingest,
dedup-across-builds, or migration logic is needed. Ledger files are opened
read-only and are never modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
from pathlib import Path

from research.events import utc_now_iso
from research.ids import canonical_json
from research.schema import EventValidationError, validate_event


DEFAULT_EVENTS_ROOT = Path("reports/research_ledger/events")
DEFAULT_MART_PATH = Path("reports/research_mart/research_mart.sqlite")
MART_SCHEMA_VERSION = 1
_TOP_TICKER_LIMIT = 5

# ticker_observations is keyed on event_id, not observation_id: duplicate
# ticker rows in one report legitimately share an observation_id.
# No foreign keys: orphan events must ingest and surface via LEFT JOIN,
# not fail the build.
_SCHEMA_SQL = """
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    report_timestamp TEXT,
    event_timestamp TEXT NOT NULL,
    git_sha TEXT,
    source TEXT NOT NULL,
    producer_version TEXT,
    empty_report_flag INTEGER,
    market_regime TEXT,
    universe_size INTEGER,
    scanned_count INTEGER,
    liquidity_pass_count INTEGER,
    setup_count INTEGER,
    csv_source_path TEXT,
    csv_copied_path TEXT,
    csv_sha256 TEXT,
    csv_byte_size INTEGER,
    csv_row_count INTEGER,
    json_source_path TEXT,
    json_copied_path TEXT,
    json_sha256 TEXT,
    json_byte_size INTEGER,
    json_row_count INTEGER,
    source_event_file TEXT NOT NULL
);

CREATE TABLE ticker_observations (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    raw_row_index INTEGER,
    observation_id TEXT,
    ticker TEXT,
    current_grade TEXT,
    simulated_grade TEXT,
    shadow_score REAL,
    shadow_grade TEXT,
    shadow_passed INTEGER,
    rs_percentile REAL,
    trend_template_pass INTEGER,
    pivot_status TEXT,
    shadow_reject_reasons TEXT,
    warning_flags TEXT,
    contraction_depths TEXT,
    stop_distance REAL,
    volume_confirmation_ratio REAL,
    contraction_count REAL,
    base_depth REAL,
    base_duration REAL,
    event_timestamp TEXT NOT NULL,
    source_event_file TEXT NOT NULL
);
CREATE INDEX idx_ticker_observations_run_id ON ticker_observations (run_id);
CREATE INDEX idx_ticker_observations_ticker ON ticker_observations (ticker);

CREATE TABLE data_quality_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    warning_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    event_timestamp TEXT NOT NULL,
    source_event_file TEXT NOT NULL
);
CREATE INDEX idx_data_quality_events_run_id ON data_quality_events (run_id);

CREATE TABLE mart_meta (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    built_at TEXT NOT NULL,
    events_root TEXT NOT NULL,
    mart_schema_version INTEGER NOT NULL,
    files_scanned INTEGER NOT NULL,
    lines_read INTEGER NOT NULL,
    events_ingested INTEGER NOT NULL,
    skipped_invalid_schema INTEGER NOT NULL,
    skipped_malformed_json INTEGER NOT NULL,
    duplicates_ignored INTEGER NOT NULL
);
"""

_INSERT_RUN_SQL = """
INSERT OR IGNORE INTO runs (
    run_id, event_id, report_timestamp, event_timestamp, git_sha, source,
    producer_version, empty_report_flag, market_regime, universe_size,
    scanned_count, liquidity_pass_count, setup_count,
    csv_source_path, csv_copied_path, csv_sha256, csv_byte_size, csv_row_count,
    json_source_path, json_copied_path, json_sha256, json_byte_size, json_row_count,
    source_event_file
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_TICKER_SQL = """
INSERT OR IGNORE INTO ticker_observations (
    event_id, run_id, raw_row_index, observation_id, ticker,
    current_grade, simulated_grade, shadow_score, shadow_grade, shadow_passed,
    rs_percentile, trend_template_pass, pivot_status,
    shadow_reject_reasons, warning_flags, contraction_depths,
    stop_distance, volume_confirmation_ratio, contraction_count,
    base_depth, base_duration, event_timestamp, source_event_file
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_QUALITY_SQL = """
INSERT OR IGNORE INTO data_quality_events (
    event_id, run_id, warning_code, severity, details,
    event_timestamp, source_event_file
) VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _to_int_bool(value: object) -> int | None:
    if value is None:
        return None
    return 1 if bool(value) else 0


def _json_text(value: object) -> str | None:
    return None if value is None else canonical_json(value)


def _insert_report_generated(cursor: sqlite3.Cursor, event: dict, source_event_file: str) -> bool:
    payload = event["payload"]
    csv_artifact = payload.get("csv_artifact") or {}
    json_artifact = payload.get("json_artifact") or {}
    source_summary = payload.get("source_summary") or {}
    cursor.execute(
        _INSERT_RUN_SQL,
        (
            event["run_id"],
            event["event_id"],
            payload.get("report_timestamp"),
            event["event_timestamp"],
            event.get("git_sha"),
            event["source"],
            event.get("producer_version"),
            _to_int_bool(payload.get("empty_report_flag")),
            source_summary.get("market_regime"),
            source_summary.get("universe_size"),
            source_summary.get("scanned_count"),
            source_summary.get("liquidity_pass_count"),
            source_summary.get("setup_count"),
            csv_artifact.get("source_path"),
            csv_artifact.get("copied_path"),
            csv_artifact.get("sha256"),
            csv_artifact.get("byte_size"),
            csv_artifact.get("row_count"),
            json_artifact.get("source_path"),
            json_artifact.get("copied_path"),
            json_artifact.get("sha256"),
            json_artifact.get("byte_size"),
            json_artifact.get("row_count"),
            source_event_file,
        ),
    )
    return cursor.rowcount > 0


def _insert_ticker_observed(cursor: sqlite3.Cursor, event: dict, source_event_file: str) -> bool:
    payload = event["payload"]
    cursor.execute(
        _INSERT_TICKER_SQL,
        (
            event["event_id"],
            event["run_id"],
            payload.get("raw_row_index"),
            payload.get("observation_id"),
            payload.get("ticker"),
            payload.get("current_grade"),
            payload.get("simulated_grade"),
            payload.get("shadow_score"),
            payload.get("shadow_grade"),
            _to_int_bool(payload.get("shadow_passed")),
            payload.get("rs_percentile"),
            _to_int_bool(payload.get("trend_template_pass")),
            payload.get("pivot_status"),
            _json_text(payload.get("shadow_reject_reasons")),
            _json_text(payload.get("warning_flags")),
            _json_text(payload.get("contraction_depths")),
            payload.get("stop_distance"),
            payload.get("volume_confirmation_ratio"),
            payload.get("contraction_count"),
            payload.get("base_depth"),
            payload.get("base_duration"),
            event["event_timestamp"],
            source_event_file,
        ),
    )
    return cursor.rowcount > 0


def _insert_data_quality_event(cursor: sqlite3.Cursor, event: dict, source_event_file: str) -> bool:
    payload = event["payload"]
    cursor.execute(
        _INSERT_QUALITY_SQL,
        (
            event["event_id"],
            event["run_id"],
            payload["warning_code"],
            payload["severity"],
            _json_text(payload.get("details")),
            event["event_timestamp"],
            source_event_file,
        ),
    )
    return cursor.rowcount > 0


_INSERTERS = {
    "report_generated": _insert_report_generated,
    "ticker_observed": _insert_ticker_observed,
    "data_quality_event": _insert_data_quality_event,
}


def _table_counts(connection: sqlite3.Connection) -> dict:
    counts = {}
    for table in ("runs", "ticker_observations", "data_quality_events"):
        counts[table] = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    return counts


def build_mart(
    events_root: Path | str = DEFAULT_EVENTS_ROOT,
    output_path: Path | str = DEFAULT_MART_PATH,
) -> dict:
    """Rebuild the mart database from scratch and atomically replace the output file."""
    events_root = Path(events_root)
    output_path = Path(output_path)
    event_files = (
        sorted(events_root.rglob("*.jsonl"), key=lambda path: path.as_posix())
        if events_root.exists()
        else []
    )

    files_scanned = 0
    lines_read = 0
    events_ingested = 0
    skipped_invalid_schema = 0
    skipped_malformed_json = 0
    duplicates_ignored = 0
    built_at = utc_now_iso()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Build into a temp file and swap in, so a failed build never leaves a
    # partially-written mart at the final path.
    tmp_path = output_path.with_name(output_path.name + ".tmp")
    tmp_path.unlink(missing_ok=True)

    try:
        connection = sqlite3.connect(str(tmp_path))
        try:
            cursor = connection.cursor()
            cursor.executescript(_SCHEMA_SQL)
            for event_file in event_files:
                files_scanned += 1
                source_event_file = event_file.as_posix()
                for line in event_file.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    lines_read += 1
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        skipped_malformed_json += 1
                        continue
                    if not isinstance(event, dict):
                        skipped_invalid_schema += 1
                        continue
                    try:
                        # Reuse the producer-side validator as the ingest gate:
                        # legacy pre-hardening events and any future shape drift
                        # are skipped and counted, never crash the build.
                        validate_event(event)
                    except EventValidationError:
                        skipped_invalid_schema += 1
                        continue
                    inserted = _INSERTERS[event["event_type"]](cursor, event, source_event_file)
                    if inserted:
                        events_ingested += 1
                    else:
                        duplicates_ignored += 1
            cursor.execute(
                """
                INSERT INTO mart_meta (
                    id, built_at, events_root, mart_schema_version, files_scanned,
                    lines_read, events_ingested, skipped_invalid_schema,
                    skipped_malformed_json, duplicates_ignored
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    built_at,
                    events_root.as_posix(),
                    MART_SCHEMA_VERSION,
                    files_scanned,
                    lines_read,
                    events_ingested,
                    skipped_invalid_schema,
                    skipped_malformed_json,
                    duplicates_ignored,
                ),
            )
            connection.commit()
            table_counts = _table_counts(connection)
        finally:
            connection.close()
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    os.replace(tmp_path, output_path)

    return {
        "events_root": events_root.as_posix(),
        "events_root_exists": events_root.exists(),
        "output_path": output_path.as_posix(),
        "built_at": built_at,
        "mart_schema_version": MART_SCHEMA_VERSION,
        "files_scanned": files_scanned,
        "lines_read": lines_read,
        "events_ingested": events_ingested,
        "skipped_invalid_schema": skipped_invalid_schema,
        "skipped_malformed_json": skipped_malformed_json,
        "duplicates_ignored": duplicates_ignored,
        "table_counts": table_counts,
    }


def summarize_mart(db_path: Path | str = DEFAULT_MART_PATH) -> dict:
    """Read latest-run and count summaries from an existing mart database."""
    db_path = Path(db_path)
    if not db_path.exists():
        # Guard: sqlite3.connect would silently create an empty file here.
        raise FileNotFoundError(f"mart database not found: {db_path.as_posix()}")

    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        meta_row = connection.execute("SELECT * FROM mart_meta WHERE id = 1").fetchone()
        table_counts = _table_counts(connection)
        latest_run_row = connection.execute(
            "SELECT * FROM runs ORDER BY event_timestamp DESC, run_id DESC LIMIT 1"
        ).fetchone()
        latest_run = dict(latest_run_row) if latest_run_row else None
        latest_run_quality = []
        top_tickers = []
        if latest_run:
            latest_run_quality = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT warning_code, COUNT(*) AS count
                    FROM data_quality_events
                    WHERE run_id = ?
                    GROUP BY warning_code
                    ORDER BY warning_code
                    """,
                    (latest_run["run_id"],),
                )
            ]
            top_tickers = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT ticker, shadow_score, shadow_grade, current_grade,
                           simulated_grade, rs_percentile
                    FROM ticker_observations
                    WHERE run_id = ?
                    ORDER BY shadow_score DESC, ticker ASC
                    LIMIT ?
                    """,
                    (latest_run["run_id"], _TOP_TICKER_LIMIT),
                )
            ]
    finally:
        connection.close()

    return {
        "db_path": db_path.as_posix(),
        "meta": dict(meta_row) if meta_row else None,
        "table_counts": table_counts,
        "latest_run": latest_run,
        "latest_run_quality": latest_run_quality,
        "top_tickers": top_tickers,
    }


def _format_build_summary(summary: dict) -> str:
    counts = summary["table_counts"]
    lines = [
        "Research mart build",
        f"Events root: {summary['events_root']}",
        f"Output: {summary['output_path']}",
        f"Files scanned: {summary['files_scanned']}",
        f"Lines read: {summary['lines_read']}",
        f"Events ingested: {summary['events_ingested']}",
        f"Skipped invalid schema: {summary['skipped_invalid_schema']}",
        f"Skipped malformed JSON: {summary['skipped_malformed_json']}",
        f"Duplicates ignored: {summary['duplicates_ignored']}",
        (
            f"Runs: {counts['runs']} | Ticker observations: {counts['ticker_observations']}"
            f" | Data quality events: {counts['data_quality_events']}"
        ),
    ]
    if not summary["events_root_exists"]:
        lines.append("Warning: events root does not exist; mart is empty")
    return "\n".join(lines)


def _yes_no(value: object) -> str:
    return "yes" if value else "no"


def _format_mart_summary(summary: dict) -> str:
    counts = summary["table_counts"]
    meta = summary["meta"] or {}
    lines = [
        "Research mart summary",
        f"DB: {summary['db_path']}",
        f"Built at: {meta.get('built_at') or 'unknown'}",
        f"Events root: {meta.get('events_root') or 'unknown'}",
        (
            f"Runs: {counts['runs']} | Ticker observations: {counts['ticker_observations']}"
            f" | Data quality events: {counts['data_quality_events']}"
        ),
        (
            f"Skipped invalid schema: {meta.get('skipped_invalid_schema', 0)}"
            f" | malformed JSON: {meta.get('skipped_malformed_json', 0)}"
            f" | duplicates ignored: {meta.get('duplicates_ignored', 0)}"
        ),
    ]
    latest_run = summary["latest_run"]
    if latest_run is None:
        lines.append("Latest run: none")
        return "\n".join(lines)
    lines.extend([
        f"Latest run: {latest_run['run_id']}",
        f"- report timestamp: {latest_run['report_timestamp']}",
        (
            f"- source: {latest_run['source']} | git: {(latest_run['git_sha'] or 'unknown')[:12]}"
            f" | empty report: {_yes_no(latest_run['empty_report_flag'])}"
        ),
        f"- market regime: {latest_run['market_regime']}",
        (
            f"- scanned: {latest_run['scanned_count']}"
            f" | liquidity passed: {latest_run['liquidity_pass_count']}"
            f" | setups: {latest_run['setup_count']}"
            f" | csv rows: {latest_run['csv_row_count']}"
        ),
    ])
    if summary["latest_run_quality"]:
        quality = " | ".join(
            f"{item['warning_code']}: {item['count']}" for item in summary["latest_run_quality"]
        )
        lines.append(f"- data quality: {quality}")
    if summary["top_tickers"]:
        lines.append("Top tickers by shadow score:")
        for row in summary["top_tickers"]:
            lines.append(
                f"- {row['ticker']} | shadow {row['shadow_score']} | {row['shadow_grade']}"
                f" | {row['current_grade']} -> {row['simulated_grade']}"
                f" | RS {row['rs_percentile']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.mart",
        description="Rebuild or summarize the read-only research mart derived from ledger events.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build", help="rebuild the mart from ledger event files")
    build_parser.add_argument("--events-root", default=str(DEFAULT_EVENTS_ROOT))
    build_parser.add_argument("--output", default=str(DEFAULT_MART_PATH))

    summary_parser = subparsers.add_parser("summary", help="summarize an existing mart database")
    summary_parser.add_argument("--db", default=str(DEFAULT_MART_PATH))

    args = parser.parse_args(argv)
    if args.command == "build":
        summary = build_mart(events_root=args.events_root, output_path=args.output)
        print(_format_build_summary(summary))
        return 0
    try:
        summary = summarize_mart(db_path=args.db)
    except FileNotFoundError as error:
        print(str(error))
        return 1
    print(_format_mart_summary(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
