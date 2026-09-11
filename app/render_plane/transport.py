"""Resumable, hash-verified chunked transfer for the render plane (T02).

Artifacts and inputs can be hundreds of megabytes over a link that drops, so a
transfer must be **resumable by byte offset** and **verified by SHA-256** rather
than trusted. This module is the transport math — pure, stdlib-only and
never-raising — so both the worker (upload) and the VPS (download/verify) share
exactly one definition of "what is the next byte" and "is this file intact".

Every public entry returns a dict; none raises.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

#: Default chunk size (1 MiB). Overridable per call or via env.
DEFAULT_CHUNK_BYTES = 1024 * 1024
CHUNK_ENV = "RENDER_PLANE_CHUNK_BYTES"


def chunk_size(chunk: int | None = None) -> int:
    """Resolve the chunk size at call time (never frozen at import)."""
    if chunk is not None:
        try:
            return max(4096, min(64 * 1024 * 1024, int(chunk)))
        except (TypeError, ValueError):
            pass
    try:
        return max(4096, min(64 * 1024 * 1024, int(os.getenv(CHUNK_ENV, str(DEFAULT_CHUNK_BYTES)))))
    except Exception:
        return DEFAULT_CHUNK_BYTES


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def sha256_file(path: str | os.PathLike[str], *, chunk: int | None = None) -> str:
    """Streaming SHA-256 of a file. Returns "" when unreadable (never raises)."""
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for block in iter(lambda: fh.read(chunk_size(chunk)), b""):
                digest.update(block)
        return digest.hexdigest()
    except Exception:
        return ""


def chunk_count(size: int, *, chunk: int | None = None) -> int:
    step = chunk_size(chunk)
    try:
        total = max(0, int(size))
    except (TypeError, ValueError):
        return 0
    return 0 if total == 0 else (total + step - 1) // step


def plan_upload(
    size: int,
    *,
    acknowledged: list[int] | None = None,
    chunk: int | None = None,
) -> dict[str, Any]:
    """Given a total size and the acknowledged chunk indexes, what is next?

    Returns the first unacknowledged byte offset so an interrupted upload resumes
    instead of restarting. ``acknowledged`` may be unsorted/duplicated/garbage —
    it is normalised, never trusted.
    """
    try:
        step = chunk_size(chunk)
        total = max(0, int(size))
        total_chunks = chunk_count(total, chunk=step)
        acked: set[int] = set()
        for idx in acknowledged or []:
            try:
                value = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= value < total_chunks:
                acked.add(value)
        missing = [i for i in range(total_chunks) if i not in acked]
        next_offset = (missing[0] * step) if missing else total
        return {
            "ok": True,
            "size": total,
            "chunk_size": step,
            "total_chunks": total_chunks,
            "acknowledged": sorted(acked),
            "missing": missing,
            "next_offset": next_offset,
            "complete": not missing,
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"ok": False, "error": f"plan_failed:{type(exc).__name__}"}


def read_chunk(
    path: str | os.PathLike[str],
    offset: int,
    *,
    length: int | None = None,
    chunk: int | None = None,
) -> dict[str, Any]:
    """Read one chunk at ``offset``; returns the bytes + their SHA-256."""
    try:
        step = chunk_size(chunk)
        start = max(0, int(offset))
        want = step if length is None else max(0, int(length))
        with open(path, "rb") as fh:
            fh.seek(start)
            data = fh.read(want)
        return {
            "ok": True,
            "offset": start,
            "length": len(data),
            "sha256": sha256_bytes(data),
            "data": data,
            "eof": len(data) < want,
        }
    except Exception as exc:
        return {"ok": False, "error": f"read_failed:{type(exc).__name__}"}


def apply_chunk(
    buffer: bytearray,
    offset: int,
    data: bytes,
    *,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Write one received chunk into ``buffer`` at ``offset`` after hash check.

    A chunk whose SHA-256 does not match is REJECTED (``ok=False``) rather than
    written, so a corrupted byte can never be silently assembled into an artifact.
    """
    try:
        start = max(0, int(offset))
        payload = bytes(data or b"")
        if expected_sha256:
            got = sha256_bytes(payload)
            if got != str(expected_sha256):
                return {
                    "ok": False,
                    "error": "chunk_hash_mismatch",
                    "offset": start,
                    "got": got,
                }
        end = start + len(payload)
        if end > len(buffer):
            buffer.extend(b"\x00" * (end - len(buffer)))
        buffer[start:end] = payload
        return {"ok": True, "offset": start, "written": len(payload), "next_offset": end}
    except Exception as exc:
        return {"ok": False, "error": f"apply_failed:{type(exc).__name__}"}


def verify_artifact(
    path: str | os.PathLike[str],
    expected_sha256: str,
    *,
    max_bytes: int | None = None,
    chunk: int | None = None,
) -> dict[str, Any]:
    """Server-side acceptance check for an uploaded artifact. Never raises."""
    try:
        if not os.path.isfile(path):
            return {"ok": False, "error": "artifact_missing"}
        size = os.path.getsize(path)
        if max_bytes is not None and size > int(max_bytes):
            return {"ok": False, "error": "artifact_too_large", "bytes": size}
        digest = sha256_file(path, chunk=chunk)
        if not digest:
            return {"ok": False, "error": "artifact_unreadable"}
        if str(expected_sha256 or "") and digest != str(expected_sha256):
            return {
                "ok": False,
                "error": "artifact_hash_mismatch",
                "expected": str(expected_sha256),
                "got": digest,
            }
        return {"ok": True, "bytes": size, "sha256": digest}
    except Exception as exc:
        return {"ok": False, "error": f"verify_failed:{type(exc).__name__}"}


def describe_transfer(path: str | os.PathLike[str], *, chunk: int | None = None) -> dict[str, Any]:
    """A small, non-secret descriptor for logging/telemetry. Never raises."""
    try:
        size = os.path.getsize(path)
        step = chunk_size(chunk)
        return {
            "ok": True,
            "size": size,
            "chunk_size": step,
            "total_chunks": chunk_count(size, chunk=step),
            "sha256": sha256_file(path, chunk=step),
        }
    except Exception as exc:
        return {"ok": False, "error": f"describe_failed:{type(exc).__name__}"}


__all__ = [
    "CHUNK_ENV",
    "DEFAULT_CHUNK_BYTES",
    "apply_chunk",
    "chunk_count",
    "chunk_size",
    "describe_transfer",
    "plan_upload",
    "read_chunk",
    "sha256_bytes",
    "sha256_file",
    "verify_artifact",
]
