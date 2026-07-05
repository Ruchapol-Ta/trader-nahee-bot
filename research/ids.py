"""Stable identifiers for research ledger events."""

from __future__ import annotations

import hashlib
import json
import re


_SAFE_ID_PATTERN = re.compile(r"[^A-Za-z0-9_.=-]+")


def canonical_json(value: object) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)


def _short_hash(value: str, prefix: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def stable_event_id(event_type: str, run_id: str, payload: dict) -> str:
    """Return a deterministic event id from immutable event content."""
    return _short_hash(
        canonical_json({
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
        }),
        "evt",
    )


def stable_observation_id(
    run_id: str,
    ticker: object,
    source_report_hash: str,
) -> str:
    """Return a deterministic ticker-observation id independent of report order."""
    return _short_hash(
        "\0".join([
            str(run_id),
            str(ticker or ""),
            str(source_report_hash),
        ]),
        "obs",
    )


def _safe_path_id(value: str) -> str:
    safe = _SAFE_ID_PATTERN.sub("-", value).strip("-")
    return safe or "unknown"


def _timestamp_slug(report_timestamp: str | None) -> str:
    if not report_timestamp:
        return "unknown-time"
    return _SAFE_ID_PATTERN.sub("", report_timestamp.replace("-", "").replace(":", ""))


def build_run_id(
    *,
    source: str,
    report_timestamp: str | None,
    workflow_run_id: str | None = None,
    attempt: str | None = None,
    git_sha: str | None = None,
) -> str:
    stamp = _timestamp_slug(report_timestamp)
    workflow = workflow_run_id or "local"
    attempt_value = attempt or "0"
    sha_value = (git_sha or "unknown")[:12]
    return _safe_path_id(
        f"{source}_{stamp}_run-{workflow}_attempt-{attempt_value}_git-{sha_value}"
    )
