"""Cutover marker — schema and validator ONLY. Never written to production here.

The marker answers one question: *has the external runtime root been verified to
hold this exact set of migrated stores, from this exact release?*

It must represent **verified** state, not merely configured state. A marker that
says "configured" would let a destructive deploy proceed over data nobody
actually checked — which is the whole failure this control plane exists to stop.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.platform import runtime_data_manifest as manifest

SCHEMA_VERSION = "1"
MARKER_RELATIVE_PATH = ("migration", "cutover.json")

REQUIRED_FIELDS = (
    "schema_version",
    "manifest_version",
    "runtime_root_identifier",
    "source_production_sha",
    "migrated_store_ids",
    "source_manifest_reference",
    "verification_reference",
    "cutover_started_at",
    "cutover_completed_at",
    "validation_status",
    "rollback_reference",
)

VALIDATION_PASSED = "PASSED"


def _parse_ts(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def validate_marker(
    marker: dict[str, Any],
    *,
    runtime_root_identifier: str | None = None,
    required_store_ids: set[str] | None = None,
) -> list[str]:
    """Return a list of problems. Empty list == the marker may be trusted."""
    problems: list[str] = []

    for field in REQUIRED_FIELDS:
        if field not in marker:
            problems.append(f"missing field: {field}")
    if problems:
        return problems  # nothing else is meaningful without the shape

    if str(marker["schema_version"]) != SCHEMA_VERSION:
        problems.append(f"schema_version {marker['schema_version']!r} != {SCHEMA_VERSION!r}")
    if str(marker["manifest_version"]) != manifest.MANIFEST_VERSION:
        problems.append(
            f"stale manifest_version {marker['manifest_version']!r}; "
            f"current is {manifest.MANIFEST_VERSION!r}"
        )
    if runtime_root_identifier and str(marker["runtime_root_identifier"]) != str(
        runtime_root_identifier
    ):
        problems.append("runtime_root_identifier does not match configuration")

    sha = str(marker["source_production_sha"] or "")
    if not (7 <= len(sha) <= 40) or not all(c in "0123456789abcdef" for c in sha.lower()):
        problems.append("source_production_sha is malformed")

    if str(marker["validation_status"]) != VALIDATION_PASSED:
        problems.append(
            f"validation_status is {marker['validation_status']!r}, not {VALIDATION_PASSED!r}"
        )

    if not str(marker["rollback_reference"] or "").strip():
        problems.append(
            "rollback_reference is empty — a cutover without a documented rollback is not a cutover"
        )

    ids = list(marker["migrated_store_ids"] or [])
    if len(ids) != len(set(ids)):
        problems.append("duplicate store ids")
    known = {s["store_id"] for s in manifest.STORES}
    unknown = [i for i in ids if i not in known]
    if unknown:
        problems.append(f"unknown store ids: {sorted(unknown)}")

    # A store still recorded as living in the checkout cannot be "migrated".
    by_id = {s["store_id"]: s for s in manifest.STORES}
    for i in ids:
        row = by_id.get(i)
        if row and row.get("migration_state") == manifest.LEGACY_IN_CHECKOUT:
            problems.append(f"{i} is still LEGACY_IN_CHECKOUT but listed as migrated")

    if required_store_ids:
        missing = sorted(required_store_ids - set(ids))
        if missing:
            problems.append(f"incomplete migrated store set; missing: {missing}")

    started = _parse_ts(marker["cutover_started_at"])
    completed = _parse_ts(marker["cutover_completed_at"])
    if started is None:
        problems.append("cutover_started_at is not a valid timestamp")
    if completed is None:
        problems.append("cutover_completed_at is not a valid timestamp")
    if started and completed and completed < started:
        problems.append("cutover_completed_at precedes cutover_started_at")

    return problems


def validate_marker_file(path: Path, **kw: Any) -> list[str]:
    """Validate a marker on disk. A missing/malformed file is itself a problem."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ["marker file absent"]
    except Exception as e:
        return [f"marker file unreadable: {str(e)[:120]}"]
    if not isinstance(raw, dict):
        return ["marker is not a JSON object"]
    return validate_marker(raw, **kw)


def example_marker() -> dict[str, Any]:
    """Shape reference for the runbook and tests. NOT a production marker."""
    return {
        "schema_version": SCHEMA_VERSION,
        "manifest_version": manifest.MANIFEST_VERSION,
        "runtime_root_identifier": "/var/lib/leadgen/runtime",
        "source_production_sha": "0000000",
        "migrated_store_ids": [],
        "source_manifest_reference": "app/platform/runtime_data_manifest.py",
        "verification_reference": "docs/runbooks/<evidence-file>",
        "cutover_started_at": "2026-01-01T00:00:00+00:00",
        "cutover_completed_at": "2026-01-01T01:00:00+00:00",
        "validation_status": VALIDATION_PASSED,
        "rollback_reference": "<prior production sha>",
        "created_by": "<operator>",
    }


__all__ = [
    "SCHEMA_VERSION",
    "MARKER_RELATIVE_PATH",
    "REQUIRED_FIELDS",
    "VALIDATION_PASSED",
    "validate_marker",
    "validate_marker_file",
    "example_marker",
]
