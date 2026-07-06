import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import research.mart as mart
from research.events import (
    create_data_quality_event,
    create_report_generated_event,
    create_ticker_observed_event,
)
from research.hashing import sha256_file
from research.ids import stable_observation_id
from research.ledger_writer import append_events


GIT_SHA = "b7d7d008ada4720a5e1bc98b911f3ce3181a5c2b"
RUN_EMPTY = "local_20260706T080000_run-local_attempt-0_git-b7d7d008ada4"
RUN_POPULATED = "local_20260706T090000_run-local_attempt-0_git-b7d7d008ada4"
EMPTY_EVENT_TS = "2026-07-06T01:00:00Z"
POPULATED_EVENT_TS = "2026-07-06T02:00:00Z"
REPORT_TIMESTAMP = "2026-07-06T09:00:00"


def _artifact(name, row_count):
    return {
        "source_path": f"reports/daily_review/{name}",
        "copied_path": f"reports/research_ledger/artifacts/run/source_reports/{name}",
        "sha256": "a" * 64,
        "byte_size": 123,
        "row_count": row_count,
    }


def _report_generated(run_id, *, row_count, empty, event_timestamp):
    return create_report_generated_event(
        run_id=run_id,
        git_sha=GIT_SHA,
        source="local",
        event_timestamp=event_timestamp,
        payload={
            "report_timestamp": REPORT_TIMESTAMP,
            "csv_artifact": _artifact("report.csv", row_count),
            "json_artifact": _artifact("report.json", row_count),
            "empty_report_flag": empty,
            "source_summary": {
                "market_regime": "Bullish market regime",
                "universe_size": None,
                "scanned_count": 514,
                "liquidity_pass_count": 459,
                "setup_count": row_count,
                "generated_report_paths": [
                    "reports/daily_review/report.csv",
                    "reports/daily_review/report.json",
                ],
                "data_quality_warnings": ["empty_report"] if empty else [],
            },
        },
    )


def _ticker_observed(run_id, ticker, *, shadow_score, row_index, shadow_passed, reject_reasons):
    return create_ticker_observed_event(
        run_id=run_id,
        git_sha=GIT_SHA,
        source="local",
        event_timestamp=POPULATED_EVENT_TS,
        payload={
            "observation_id": stable_observation_id(run_id, ticker, "a" * 64),
            "ticker": ticker,
            "current_grade": "A",
            "simulated_grade": "C",
            "shadow_score": shadow_score,
            "shadow_grade": "Strong" if shadow_passed else "Poor",
            "rs_percentile": 83.46,
            "trend_template_pass": True,
            "pivot_status": "near_pivot",
            "shadow_passed": shadow_passed,
            "shadow_reject_reasons": reject_reasons,
            "warning_flags": None,
            "stop_distance": None,
            "volume_confirmation_ratio": 1.1,
            "contraction_count": 3,
            "contraction_depths": [12.5, 6.25],
            "base_depth": 23.26,
            "base_duration": None,
            "raw_row_index": row_index,
        },
    )


def _quality_event(run_id, *, warning_code, severity, event_timestamp):
    return create_data_quality_event(
        run_id=run_id,
        git_sha=GIT_SHA,
        source="local",
        event_timestamp=event_timestamp,
        warning_code=warning_code,
        severity=severity,
        details={"report_timestamp": REPORT_TIMESTAMP, "row_count": 0},
    )


def _fixture_events():
    """One empty run and one later populated run, mirroring real daily files."""
    return [
        _report_generated(RUN_EMPTY, row_count=0, empty=True, event_timestamp=EMPTY_EVENT_TS),
        _quality_event(
            RUN_EMPTY,
            warning_code="quality_check_passed",
            severity="info",
            event_timestamp=EMPTY_EVENT_TS,
        ),
        _quality_event(
            RUN_EMPTY,
            warning_code="empty_report",
            severity="warning",
            event_timestamp=EMPTY_EVENT_TS,
        ),
        _report_generated(
            RUN_POPULATED, row_count=2, empty=False, event_timestamp=POPULATED_EVENT_TS
        ),
        _ticker_observed(
            RUN_POPULATED,
            "HST",
            shadow_score=82,
            row_index=0,
            shadow_passed=True,
            reject_reasons=None,
        ),
        _ticker_observed(
            RUN_POPULATED,
            "MRNA",
            shadow_score=21,
            row_index=1,
            shadow_passed=False,
            reject_reasons=["no identifiable final contraction pivot"],
        ),
        _quality_event(
            RUN_POPULATED,
            warning_code="quality_check_passed",
            severity="info",
            event_timestamp=POPULATED_EVENT_TS,
        ),
    ]


def _write_fixture_ledger(tmp_path):
    """Write all fixture events into a single daily JSONL file; return events root."""
    event_file = append_events(
        _fixture_events(),
        ledger_root=tmp_path,
        report_timestamp=REPORT_TIMESTAMP,
    )
    return tmp_path / "events", event_file


def _append_raw_line(event_file, text):
    with Path(event_file).open("a", encoding="utf-8", newline="\n") as file:
        file.write(text + "\n")


def _legacy_event_line():
    # Real pre-hardening shape: old producer, no producer_version, flat payload.
    return json.dumps({
        "schema_version": 1,
        "producer": "signal_bot.v3_dry_run_review",
        "event_type": "report_generated",
        "event_id": "evt_legacy",
        "event_timestamp": "2026-07-05T07:13:45Z",
        "run_id": "local_20260705T141345_run-local_attempt-0_git-37d8a881ef4d",
        "git_sha": "37d8a881ef4d39f25004dffa24f0adb9fc0e9795",
        "source": "local",
        "payload": {
            "report_timestamp": "2026-07-05T14:13:45",
            "csv_path": "reports/daily_review/report.csv",
            "row_count": 19,
        },
    })


def _connect(db_path):
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def test_build_ingests_populated_and_empty_runs_from_single_daily_file(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "mart" / "research_mart.sqlite"

    summary = mart.build_mart(events_root, db_path)

    assert summary["files_scanned"] == 1
    assert summary["lines_read"] == 7
    assert summary["events_ingested"] == 7
    assert summary["skipped_invalid_schema"] == 0
    assert summary["skipped_malformed_json"] == 0
    assert summary["duplicates_ignored"] == 0
    assert summary["table_counts"] == {
        "runs": 2,
        "ticker_observations": 2,
        "data_quality_events": 3,
    }

    connection = _connect(db_path)
    try:
        runs = {row["run_id"]: row for row in connection.execute("SELECT * FROM runs")}
        assert set(runs) == {RUN_EMPTY, RUN_POPULATED}
        populated = runs[RUN_POPULATED]
        assert populated["empty_report_flag"] == 0
        assert populated["csv_row_count"] == 2
        assert populated["setup_count"] == 2
        assert populated["market_regime"] == "Bullish market regime"
        assert populated["git_sha"] == GIT_SHA
        assert runs[RUN_EMPTY]["empty_report_flag"] == 1
        quality_rows = list(
            connection.execute("SELECT run_id, warning_code FROM data_quality_events")
        )
        assert len(quality_rows) == 3
    finally:
        connection.close()


def test_ticker_observation_fields_round_trip(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "mart.sqlite"

    mart.build_mart(events_root, db_path)

    connection = _connect(db_path)
    try:
        tickers = list(
            connection.execute("SELECT * FROM ticker_observations ORDER BY raw_row_index")
        )
    finally:
        connection.close()

    assert [row["ticker"] for row in tickers] == ["HST", "MRNA"]
    hst, mrna = tickers
    assert hst["run_id"] == RUN_POPULATED
    assert hst["observation_id"].startswith("obs_")
    assert hst["shadow_score"] == 82
    assert hst["shadow_passed"] == 1
    assert hst["trend_template_pass"] == 1
    assert hst["shadow_reject_reasons"] is None
    assert hst["base_duration"] is None
    assert json.loads(hst["contraction_depths"]) == [12.5, 6.25]
    assert mrna["shadow_passed"] == 0
    assert json.loads(mrna["shadow_reject_reasons"]) == [
        "no identifiable final contraction pivot"
    ]


def test_legacy_producer_events_are_skipped_and_counted(tmp_path):
    events_root, event_file = _write_fixture_ledger(tmp_path)
    _append_raw_line(event_file, _legacy_event_line())
    db_path = tmp_path / "mart.sqlite"

    summary = mart.build_mart(events_root, db_path)

    assert summary["skipped_invalid_schema"] == 1
    assert summary["events_ingested"] == 7
    assert summary["table_counts"]["runs"] == 2


def test_malformed_json_and_non_dict_lines_are_skipped_and_counted(tmp_path):
    events_root, event_file = _write_fixture_ledger(tmp_path)
    _append_raw_line(event_file, "{not valid json")
    _append_raw_line(event_file, '["valid json", "but not an event object"]')
    db_path = tmp_path / "mart.sqlite"

    summary = mart.build_mart(events_root, db_path)

    assert summary["skipped_malformed_json"] == 1
    assert summary["skipped_invalid_schema"] == 1
    assert summary["events_ingested"] == 7


def test_duplicate_event_lines_are_ignored_and_counted(tmp_path):
    event = _quality_event(
        RUN_EMPTY,
        warning_code="quality_check_passed",
        severity="info",
        event_timestamp=EMPTY_EVENT_TS,
    )
    append_events([event], ledger_root=tmp_path, report_timestamp=REPORT_TIMESTAMP)
    append_events([event], ledger_root=tmp_path, report_timestamp=REPORT_TIMESTAMP)
    db_path = tmp_path / "mart.sqlite"

    summary = mart.build_mart(tmp_path / "events", db_path)

    assert summary["lines_read"] == 2
    assert summary["events_ingested"] == 1
    assert summary["duplicates_ignored"] == 1
    assert summary["table_counts"]["data_quality_events"] == 1


def test_rebuild_replaces_existing_mart_without_doubling(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "mart.sqlite"

    first = mart.build_mart(events_root, db_path)
    second = mart.build_mart(events_root, db_path)

    assert first["table_counts"] == second["table_counts"]
    assert second["table_counts"]["runs"] == 2
    assert second["duplicates_ignored"] == 0
    assert not db_path.with_name(db_path.name + ".tmp").exists()


def test_output_directory_is_created(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "nested" / "deep" / "research_mart.sqlite"

    mart.build_mart(events_root, db_path)

    assert db_path.exists()


def test_source_event_files_are_unchanged_by_build(tmp_path):
    events_root, event_file = _write_fixture_ledger(tmp_path)
    before = sha256_file(event_file)

    mart.build_mart(events_root, tmp_path / "mart.sqlite")

    assert sha256_file(event_file) == before


def test_summarize_mart_reports_latest_run_and_top_tickers(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "mart.sqlite"
    mart.build_mart(events_root, db_path)

    summary = mart.summarize_mart(db_path)

    assert summary["meta"]["events_ingested"] == 7
    assert summary["table_counts"]["ticker_observations"] == 2
    assert summary["latest_run"]["run_id"] == RUN_POPULATED
    assert [row["ticker"] for row in summary["top_tickers"]] == ["HST", "MRNA"]
    assert summary["latest_run_quality"] == [
        {"warning_code": "quality_check_passed", "count": 1}
    ]


def test_cli_build_and_summary_commands(tmp_path):
    events_root, _ = _write_fixture_ledger(tmp_path)
    db_path = tmp_path / "mart.sqlite"

    assert mart.main(["build", "--events-root", str(events_root), "--output", str(db_path)]) == 0
    assert mart.main(["summary", "--db", str(db_path)]) == 0

    missing = tmp_path / "missing.sqlite"
    assert mart.main(["summary", "--db", str(missing)]) == 1
    assert not missing.exists()


def test_mart_output_path_is_gitignored():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo_root.as_posix()}",
            "check-ignore",
            "reports/research_mart/research_mart.sqlite",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
