"""Schema constants and validation for research ledger events."""

from __future__ import annotations


SCHEMA_VERSION = 1
PRODUCER = "shadow-research-ledger"
PRODUCER_VERSION = "1.0.0"
ALLOWED_EVENT_TYPES = {
    "report_generated",
    "ticker_observed",
    "data_quality_event",
}
REQUIRED_TOP_LEVEL_FIELDS = {
    "schema_version",
    "producer",
    "producer_version",
    "event_type",
    "event_id",
    "event_timestamp",
    "run_id",
    "git_sha",
    "source",
    "payload",
}
REQUIRED_ARTIFACT_FIELDS = {
    "source_path",
    "copied_path",
    "sha256",
    "byte_size",
    "row_count",
}


class EventValidationError(ValueError):
    """Raised when a research ledger event does not match the schema."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EventValidationError(message)


def _validate_report_generated(payload: dict) -> None:
    _require(bool(payload.get("report_timestamp")), "report_generated requires report_timestamp")
    for key in ("csv_artifact", "json_artifact"):
        artifact = payload.get(key)
        _require(isinstance(artifact, dict), f"report_generated requires {key}")
        missing = REQUIRED_ARTIFACT_FIELDS - set(artifact)
        _require(not missing, f"{key} missing required fields: {sorted(missing)}")


def _validate_ticker_observed(payload: dict) -> None:
    _require(bool(payload.get("observation_id")), "ticker_observed requires observation_id")
    _require(bool(payload.get("ticker")), "ticker_observed requires ticker")


def _validate_data_quality_event(payload: dict) -> None:
    _require(bool(payload.get("warning_code")), "data_quality_event requires warning_code")
    _require(bool(payload.get("severity")), "data_quality_event requires severity")
    _require(isinstance(payload.get("details"), dict), "data_quality_event requires details")


def validate_event(event: dict) -> None:
    missing = REQUIRED_TOP_LEVEL_FIELDS - set(event)
    _require(not missing, f"event missing required fields: {sorted(missing)}")
    _require(event.get("schema_version") == SCHEMA_VERSION, "event schema_version mismatch")
    _require(event.get("producer") == PRODUCER, "event producer mismatch")
    _require(bool(event.get("producer_version")), "event requires producer_version")
    event_type = event.get("event_type")
    _require(event_type in ALLOWED_EVENT_TYPES, f"event_type not allowed: {event_type}")
    _require(isinstance(event.get("payload"), dict), "event payload must be a dict")
    if event_type == "report_generated":
        _validate_report_generated(event["payload"])
    elif event_type == "ticker_observed":
        _validate_ticker_observed(event["payload"])
    elif event_type == "data_quality_event":
        _validate_data_quality_event(event["payload"])


def validate_events(events: list[dict]) -> None:
    for event in events:
        validate_event(event)
