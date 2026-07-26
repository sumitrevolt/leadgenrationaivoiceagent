"""Loader and validator for the controlled mutable-path allowlist.

An allowlist that is never checked back against the code becomes a list of
things that USED to be true. Every failure mode this validator covers has
already happened somewhere in this repo: a path moved and the note about it
didn't, a store id was typo'd, a writer was filed as read-only.

So validation is bidirectional:
  * every entry must still match a LIVE finding (no stale declarations),
  * every entry must name a real store family,
  * a writer may not be declared against a static/immutable store,
  * a production writer may not be filed as fixture-only.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from app.platform import runtime_data_allowlist_entries as _entries
from app.platform import runtime_data_manifest as _manifest
from app.platform import runtime_data_scan as _scan

ALLOWLIST_PATH = Path(__file__).with_name("runtime_data_allowlist_entries.py")

REQUIRED_FIELDS = (
    "allowlist_id",
    "file",
    "line_or_symbol",
    "path_pattern",
    "store_id",
    "access_modes",
    "reason",
    "migration_tier",
    "target_change_set",
    "owner",
    "production_relevance",
    "review_condition",
)

# Stores that cannot legitimately have a declared WRITER.
IMMUTABLE_STORE_IDS = frozenset({"static.legal_documents"})

_WRITE_MODES = frozenset(
    {"APPEND", "REWRITE", "CREATE", "DELETE", "REPLACE", "LOCK", "SQLITE", "CACHE_WRITE"}
)


def load(path: Path | None = None) -> list[dict[str, Any]]:
    """Deep copy so a caller mutating a returned entry cannot corrupt the
    declaration for everyone else in the same process."""
    return copy.deepcopy(_entries.ENTRIES)


def _store_ids() -> set[str]:
    return {s["store_id"] for s in _manifest.STORES}


def validate(
    entries: list[dict[str, Any]] | None = None,
    findings: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Return a list of problems. Empty list means the allowlist is coherent."""
    entries = load() if entries is None else entries
    problems: list[str] = []
    known_stores = _store_ids()

    seen: set[str] = set()
    for e in entries:
        eid = e.get("allowlist_id", "<missing id>")

        missing = [f for f in REQUIRED_FIELDS if f not in e or e[f] in (None, "", [])]
        if missing:
            problems.append(f"{eid}: missing required fields: {', '.join(missing)}")
            continue

        if eid in seen:
            problems.append(f"{eid}: duplicate allowlist_id")
        seen.add(eid)

        if e["store_id"] not in known_stores:
            problems.append(f"{eid}: unknown store_id {e['store_id']!r}")

        modes = set(e["access_modes"])
        if modes & _WRITE_MODES and e["store_id"] in IMMUTABLE_STORE_IDS:
            problems.append(
                f"{eid}: declares write modes {sorted(modes & _WRITE_MODES)} "
                f"against immutable store {e['store_id']}"
            )

        if not isinstance(e["migration_tier"], int):
            problems.append(f"{eid}: migration_tier must be an integer wave")

        if e["production_relevance"] == "FIXTURE" and modes & _WRITE_MODES:
            problems.append(f"{eid}: production writer filed as FIXTURE")

        src = Path(__file__).resolve().parents[2] / e["file"]
        if not src.is_file():
            problems.append(f"{eid}: file no longer exists: {e['file']}")

    if findings is not None:
        problems.extend(_check_liveness(entries, findings))
    return problems


def _check_liveness(entries: list[dict[str, Any]], findings: list[dict[str, Any]]) -> list[str]:
    """Every entry must still correspond to real code, and the declared access
    modes must actually be the ones observed.

    Without this an allowlist quietly becomes documentation of the past: the
    declaration survives long after the code it excused has moved.
    """
    problems: list[str] = []
    by_key: dict[str, set[str]] = {}
    for f in findings:
        by_key.setdefault(f"{f['file']}:{f['line']}", set()).add(f["operation"])
        if f.get("symbol"):
            by_key.setdefault(f"{f['file']}:{f['symbol']}", set()).add(f["operation"])

    for e in entries:
        key = f"{e['file']}:{e['line_or_symbol']}"
        observed = by_key.get(key)
        if observed is None:
            problems.append(
                f"{e['allowlist_id']}: STALE — no live finding at {key}. "
                "Remove the entry or point it at the code that replaced it."
            )
            continue
        declared = set(e["access_modes"])
        undeclared_ops = observed - declared
        if undeclared_ops:
            problems.append(
                f"{e['allowlist_id']}: operation mismatch at {key} — code performs "
                f"{sorted(undeclared_ops)} which the entry does not declare"
            )
    return problems


def index(entries: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Entries in the shape `runtime_data_scan.scan_repo` expects."""
    return load() if entries is None else entries


def coverage(findings: list[dict[str, Any]]) -> dict[str, int]:
    """Gate-relevant counts, all derived — never hand-maintained."""
    return {
        "undeclared_mutable_paths": sum(
            1 for f in findings if f["classification"] == _scan.UNDECLARED_MUTABLE_PATH
        ),
        "ambiguous_mutable_paths": sum(
            1 for f in findings if f["classification"] == _scan.AMBIGUOUS_REQUIRES_REVIEW
        ),
        "declared_legacy_writes": sum(
            1 for f in findings if f["classification"] == _scan.DECLARED_LEGACY_WRITE
        ),
        "declared_legacy_reads": sum(
            1 for f in findings if f["classification"] == _scan.DECLARED_LEGACY_READ
        ),
        "canonical": sum(
            1 for f in findings if f["classification"] == _scan.CANONICAL_RUNTIME_PATH
        ),
    }


__all__ = [
    "ALLOWLIST_PATH",
    "REQUIRED_FIELDS",
    "IMMUTABLE_STORE_IDS",
    "load",
    "validate",
    "index",
    "coverage",
]
