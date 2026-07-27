"""Governed record of every unresolved-baseline expansion.

Replacing the baseline and then reporting "new unresolved = 0" describes the
state AFTER accepting the expansion, not the expansion itself. That is what I
did when the baseline went 691 -> 881: the sentence was true and the impression
was wrong.

So an expansion is only legitimate when it is written down here, with the
detector change that caused it and the exact fingerprints it added. Growth from
a scanner fix is welcome; growth that nobody can account for is not.

This is NOT a bypass. A change record cannot authorise arbitrary new debt: the
ratchet still refuses any added fingerprint that is not listed in a record whose
scanner version actually changed.
"""

from __future__ import annotations

from typing import Any

# Bumped whenever detection SEMANTICS change (new call shapes, new inference).
# Cosmetic edits must not bump it, and a semantic change must not skip it.
SCANNER_ENGINE_VERSION = "2026-07-26.3-local-helper-inference"
SCANNER_SCHEMA_VERSION = "2026-07-26.1"
CLASSIFICATION_VERSION = "2026-07-26.2"

REVIEW_APPROVED = "APPROVED_REVIEWED_EXPANSION"
REVIEW_PENDING = "PENDING_REVIEW"

CHANGES: list[dict[str, Any]] = [
    {
        "change_id": "bce-2026-07-26-local-helper-inference",
        "old_scanner_version": "2026-07-26.2-receiver-path",
        "new_scanner_version": SCANNER_ENGINE_VERSION,
        "old_baseline_count": 691,
        "new_baseline_count": 881,
        "added_fingerprints": 190,
        "removed_fingerprints": 0,
        "reason": "module-local helper write inference added",
        "detector_change": (
            "Writes reached through module-local helpers -- `_append(PATH, rec)`, "
            "`_write_all(PATH, rows)` -- were invisible because only a fixed set of "
            "stdlib call names was recognised. The scanner now infers which local "
            "functions write to a path passed in as a parameter."
        ),
        "affected_files": [
            "app/telephony/consent_ledger.py",
            "app/marketing/wa_campaign_runner.py",
        ],
        "affected_store_candidates": [
            "compliance.consent_ledger",
            "compliance.voice_suppression",
            "compliance.wa_suppression",
        ],
        "review_status": REVIEW_APPROVED,
        "evidence": (
            "consent_ledger.py went 0 -> 12 findings (including the retention-sweep "
            "REWRITE of data/voice_suppression.jsonl at line 529); "
            "wa_campaign_runner.py went 0 -> 19. These are three Tier 0 compliance "
            "authorities that the Tier 0 report had shown as 0 findings -- which meant "
            "no DETECTION, not no debt. The expansion is newly visible debt, not new "
            "debt: no application code changed in the same commit."
        ),
    },
]


def latest() -> dict[str, Any] | None:
    return CHANGES[-1] if CHANGES else None


def validate() -> list[str]:
    """Structural checks. Empty list means the change log is coherent."""
    problems: list[str] = []
    required = (
        "change_id",
        "old_scanner_version",
        "new_scanner_version",
        "old_baseline_count",
        "new_baseline_count",
        "added_fingerprints",
        "removed_fingerprints",
        "reason",
        "detector_change",
        "affected_files",
        "affected_store_candidates",
        "review_status",
        "evidence",
    )
    seen: set[str] = set()
    for c in CHANGES:
        cid = c.get("change_id", "<missing>")
        missing = [f for f in required if f not in c or c[f] in (None, "", [])]
        if missing:
            problems.append(f"{cid}: missing {', '.join(missing)}")
            continue
        if cid in seen:
            problems.append(f"{cid}: duplicate change_id")
        seen.add(cid)
        if c["old_scanner_version"] == c["new_scanner_version"]:
            problems.append(
                f"{cid}: scanner version unchanged — an expansion with identical "
                "detector semantics is new debt, not improved detection"
            )
        arithmetic = c["old_baseline_count"] + c["added_fingerprints"] - c["removed_fingerprints"]
        if arithmetic != c["new_baseline_count"]:
            problems.append(
                f"{cid}: arithmetic does not reconcile — "
                f"{c['old_baseline_count']} + {c['added_fingerprints']} "
                f"- {c['removed_fingerprints']} != {c['new_baseline_count']}"
            )
        if c["review_status"] not in (REVIEW_APPROVED, REVIEW_PENDING):
            problems.append(f"{cid}: unknown review_status {c['review_status']!r}")
    return problems


def expansion_is_governed(baseline_count: int) -> tuple[bool, str]:
    """Does the committed baseline size match an approved change record?"""
    rec = latest()
    if rec is None:
        return baseline_count == 0, "no change records"
    if rec["review_status"] != REVIEW_APPROVED:
        return False, f"{rec['change_id']} is {rec['review_status']}"
    if rec["new_baseline_count"] != baseline_count:
        return (
            False,
            f"baseline holds {baseline_count} fingerprints but the newest approved "
            f"record ({rec['change_id']}) describes {rec['new_baseline_count']}. "
            "Regenerating without a matching record is an ungoverned expansion.",
        )
    return True, rec["change_id"]


__all__ = [
    "SCANNER_ENGINE_VERSION",
    "SCANNER_SCHEMA_VERSION",
    "CLASSIFICATION_VERSION",
    "REVIEW_APPROVED",
    "REVIEW_PENDING",
    "CHANGES",
    "latest",
    "validate",
    "expansion_is_governed",
]
