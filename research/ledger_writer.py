"""Append-only writer for dry-run research ledger events."""

from __future__ import annotations

import csv
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from research.artifacts import artifact_metadata, copy_source_report
from research.events import (
    create_data_quality_event,
    create_report_generated_event,
    create_ticker_observed_event,
    utc_now_iso,
)
from research.hashing import sha256_file
from research.ids import build_run_id, canonical_json, stable_observation_id
from research.schema import validate_events


DEFAULT_LEDGER_ROOT = Path("reports/research_ledger")


def _parse_number(value: object) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _parse_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip().lower()
    if text in {"true", "1", "yes"}:
        return True
    if text in {"false", "0", "no"}:
        return False
    return None


def _ledger_path(path: object) -> str | None:
    return Path(path).as_posix() if path is not None else None


def _parse_array(value: object) -> list | None:
    if value in (None, ""):
        return None
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[0] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return parsed
        parts = [item.strip() for item in re.split(r"[;,]", text) if item.strip()]
        return parts or None
    return [value]


def _field(row: dict, *names: str) -> object:
    for name in names:
        if name in row:
            value = row.get(name)
            return None if value == "" else value
    return None


def get_git_sha(repo_root: Path | str | None = None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    value = result.stdout.strip()
    return value or None


def infer_source(env: dict[str, str] | None = None) -> str:
    values = env or os.environ
    return "github_actions" if values.get("GITHUB_ACTIONS") == "true" else "local"


def _load_report_timestamp(json_path: Path, fallback: datetime | None = None) -> str:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        generated_at = payload.get("generated_at")
        if generated_at:
            return str(generated_at)
    except (OSError, json.JSONDecodeError):
        pass
    timestamp = fallback or datetime.fromtimestamp(json_path.stat().st_mtime)
    return timestamp.isoformat(timespec="seconds")


def _event_file_path(ledger_root: Path, report_timestamp: str) -> Path:
    try:
        parsed = datetime.fromisoformat(report_timestamp.replace("Z", "+00:00"))
    except ValueError:
        parsed = datetime.now(timezone.utc)
    return (
        ledger_root
        / "events"
        / parsed.strftime("%Y")
        / parsed.strftime("%m")
        / f"research_events_{parsed.strftime('%Y%m%d')}.jsonl"
    )


def append_events(
    events: list[dict],
    *,
    ledger_root: Path | str = DEFAULT_LEDGER_ROOT,
    report_timestamp: str,
) -> Path:
    event_list = list(events)
    validate_events(event_list)
    serialized_lines = [f"{canonical_json(event)}\n" for event in event_list]
    event_file = _event_file_path(Path(ledger_root), report_timestamp)
    event_file.parent.mkdir(parents=True, exist_ok=True)
    with event_file.open("a", encoding="utf-8", newline="\n") as file:
        file.writelines(serialized_lines)
    return event_file


def _read_csv_rows(csv_path: Path) -> list[dict]:
    with csv_path.open(newline="", encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _json_row_count(json_path: Path) -> int | None:
    try:
        payload = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    rows = ((payload.get("simulation") or {}).get("rows"))
    return len(rows) if isinstance(rows, list) else None


def _ticker_payload(
    row: dict,
    *,
    run_id: str,
    source_report_hash: str,
    row_index: int,
) -> dict:
    ticker = _field(row, "ticker")
    return {
        "observation_id": stable_observation_id(run_id, ticker, source_report_hash),
        "ticker": ticker,
        "current_grade": _field(row, "current_grade"),
        "simulated_grade": _field(row, "simulated_grade"),
        "shadow_score": _parse_number(_field(row, "shadow_score")),
        "shadow_grade": _field(row, "shadow_grade"),
        "rs_percentile": _parse_number(_field(row, "rs_percentile")),
        "trend_template_pass": _parse_bool(_field(row, "trend_template_pass")),
        "pivot_status": _field(row, "pivot_status"),
        "shadow_passed": _parse_bool(_field(row, "shadow_passed")),
        "shadow_reject_reasons": _parse_array(_field(row, "shadow_reject_reasons", "reject_reasons")),
        "warning_flags": _parse_array(_field(row, "warning_flags")),
        "stop_distance": _parse_number(_field(row, "stop_distance", "stop_distance_pct")),
        "volume_confirmation_ratio": _parse_number(
            _field(row, "volume_confirmation_ratio", "volume_ratio")
        ),
        "contraction_count": _parse_number(_field(row, "contraction_count")),
        "contraction_depths": _parse_array(_field(row, "contraction_depths")),
        "base_depth": _parse_number(_field(row, "base_depth")),
        "base_duration": _parse_number(_field(row, "base_duration", "base_duration_days")),
        "raw_row_index": row_index,
    }


def _source_summary(result: dict, report_files: dict, data_quality_warnings: list[str]) -> dict:
    funnel = result.get("funnel") or {}
    liquidity_passed = result.get("liquidity_passed")
    setup_passed = result.get("setup_passed")
    return {
        "market_regime": result.get("market_regime"),
        "universe_size": result.get("universe_size"),
        "scanned_count": result.get("scanned"),
        "liquidity_pass_count": (
            liquidity_passed if liquidity_passed is not None else funnel.get("liquidity_passed")
        ),
        "setup_count": setup_passed if setup_passed is not None else funnel.get("setup_passed"),
        "generated_report_paths": [
            _ledger_path(report_files.get("csv")),
            _ledger_path(report_files.get("json")),
        ],
        "data_quality_warnings": data_quality_warnings,
    }


def write_research_ledger_for_shadow_reports(
    result: dict,
    report_files: dict,
    *,
    ledger_root: Path | str = DEFAULT_LEDGER_ROOT,
    now: datetime | None = None,
    env: dict[str, str] | None = None,
    git_sha: str | None = None,
    repo_root: Path | str | None = None,
) -> dict:
    """Append event-sourced ledger entries for generated dry-run reports."""
    if not report_files.get("csv") or not report_files.get("json"):
        return {}
    csv_path = Path(report_files["csv"])
    json_path = Path(report_files["json"])
    if not csv_path.exists() or not json_path.exists():
        return {}

    values = env or os.environ
    source = infer_source(values)
    git_sha = git_sha if git_sha is not None else get_git_sha(repo_root)
    report_timestamp = _load_report_timestamp(json_path, fallback=now)
    run_id = build_run_id(
        source=source,
        report_timestamp=report_timestamp,
        workflow_run_id=values.get("GITHUB_RUN_ID"),
        attempt=values.get("GITHUB_RUN_ATTEMPT"),
        git_sha=git_sha,
    )
    ledger_root = Path(ledger_root)
    artifact_dir = ledger_root / "artifacts" / run_id / "source_reports"
    copied_csv = copy_source_report(csv_path, artifact_dir)
    copied_json = copy_source_report(json_path, artifact_dir)

    csv_rows = _read_csv_rows(csv_path)
    csv_sha = sha256_file(csv_path)
    json_rows = _json_row_count(json_path)
    event_timestamp = utc_now_iso(now)
    empty_report = len(csv_rows) == 0
    data_quality_warnings = ["empty_report"] if empty_report else []

    events = [
        create_report_generated_event(
            run_id=run_id,
            git_sha=git_sha,
            source=source,
            event_timestamp=event_timestamp,
            payload={
                "report_timestamp": report_timestamp,
                "csv_artifact": artifact_metadata(
                    source_path=csv_path,
                    copied_path=copied_csv,
                    row_count=len(csv_rows),
                ),
                "json_artifact": artifact_metadata(
                    source_path=json_path,
                    copied_path=copied_json,
                    row_count=json_rows,
                ),
                "empty_report_flag": empty_report,
                "source_summary": _source_summary(result, report_files, data_quality_warnings),
            },
        )
    ]

    for index, row in enumerate(csv_rows):
        events.append(
            create_ticker_observed_event(
                run_id=run_id,
                git_sha=git_sha,
                source=source,
                event_timestamp=event_timestamp,
                payload=_ticker_payload(
                    row,
                    run_id=run_id,
                    source_report_hash=csv_sha,
                    row_index=index,
                ),
            )
        )

    events.append(
        create_data_quality_event(
            run_id=run_id,
            git_sha=git_sha,
            source=source,
            event_timestamp=event_timestamp,
            warning_code="quality_check_passed",
            severity="info",
            details={
                "report_timestamp": report_timestamp,
                "csv_path": _ledger_path(csv_path),
                "json_path": _ledger_path(json_path),
                "row_count": len(csv_rows),
            },
        )
    )
    if empty_report:
        events.append(
            create_data_quality_event(
                run_id=run_id,
                git_sha=git_sha,
                source=source,
                event_timestamp=event_timestamp,
                warning_code="empty_report",
                severity="warning",
                details={
                    "report_timestamp": report_timestamp,
                    "csv_path": _ledger_path(csv_path),
                    "json_path": _ledger_path(json_path),
                    "row_count": 0,
                },
            )
        )

    event_file = append_events(events, ledger_root=ledger_root, report_timestamp=report_timestamp)
    return {
        "run_id": run_id,
        "event_file": _ledger_path(event_file),
        "artifact_dir": _ledger_path(artifact_dir),
        "csv_artifact_path": _ledger_path(copied_csv),
        "json_artifact_path": _ledger_path(copied_json),
        "event_count": len(events),
        "row_count": len(csv_rows),
        "empty_report_flag": empty_report,
    }
