"""Stage 3C — publish consumes a once-opened verified snapshot descriptor.

Identity and local publish-reservation helpers. Never opens the mutable
``video_path``. Provider upload MUST stream from the same file descriptor that
was hashed; hashing a path and then re-opening that path is NOT a closed race.

Postiz public API (docs inspected 2026-07-30) does **not** document an
idempotency-key contract for ``/public/v1/posts`` or ``/upload``. Therefore this
module never claims exactly-once *external* publication — only durable local
reservation / outcome states.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from typing import Any, BinaryIO

_SCHEMA = 1
_HASH_CHUNK = 1024 * 1024

# Honest local attempt machine. External exactly-once is NOT claimed.
PUBLISH_RESERVED = "publish_reserved"
PROVIDER_INFLIGHT = "provider_inflight"
PUBLISHED = "published"
PUBLISH_OUTCOME_UNKNOWN = "publish_outcome_unknown"
PUBLISH_REFUSED = "publish_refused"
PUBLISH_FAILED = "publish_failed"

# Postiz public API: no documented Idempotency-Key / replay contract.
PROVIDER_ACCEPTS_IDEMPOTENCY_KEY = False


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
    """Canonical identity object — JSON-serialised for the local reservation key.

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


def open_verified_snapshot(
    *,
    snapshot_path: str,
    expected_sha256: str,
    expected_bytes: int,
) -> dict[str, Any]:
    """Open the snapshot exactly once (``O_NOFOLLOW``) and verify on that fd.

    Sequence: resolve → ``os.open`` once → ``fstat`` → streaming hash → ``fstat``
    → compare expected digest/size → ``seek(0)``. Caller owns ``fh`` and MUST
    close it on success, error, or disconnect. A second path open for upload is
    a contract violation.
    """
    from app.marketing.video_media_paths import resolve_video_media_file

    exp = str(expected_sha256 or "").strip().lower()
    exp_bytes = int(expected_bytes)
    resolved = resolve_video_media_file(str(snapshot_path or ""))
    if resolved is None:
        return {"ok": False, "error": "snapshot_unverifiable"}

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fh: BinaryIO | None = None
    try:
        fd = os.open(resolved, flags)
        fh = os.fdopen(fd, "rb")
        before = os.fstat(fh.fileno())
        if not stat.S_ISREG(before.st_mode):
            fh.close()
            return {"ok": False, "error": "snapshot_unverifiable"}
        h = hashlib.sha256()
        size = 0
        while chunk := fh.read(_HASH_CHUNK):
            h.update(chunk)
            size += len(chunk)
        after = os.fstat(fh.fileno())
        if (before.st_ino, before.st_dev, before.st_size, before.st_mtime_ns) != (
            after.st_ino,
            after.st_dev,
            after.st_size,
            after.st_mtime_ns,
        ) or size != after.st_size:
            fh.close()
            return {"ok": False, "error": "snapshot_changed_during_read"}
        live = h.hexdigest()
        if live != exp or size != exp_bytes:
            fh.close()
            return {
                "ok": False,
                "error": "snapshot_changed_before_provider",
                "expected_sha256": exp,
                "live_sha256": live,
                "expected_bytes": exp_bytes,
                "live_bytes": size,
            }
        fh.seek(0)
    except OSError:
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
        return {"ok": False, "error": "snapshot_unverifiable"}

    return {
        "ok": True,
        "fh": fh,
        "content_sha256": exp,
        "content_bytes": exp_bytes,
        "snapshot_path": str(resolved),
        "descriptor_open": True,
    }


def verify_snapshot_descriptor(
    *,
    snapshot_path: str,
    expected_sha256: str,
    expected_bytes: int,
) -> dict[str, Any]:
    """Compatibility wrapper — opens, verifies, then CLOSES.

    Prefer :func:`open_verified_snapshot` on the publish path so the provider
    can stream from the same descriptor. This helper exists for gate-style
    checks that do not upload.
    """
    opened = open_verified_snapshot(
        snapshot_path=snapshot_path,
        expected_sha256=expected_sha256,
        expected_bytes=expected_bytes,
    )
    if not opened.get("ok"):
        return opened
    fh = opened.get("fh")
    if fh is not None:
        try:
            fh.close()
        except OSError:
            pass
    return {
        "ok": True,
        "snapshot_path": opened["snapshot_path"],
        "content_sha256": opened["content_sha256"],
        "content_bytes": opened["content_bytes"],
    }


__all__ = [
    "PROVIDER_ACCEPTS_IDEMPOTENCY_KEY",
    "PUBLISHED",
    "PUBLISH_FAILED",
    "PUBLISH_OUTCOME_UNKNOWN",
    "PUBLISH_REFUSED",
    "PUBLISH_RESERVED",
    "PROVIDER_INFLIGHT",
    "canonical_publish_identity",
    "open_verified_snapshot",
    "publish_idempotency_key",
    "verify_snapshot_descriptor",
]
