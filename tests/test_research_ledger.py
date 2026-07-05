import csv
import json
import math
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import research
import research_ledger


def _write_report_pair(root, *, rows, generated_at="2026-06-29T10:08:26"):
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "shadow_grade_cap_20260629_100826.csv"
    json_path = root / "shadow_grade_cap_20260629_100826.json"
    fieldnames = [
        "ticker",
        "current_grade",
        "simulated_grade",
        "shadow_score",
        "shadow_grade",
        "rs_percentile",
        "trend_template_pass",
        "pivot_status",
        "shadow_passed",
        "contraction_count",
        "base_depth",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    json_path.write_text(
        json.dumps({
            "generated_at": generated_at,
            "report_type": "shadow_grade_cap_simulation",
            "simulation": {"rows": rows},
        }),
        encoding="utf-8",
    )
    return {"csv": str(csv_path), "json": str(json_path), "row_count": len(rows)}


def _read_events(event_file):
    return [
        json.loads(line)
        for line in Path(event_file).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _valid_data_quality_event():
    return {
        "schema_version": 1,
        "producer": "shadow-research-ledger",
        "producer_version": "1.0.0",
        "event_type": "data_quality_event",
        "event_id": "evt_test",
        "event_timestamp": "2026-06-29T10:08:26Z",
        "run_id": "run_test",
        "git_sha": None,
        "source": "local",
        "payload": {
            "warning_code": "quality_check_passed",
            "severity": "info",
            "details": {},
        },
    }


def test_module_imports_work():
    assert research.PRODUCER == "shadow-research-ledger"
    assert research.PRODUCER_VERSION == "1.0.0"
    assert research_ledger.write_research_ledger_for_shadow_reports is research.write_research_ledger_for_shadow_reports


def test_event_file_append(tmp_path):
    event = _valid_data_quality_event()

    event_file = research_ledger.append_events(
        [event],
        ledger_root=tmp_path,
        report_timestamp="2026-06-29T10:08:26",
    )
    research_ledger.append_events(
        [event],
        ledger_root=tmp_path,
        report_timestamp="2026-06-29T10:08:26",
    )

    assert event_file.name == "research_events_20260629.jsonl"
    assert len(_read_events(event_file)) == 2


def test_stable_event_id_is_deterministic():
    payload = {"b": 2, "a": 1}

    first = research_ledger.stable_event_id("report_generated", "run-1", payload)
    second = research_ledger.stable_event_id("report_generated", "run-1", {"a": 1, "b": 2})

    assert first == second
    assert first.startswith("evt_")


def test_stable_observation_id_is_deterministic_without_row_index():
    first = research_ledger.stable_observation_id("run-1", "HST", "abc123")
    second = research_ledger.stable_observation_id("run-1", "HST", "abc123")

    assert first == second
    assert first.startswith("obs_")
    assert first != research_ledger.stable_observation_id("run-1", "CFG", "abc123")
    assert first != research_ledger.stable_observation_id("run-1", "HST", "different-hash")


def test_artifact_hashing_byte_size_and_copy(tmp_path):
    report_files = _write_report_pair(
        tmp_path / "daily_review",
        rows=[{
            "ticker": "HST",
            "current_grade": "B",
            "simulated_grade": "B",
            "shadow_score": "82",
            "shadow_grade": "Strong",
            "rs_percentile": "89.51",
            "trend_template_pass": "True",
            "pivot_status": "near_pivot",
            "shadow_passed": "True",
            "contraction_count": "3",
            "base_depth": "29.95",
        }],
    )

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {"market_regime": "Bullish", "scanned": 515, "funnel": {"liquidity_passed": 200}},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha="abcdef1234567890",
    )

    assert Path(result["csv_artifact_path"]).exists()
    assert Path(result["json_artifact_path"]).exists()
    assert (
        research_ledger.sha256_file(result["csv_artifact_path"])
        == research_ledger.sha256_file(report_files["csv"])
    )
    assert research_ledger.byte_size(result["csv_artifact_path"]) == Path(report_files["csv"]).stat().st_size


def test_artifact_paths_are_posix_for_portability(tmp_path):
    report_files = _write_report_pair(
        tmp_path / "daily_review",
        rows=[{
            "ticker": "HST",
            "current_grade": "B",
            "simulated_grade": "B",
            "shadow_score": "82",
            "shadow_grade": "Strong",
            "rs_percentile": "89.51",
            "trend_template_pass": "True",
            "pivot_status": "near_pivot",
            "shadow_passed": "True",
            "contraction_count": "3",
            "base_depth": "29.95",
        }],
    )

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {"market_regime": "Bullish", "scanned": 1},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha="abcdef1234567890",
    )
    report_event = _read_events(result["event_file"])[0]

    assert "\\" not in report_event["payload"]["csv_artifact"]["source_path"]
    assert "\\" not in report_event["payload"]["csv_artifact"]["copied_path"]
    assert "\\" not in result["csv_artifact_path"]
    assert all(
        "\\" not in path
        for path in report_event["payload"]["source_summary"]["generated_report_paths"]
    )


def test_populated_report_creates_report_ticker_and_quality_events(tmp_path):
    report_files = _write_report_pair(
        tmp_path / "daily_review",
        rows=[
            {
                "ticker": "HST",
                "current_grade": "B",
                "simulated_grade": "B",
                "shadow_score": "82",
                "shadow_grade": "Strong",
                "rs_percentile": "89.51",
                "trend_template_pass": "True",
                "pivot_status": "near_pivot",
                "shadow_passed": "True",
                "contraction_count": "3",
                "base_depth": "29.95",
            },
            {
                "ticker": "MRNA",
                "current_grade": "B",
                "simulated_grade": "C",
                "shadow_score": "21",
                "shadow_grade": "Poor",
                "rs_percentile": "95.53",
                "trend_template_pass": "True",
                "pivot_status": "no_pivot",
                "shadow_passed": "False",
                "contraction_count": "0",
                "base_depth": "53.28",
            },
        ],
    )

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {"market_regime": "Bullish", "scanned": 515, "setup_passed": 15},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={"GITHUB_ACTIONS": "true", "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"},
        git_sha="abcdef1234567890",
    )
    events = _read_events(result["event_file"])

    assert result["event_count"] == 4
    assert [event["event_type"] for event in events] == [
        "report_generated",
        "ticker_observed",
        "ticker_observed",
        "data_quality_event",
    ]
    assert events[0]["producer"] == "shadow-research-ledger"
    assert events[0]["producer_version"] == "1.0.0"
    assert events[0]["source"] == "github_actions"
    assert events[0]["payload"]["csv_artifact"]["row_count"] == 2
    assert events[0]["payload"]["json_artifact"]["row_count"] == 2
    assert events[0]["payload"]["source_summary"]["setup_count"] == 15
    assert events[1]["payload"]["ticker"] == "HST"
    assert events[1]["payload"]["observation_id"].startswith("obs_")
    assert events[-1]["payload"]["warning_code"] == "quality_check_passed"
    assert events[-1]["payload"]["severity"] == "info"


def test_zero_counts_are_preserved_in_source_summary(tmp_path):
    report_files = _write_report_pair(
        tmp_path / "daily_review",
        rows=[{
            "ticker": "HST",
            "current_grade": "B",
            "simulated_grade": "B",
            "shadow_score": "82",
            "shadow_grade": "Strong",
            "rs_percentile": "89.51",
            "trend_template_pass": "True",
            "pivot_status": "near_pivot",
            "shadow_passed": "True",
            "contraction_count": "3",
            "base_depth": "29.95",
        }],
    )

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {
            "market_regime": "Bullish",
            "scanned": 1,
            "liquidity_passed": 0,
            "setup_passed": 0,
            "funnel": {"liquidity_passed": 99, "setup_passed": 99},
        },
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha="abcdef1234567890",
    )
    source_summary = _read_events(result["event_file"])[0]["payload"]["source_summary"]

    assert source_summary["liquidity_pass_count"] == 0
    assert source_summary["setup_count"] == 0


def test_observation_id_ignores_raw_row_index_in_written_events(tmp_path):
    row = {
        "ticker": "HST",
        "current_grade": "B",
        "simulated_grade": "B",
        "shadow_score": "82",
        "shadow_grade": "Strong",
        "rs_percentile": "89.51",
        "trend_template_pass": "True",
        "pivot_status": "near_pivot",
        "shadow_passed": "True",
        "contraction_count": "3",
        "base_depth": "29.95",
    }
    report_files = _write_report_pair(tmp_path / "daily_review", rows=[row, row])

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha="abcdef1234567890",
    )
    ticker_events = [
        event for event in _read_events(result["event_file"])
        if event["event_type"] == "ticker_observed"
    ]

    assert ticker_events[0]["payload"]["raw_row_index"] == 0
    assert ticker_events[1]["payload"]["raw_row_index"] == 1
    assert ticker_events[0]["payload"]["observation_id"] == ticker_events[1]["payload"]["observation_id"]


def test_empty_report_creates_report_passed_and_empty_quality_events(tmp_path):
    report_files = _write_report_pair(tmp_path / "daily_review", rows=[])

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {"market_regime": "Invalid market", "scanned": 0},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha=None,
    )
    events = _read_events(result["event_file"])

    assert result["empty_report_flag"] is True
    assert [event["event_type"] for event in events] == [
        "report_generated",
        "data_quality_event",
        "data_quality_event",
    ]
    assert events[0]["payload"]["empty_report_flag"] is True
    assert events[1]["payload"]["warning_code"] == "quality_check_passed"
    assert events[1]["payload"]["severity"] == "info"
    assert events[2]["payload"]["warning_code"] == "empty_report"
    assert events[2]["payload"]["severity"] == "warning"


def test_missing_optional_fields_become_null(tmp_path):
    report_files = _write_report_pair(
        tmp_path / "daily_review",
        rows=[{
            "ticker": "CFG",
            "current_grade": "B",
            "simulated_grade": "B",
            "shadow_score": "90",
            "shadow_grade": "Elite",
            "rs_percentile": "84.85",
            "trend_template_pass": "True",
            "pivot_status": "near_pivot",
            "shadow_passed": "True",
            "contraction_count": "3",
            "base_depth": "16.09",
        }],
    )

    result = research_ledger.write_research_ledger_for_shadow_reports(
        {},
        report_files,
        ledger_root=tmp_path / "ledger",
        now=datetime(2026, 6, 29, 10, 8, 26, tzinfo=timezone.utc),
        env={},
        git_sha=None,
    )
    ticker_event = _read_events(result["event_file"])[1]
    payload = ticker_event["payload"]

    assert payload["shadow_reject_reasons"] is None
    assert payload["warning_flags"] is None
    assert payload["stop_distance"] is None
    assert payload["volume_confirmation_ratio"] is None
    assert payload["contraction_depths"] is None
    assert payload["base_duration"] is None


def test_malformed_events_are_rejected_before_append(tmp_path):
    valid = _valid_data_quality_event()
    malformed = dict(valid)
    malformed.pop("payload")

    with pytest.raises(research_ledger.EventValidationError):
        research_ledger.append_events(
            [valid, malformed],
            ledger_root=tmp_path,
            report_timestamp="2026-06-29T10:08:26",
        )

    assert not list(tmp_path.rglob("*.jsonl"))


def test_malformed_data_quality_event_payload_is_rejected_before_append(tmp_path):
    malformed = _valid_data_quality_event()
    malformed["payload"].pop("warning_code")

    with pytest.raises(research_ledger.EventValidationError):
        research_ledger.append_events(
            [malformed],
            ledger_root=tmp_path,
            report_timestamp="2026-06-29T10:08:26",
        )

    assert not list(tmp_path.rglob("*.jsonl"))


def test_unserializable_events_are_rejected_before_append(tmp_path):
    valid = _valid_data_quality_event()
    unserializable = _valid_data_quality_event()
    unserializable["payload"]["details"] = {"bad": math.nan}

    with pytest.raises(ValueError):
        research_ledger.append_events(
            [valid, unserializable],
            ledger_root=tmp_path,
            report_timestamp="2026-06-29T10:08:26",
        )

    assert not list(tmp_path.rglob("*.jsonl"))


def test_generated_research_ledger_files_are_gitignored():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={repo_root.as_posix()}",
            "check-ignore",
            "reports/research_ledger/events/2026/06/research_events_20260629.jsonl",
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
