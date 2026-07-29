"""Stage 2 — immutable approved-artifact snapshot preparation.

FILESYSTEM ONLY. This module never touches the approval ledger, the video
record, a queue, a provider or the UI. Stage 3 wires it into the approval saga;
until then it is a pure primitive.

Why a copy and not a link: a hardlink shares the source inode, so an in-place
overwrite of the original would silently change the "snapshot" too. The snapshot
must be a NEW inode holding the exact previewed bytes.

Sequence:
  resolve source through the canonical media authority
  -> open once (O_NOFOLLOW where supported)
  -> fstat: regular file, bounded size
  -> stream-copy into a tenant-scoped temp file while hashing
  -> fstat again: refuse if the source changed under us
  -> digest must equal the previewed expected hash
  -> flush + fsync the temp file
  -> independently re-hash the temp file
  -> under the cross-process lock: install with os.replace, fsync parent dir
  -> any handled failure removes the temp artifact and installs nothing

Finalized snapshots are never deleted here; cleanup is a separate, separately
tested lifecycle slice.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CHUNK = 1024 * 1024
_MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB ceiling for one render
_DISK_HEADROOM_BYTES = 512 * 1024 * 1024  # keep 512 MiB free after the copy
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_-]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _safe_component(value: Any, *, fallback: str = "unknown") -> str:
    """Path-safe identifier: traversal, separators and NUL cannot survive."""
    text = _SAFE_COMPONENT.sub("-", str(value or "").strip())
    text = text.strip("-")[:64]
    return text or fallback


def snapshot_filename(record_id: str, revision: int, digest: str) -> str:
    return f"{_safe_component(record_id)}.r{int(revision)}.{digest}.mp4"


def _open_source(resolved: Path):
    """Open once, refusing to follow a final symlink component where supported."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(resolved, flags)
    return os.fdopen(fd, "rb")


def _fstat_identity(st: os.stat_result) -> tuple:
    return (st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns)


def _free_bytes(path: Path) -> int:
    try:
        return int(shutil.disk_usage(path).free)
    except OSError:
        return -1


def _digest_file(path: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    size = 0
    with open(path, "rb") as fh:
        while chunk := fh.read(_CHUNK):
            h.update(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _install_lock(dest_dir: Path):
    """Cross-process lock for the install step (same authority the stores use)."""
    try:
        from filelock import FileLock

        return FileLock(str(dest_dir / ".install.lock"), timeout=10)
    except Exception:
        import contextlib

        return contextlib.nullcontext()


def _fsync_dir(path: Path) -> None:
    """Durability for the rename itself. No-op where the platform disallows it."""
    if not hasattr(os, "O_DIRECTORY"):
        return
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def prepare_snapshot(
    *,
    tenant_id: str,
    record_id: str,
    revision: int,
    expected_sha256: str,
    source_path: str,
) -> dict[str, Any]:
    """Materialise an immutable copy of the previewed bytes. Never raises.

    Returns ``{"ok": True, "path", "sha256", "bytes", "reused"}`` or
    ``{"ok": False, "error": <stable reason>}``. Installs nothing on failure.
    """
    from app.marketing.video_media_paths import approved_media_dir, resolve_video_media_file

    expected = str(expected_sha256 or "").strip().lower()
    if not _SHA256_RE.match(expected):
        return {"ok": False, "error": "expected_sha256_invalid"}

    resolved = resolve_video_media_file(source_path)
    if resolved is None:
        return {"ok": False, "error": "source_unverifiable"}

    dest_dir = approved_media_dir() / _safe_component(tenant_id, fallback="tenant")
    final_path = dest_dir / snapshot_filename(record_id, revision, expected)

    # Idempotent reuse: an existing snapshot is trusted only after re-verifying
    # its bytes. A same-name file whose digest disagrees is REFUSED, never
    # overwritten — that filename is a content claim.
    if final_path.exists():
        try:
            have, size = _digest_file(final_path)
        except OSError:
            return {"ok": False, "error": "existing_snapshot_unreadable"}
        if have == expected:
            return {
                "ok": True,
                "path": str(final_path),
                "sha256": have,
                "bytes": size,
                "reused": True,
            }
        return {"ok": False, "error": "existing_snapshot_corrupt"}

    tmp_path: Path | None = None
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with _open_source(resolved) as src:
            st_before = os.fstat(src.fileno())
            if not stat.S_ISREG(st_before.st_mode):
                return {"ok": False, "error": "source_not_regular_file"}
            if st_before.st_size <= 0 or st_before.st_size > _MAX_SNAPSHOT_BYTES:
                return {"ok": False, "error": "source_size_out_of_bounds"}
            free = _free_bytes(dest_dir)
            if free >= 0 and free - st_before.st_size < _DISK_HEADROOM_BYTES:
                return {"ok": False, "error": "insufficient_disk_headroom"}

            fd, tmp_name = tempfile.mkstemp(dir=dest_dir, prefix=".snap-", suffix=".part")
            tmp_path = Path(tmp_name)
            h = hashlib.sha256()
            copied = 0
            with os.fdopen(fd, "wb") as dst:
                while chunk := src.read(_CHUNK):
                    dst.write(chunk)
                    h.update(chunk)
                    copied += len(chunk)
                dst.flush()
                os.fsync(dst.fileno())

            st_after = os.fstat(src.fileno())

        if _fstat_identity(st_before) != _fstat_identity(st_after):
            return {"ok": False, "error": "source_changed_during_copy"}
        if copied != st_before.st_size:
            return {"ok": False, "error": "short_copy"}
        if h.hexdigest() != expected:
            return {"ok": False, "error": "content_hash_mismatch"}

        # Independent re-verification of what actually landed on disk.
        written, written_size = _digest_file(tmp_path)
        if written != expected or written_size != copied:
            return {"ok": False, "error": "snapshot_verify_failed"}

        with _install_lock(dest_dir):
            if final_path.exists():
                have, size = _digest_file(final_path)
                if have != expected:
                    return {"ok": False, "error": "existing_snapshot_corrupt"}
                return {
                    "ok": True,
                    "path": str(final_path),
                    "sha256": have,
                    "bytes": size,
                    "reused": True,
                }
            os.replace(tmp_path, final_path)
            tmp_path = None
            _fsync_dir(dest_dir)

        return {
            "ok": True,
            "path": str(final_path),
            "sha256": expected,
            "bytes": copied,
            "reused": False,
        }
    except OSError as exc:
        logger.warning("[snapshot] refused (%s): %s", _safe_component(record_id), exc)
        return {"ok": False, "error": "snapshot_io_error"}
    finally:
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


__all__ = ["prepare_snapshot", "snapshot_filename"]
