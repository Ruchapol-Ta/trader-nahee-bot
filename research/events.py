"""Event construction for the research ledger."""

from __future__ import annotations

from datetime import datetime, timezone

from research.ids import stable_event_id
from research.schema import PRODUCER, PRODUCER_VERSION, SCHEMA_VERSION


def utc_now_iso(now: datetime | None = None) -> str:
    timestamp = now or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")


def json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    try:
        return json_safe(value.item())
    except AttributeError:
        return str(value)


def make_event(
    *,
    event_type: str,
    run_id: str,
    git_sha: str | None,
    source: str,
    payload: dict,
    event_timestamp: str,
) -> dict:
    payload = json_safe(payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "producer": PRODUCER,
        "producer_version": PRODUCER_VERSION,
        "event_type": event_type,
        "event_id": stable_event_id(event_type, run_id, payload),
        "event_timestamp": event_timestamp,
        "run_id": run_id,
        "git_sha": git_sha,
        "source": source,
        "payload": payload,
    }


def create_report_generated_event(
    *,
    run_id: str,
    git_sha: str | None,
    source: str,
    event_timestamp: str,
    payload: dict,
) -> dict:
    return make_event(
        event_type="report_generated",
        run_id=run_id,
        git_sha=git_sha,
        source=source,
        event_timestamp=event_timestamp,
        payload=payload,
    )


def create_ticker_observed_event(
    *,
    run_id: str,
    git_sha: str | None,
    source: str,
    event_timestamp: str,
    payload: dict,
) -> dict:
    return make_event(
        event_type="ticker_observed",
        run_id=run_id,
        git_sha=git_sha,
        source=source,
        event_timestamp=event_timestamp,
        payload=payload,
    )


def create_data_quality_event(
    *,
    run_id: str,
    git_sha: str | None,
    source: str,
    event_timestamp: str,
    warning_code: str,
    severity: str,
    details: dict,
) -> dict:
    return make_event(
        event_type="data_quality_event",
        run_id=run_id,
        git_sha=git_sha,
        source=source,
        event_timestamp=event_timestamp,
        payload={
            "warning_code": warning_code,
            "severity": severity,
            "details": details,
        },
    )
