"""Scoped HMAC authentication for trusted Claude/ChatGPT review adapters.

Only the trusted control-plane adapter sees its governor-specific environment
secret. Signatures, nonces and timestamps authorize one bounded review payload;
they never grant repository, tool, provider, or deployment access.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import time
from typing import Any

ATTESTATION_VERSION = "hmac-sha256-v1"
SECRET_MIN_CHARS = 32
MAX_PAST_AGE_SECONDS = 300
MAX_FUTURE_SKEW_SECONDS = 30

_SECRET_ENV = {
    "claude": "DEV_CLAUDE_REVIEW_SECRET",
    "chatgpt": "DEV_CHATGPT_REVIEW_SECRET",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")


def _configured_secret(governor: str) -> str:
    name = _SECRET_ENV.get(str(governor).strip().lower(), "")
    secret = os.getenv(name, "").strip() if name else ""
    return secret if len(secret) >= SECRET_MIN_CHARS else ""


def governor_auth_status() -> dict[str, Any]:
    """Configuration booleans only; never return names, values or fingerprints."""
    return {
        "attestation_version": ATTESTATION_VERSION,
        "claude_configured": bool(_configured_secret("claude")),
        "chatgpt_configured": bool(_configured_secret("chatgpt")),
        "required_secret_min_chars": SECRET_MIN_CHARS,
    }


def _canonical_payload(
    *,
    task_id: str,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
    issued_at: int,
    nonce: str,
) -> bytes:
    payload = {
        "artifact_hash": str(artifact_hash).strip().lower(),
        "decision": str(decision).strip().lower(),
        "governor": str(governor).strip().lower(),
        "issued_at": int(issued_at),
        "nonce": str(nonce),
        "summary_sha256": hashlib.sha256(str(summary).encode("utf-8")).hexdigest(),
        "task_id": str(task_id),
        "version": ATTESTATION_VERSION,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def build_governor_signature(
    *,
    secret: str,
    task_id: str,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
    issued_at: int,
    nonce: str,
) -> str:
    """Trusted-adapter helper. Callers must never log ``secret``."""
    payload = _canonical_payload(
        task_id=task_id,
        governor=governor,
        decision=decision,
        artifact_hash=artifact_hash,
        summary=summary,
        issued_at=issued_at,
        nonce=nonce,
    )
    return hmac.new(str(secret).encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_governor_attestation(
    *,
    task_id: str,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
    issued_at: str | int | None,
    nonce: str | None,
    signature: str | None,
    now: int | None = None,
) -> dict[str, Any]:
    """Fail closed on missing config, malformed input, stale time or bad HMAC."""
    governor = str(governor).strip().lower()
    decision = str(decision).strip().lower()
    artifact_hash = str(artifact_hash).strip().lower()
    nonce = str(nonce or "")
    signature = str(signature or "").strip().lower()
    secret = _configured_secret(governor)
    if not secret:
        return {"ok": False, "reason": "secret_unconfigured", "version": ATTESTATION_VERSION}
    try:
        issued_at_int = int(str(issued_at))
    except (TypeError, ValueError):
        return {"ok": False, "reason": "attestation_malformed", "version": ATTESTATION_VERSION}
    if (
        not task_id
        or governor not in _SECRET_ENV
        or decision not in {"approve", "changes_requested", "reject"}
        or not _SHA256_RE.fullmatch(artifact_hash)
        or not _NONCE_RE.fullmatch(nonce)
        or not _SHA256_RE.fullmatch(signature)
    ):
        return {"ok": False, "reason": "attestation_malformed", "version": ATTESTATION_VERSION}

    current = int(time.time()) if now is None else int(now)
    if (
        issued_at_int < current - MAX_PAST_AGE_SECONDS
        or issued_at_int > current + MAX_FUTURE_SKEW_SECONDS
    ):
        return {"ok": False, "reason": "timestamp_outside_window", "version": ATTESTATION_VERSION}

    expected = build_governor_signature(
        secret=secret,
        task_id=task_id,
        governor=governor,
        decision=decision,
        artifact_hash=artifact_hash,
        summary=summary,
        issued_at=issued_at_int,
        nonce=nonce,
    )
    if not hmac.compare_digest(expected, signature):
        return {"ok": False, "reason": "signature_invalid", "version": ATTESTATION_VERSION}
    return {"ok": True, "reason": "verified", "version": ATTESTATION_VERSION}


def nonce_fingerprint(nonce: str) -> str:
    """Persist only a one-way nonce digest for replay detection."""
    return hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()


def build_configured_governor_headers(
    *,
    task_id: str,
    governor: str,
    decision: str,
    artifact_hash: str,
    summary: str,
    issued_at: int | None = None,
    nonce: str | None = None,
) -> dict[str, str]:
    """Build short-lived headers without returning or logging the env secret."""
    secret = _configured_secret(governor)
    if not secret:
        raise ValueError("governor_secret_unconfigured")
    timestamp = int(time.time()) if issued_at is None else int(issued_at)
    nonce_value = nonce or secrets.token_urlsafe(24)
    if not _NONCE_RE.fullmatch(nonce_value):
        raise ValueError("attestation_nonce_invalid")
    signature = build_governor_signature(
        secret=secret,
        task_id=task_id,
        governor=governor,
        decision=decision,
        artifact_hash=artifact_hash,
        summary=summary,
        issued_at=timestamp,
        nonce=nonce_value,
    )
    return {
        "X-Governor-Timestamp": str(timestamp),
        "X-Governor-Nonce": nonce_value,
        "X-Governor-Signature": signature,
    }
