"""Compatibility wrapper for the research ledger package."""

from research import (
    ALLOWED_EVENT_TYPES,
    PRODUCER,
    PRODUCER_VERSION,
    SCHEMA_VERSION,
    EventValidationError,
    append_events,
    build_run_id,
    byte_size,
    get_git_sha,
    infer_source,
    sha256_file,
    stable_event_id,
    stable_observation_id,
    validate_event,
    validate_events,
    write_research_ledger_for_shadow_reports,
)

__all__ = [
    "ALLOWED_EVENT_TYPES",
    "EventValidationError",
    "PRODUCER",
    "PRODUCER_VERSION",
    "SCHEMA_VERSION",
    "append_events",
    "build_run_id",
    "byte_size",
    "get_git_sha",
    "infer_source",
    "sha256_file",
    "stable_event_id",
    "stable_observation_id",
    "validate_event",
    "validate_events",
    "write_research_ledger_for_shadow_reports",
]
