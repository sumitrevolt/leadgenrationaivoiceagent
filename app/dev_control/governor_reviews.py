"""Fail-closed Claude + ChatGPT review ledger for proposal artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.dev_control.context_packets import redact_packet_text
from app.dev_control.governor_auth import ATTESTATION_VERSION, nonce_fingerprint

REQUIRED_GOVERNORS = ("chatgpt", "claude")
VALID_DECISIONS = ("approve", "changes_requested", "reject")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def artifact_sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def load_worker_report(value: str | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "")
        return dict(parsed) if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def review_gate_status(value: str | dict[str, Any] | None) -> dict[str, Any]:
    report = load_worker_report(value)
    current_hash = str(report.get("proposal_sha256") or "").lower()
    reviews = report.get("governor_reviews")
    if not _SHA256_RE.fullmatch(current_hash) or not isinstance(reviews, dict):
        return {
            "approved": False,
            "artifact_hash": current_hash or None,
            "approved_governors": [],
            "missing_governors": list(REQUIRED_GOVERNORS),
            "blocking_decisions": [],
        }

    approved: list[str] = []
    blocking: list[dict[str, str]] = []
    for governor in REQUIRED_GOVERNORS:
        review = reviews.get(governor)
        if not isinstance(review, dict):
            continue
        decision = str(review.get("decision") or "")
        review_hash = str(review.get("artifact_hash") or "").lower()
        attestation_version = str(review.get("attestation_version") or "")
        attestation_nonce_sha256 = str(review.get("attestation_nonce_sha256") or "").lower()
        if attestation_version != ATTESTATION_VERSION or not _SHA256_RE.fullmatch(
            attestation_nonce_sha256
        ):
            blocking.append({"governor": governor, "decision": "attestation_missing_or_invalid"})
        elif review_hash != current_hash:
            blocking.append({"governor": governor, "decision": "artifact_hash_mismatch"})
        elif decision == "approve":
            approved.append(governor)
        elif decision in VALID_DECISIONS:
            blocking.append({"governor": governor, "decision": decision})

    missing = [name for name in REQUIRED_GOVERNORS if name not in approved]
    return {
        "approved": not missing and not blocking,
        "artifact_hash": current_hash,
        "approved_governors": approved,
        "missing_governors": missing,
        "blocking_decisions": blocking,
    }


def record_governor_review(
    value: str | dict[str, Any] | None,
    *,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
    reviewed_by: str,
    reviewed_at: str | None = None,
    attestation_version: str | None = None,
    attestation_nonce: str | None = None,
) -> dict[str, Any]:
    report = load_worker_report(value)
    governor = str(governor).strip().lower()
    decision = str(decision).strip().lower()
    supplied_hash = str(artifact_hash).strip().lower()
    current_hash = str(report.get("proposal_sha256") or "").strip().lower()
    if governor not in REQUIRED_GOVERNORS:
        raise ValueError("unknown_governor")
    if decision not in VALID_DECISIONS:
        raise ValueError("invalid_review_decision")
    if not _SHA256_RE.fullmatch(current_hash):
        raise ValueError("proposal_hash_missing_or_invalid")
    if not _SHA256_RE.fullmatch(supplied_hash) or supplied_hash != current_hash:
        raise ValueError("artifact_hash_mismatch")
    if attestation_version != ATTESTATION_VERSION or not attestation_nonce:
        raise ValueError("attestation_required")

    reviews = report.get("governor_reviews")
    reviews = dict(reviews) if isinstance(reviews, dict) else {}
    nonce_hash = nonce_fingerprint(attestation_nonce)
    if any(
        isinstance(review, dict) and review.get("attestation_nonce_sha256") == nonce_hash
        for review in reviews.values()
    ):
        raise ValueError("attestation_replayed")
    reviews[governor] = {
        "governor": governor,
        "decision": decision,
        "artifact_hash": supplied_hash,
        "summary": redact_packet_text(str(summary))[:1000],
        "reviewed_by": str(reviewed_by)[:180],
        "reviewed_at": reviewed_at or datetime.utcnow().isoformat(),
        "attestation_version": ATTESTATION_VERSION,
        "attestation_nonce_sha256": nonce_hash,
    }
    report["governor_reviews"] = reviews
    return report
