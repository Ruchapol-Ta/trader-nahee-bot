"""Immutable raw-artifact handling for research ledger writes."""

from __future__ import annotations

import shutil
from pathlib import Path

from research.hashing import byte_size, sha256_file


def _ledger_path(path: Path | str) -> str:
    return Path(path).as_posix()


def copy_source_report(source_path: Path | str, artifact_dir: Path | str) -> Path:
    source = Path(source_path)
    destination_dir = Path(artifact_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    if destination.exists():
        if sha256_file(destination) != sha256_file(source):
            raise RuntimeError(f"artifact path already exists with different content: {destination}")
        return destination
    shutil.copy2(source, destination)
    return destination


def artifact_metadata(
    *,
    source_path: Path | str,
    copied_path: Path | str,
    row_count: int | None,
) -> dict:
    source = Path(source_path)
    copied = Path(copied_path)
    return {
        "source_path": _ledger_path(source),
        "copied_path": _ledger_path(copied),
        "sha256": sha256_file(source),
        "byte_size": byte_size(source),
        "row_count": row_count,
    }
