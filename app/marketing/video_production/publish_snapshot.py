"""Stage 3C — publish consumes the finalized immutable snapshot only.

Identity and idempotency for provider invocation. Never opens the mutable
``video_path``. The gate observes the snapshot; the publisher re-hashes the
same path immediately before any provider call.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

_SCHEMA = 1


def canonical_publish_identity(
    *,
    tenant: str,
    video_id: str,
    approval_txn: str,
    revision: int,
    snapshot_sha256: str,
    snapshot_bytes: int,
    channel: str,
) -> dict[str, Any]:
    """Canonical identity object — JSON-serialised for the idempotency key.

    Deliberately excludes filename, mutable path, and pipe-joined strings.
    """
    return {
        "schema": _SCHEMA,
        "tenant": str(tenant or "").strip(),
        "video_id": str(video_id or "").strip(),
        "approval_txn": str(approval_txn or "").strip(),
        "revision": int(revision),
        "snapshot_sha256": str(snapshot_sha256 or "").strip().lower(),
        "snapshot_bytes": int(snapshot_bytes),
        "channel": str(channel or "").strip(),
    }


def publish_idempotency_key(identity: dict[str, Any]) -> str:
    """SHA-256 over canonical JSON (sorted keys, no whitespace). Prefix ``vap:``."""
    blob = json.dumps(identity, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return f"vap:{digest}"


def verify_snapshot_descriptor(
    *,
    snapshot_path: str,
    expected_sha256: str,
    expected_bytes: int,
) -> dict[str, Any]:
    """Re-hash the snapshot immediately before provider invocation.

    Refuses missing/unreadable/out-of-root/symlink/non-regular/changed bytes.
    """
    from app.marketing.video_production.publish_gate import hash_video_file

    live_hash, live_size = hash_video_file(str(snapshot_path or ""))
    exp = str(expected_sha256 or "").strip().lower()
    if not live_hash:
        return {"ok": False, "error": "snapshot_unverifiable"}
    if live_hash != exp or int(live_size) != int(expected_bytes):
        return {
            "ok": False,
            "error": "snapshot_changed_before_provider",
            "expected_sha256": exp,
            "live_sha256": live_hash,
            "expected_bytes": int(expected_bytes),
            "live_bytes": int(live_size),
        }
    return {
        "ok": True,
        "snapshot_path": str(snapshot_path),
        "content_sha256": live_hash,
        "content_bytes": int(live_size),
    }


__all__ = [
    "canonical_publish_identity",
    "publish_idempotency_key",
    "verify_snapshot_descriptor",
]
