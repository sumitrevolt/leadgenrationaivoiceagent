"""Durable per-tenant creative-learning ledger (append-only JSONL).

WHY THIS EXISTS
---------------
`learning.py` used an in-process module dict (`_MEM_STORE`) as its backing store.
That store is process-local, so learning never survived a worker restart and
`record_learning()` had zero callers in `app/` — the "learning" was dead. This
module is the durable replacement: one append-only JSONL file per tenant, the
same proven pattern `delivery_ledger.py` already uses per customer.

CONVENTIONS (mirrors delivery_ledger.py / store.py)
  - Per-tenant file at ``<root>/<tenant_id>.jsonl`` — the filename IS the tenant
    boundary, so a cross-tenant read cannot resolve to another tenant's rows.
  - ``<root>`` is resolved through ``runtime_data_authority`` at CALL time, never
    captured in an import-time constant (a path frozen at import cannot be
    redirected by a later fixture, and that bug is why the authority exists).
  - ``filelock`` guards appends (already a repo dependency); a lock timeout falls
    back to an unlocked append rather than losing the row.
  - Every public entry returns a dict (or list) and NEVER raises.
  - Reads skip corrupt lines; a partially written tail must never blank the
    history or explode a caller.
"""

from __future__ import annotations

import json
import os
from collections import deque
from pathlib import Path
from typing import Any

from app.platform.runtime_data import RuntimeDataError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

#: Hard cap on how many ledger rows a single read will return. The ledger is
#: append-only and may grow unbounded; callers that want the whole history can
#: page, but a single call must not load an unbounded file into memory.
DEFAULT_LIMIT = 500


def _learning_dir() -> str:
    """Per-tenant learning-ledger directory — resolved per call, never frozen.

    Honours the repo's creative_os root-override convention: a dedicated
    ``CREATIVE_LEARNING_ROOT`` wins, otherwise the subsystem root
    ``CREATIVE_LEDGER_ROOT`` (which the existing creative_os test fixture pins)
    is used, so the ledger stays isolated with the rest of the subsystem.
    """
    from app.platform import runtime_data_authority as _auth

    override = "CREATIVE_LEARNING_ROOT"
    if not os.getenv(override) and os.getenv("CREATIVE_LEDGER_ROOT"):
        override = "CREATIVE_LEDGER_ROOT"
    return str(
        _auth.resolve_store_path(
            store_id="marketing.creative_learning",
            legacy_path=Path("data") / "creative_os" / "learning",
            target_segments=("marketing", "creative_learning"),
            override_env=override,
        )
    )


def _safe_stem(tenant_id: str) -> str:
    """Refuse a tenant id that would place the file outside its own store."""
    from app.platform.runtime_data import _safe_segment

    return _safe_segment(tenant_id)


def learning_path(tenant_id: str) -> str:
    """Absolute path of a tenant's learning ledger (call-time resolved).

    Raises ``RuntimeDataError`` for an unsafe or absent tenant id — this is a
    deliberate path-traversal guard, not an error path. Public callers
    (``append_learning`` / ``read_learning`` / ``count_learning``) catch it and
    remain "never raises".
    """
    try:
        stem = _safe_stem(tenant_id)
    except RuntimeDataError:
        raise
    except Exception as exc:
        raise RuntimeDataError(f"unsafe learning tenant id: {tenant_id!r}") from exc
    return os.path.join(_learning_dir(), f"{stem}.jsonl")


def _lock(path: str):
    try:
        from filelock import FileLock

        return FileLock(path + ".lock", timeout=5)
    except Exception:  # pragma: no cover - filelock is a hard dep in practice
        import contextlib

        return contextlib.nullcontext()


def append_learning(tenant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append one learning row to the tenant's append-only ledger.

    Never raises. Returns ``{"ok": bool, ...}``; a failure is reported, never
    swallowed into a silent success.
    """
    try:
        tid = str(tenant_id or "").strip()
        if not tid:
            return {"ok": False, "error": "tenant_id_required"}
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload_not_dict"}
        _learning_dir()
        os.makedirs(_learning_dir(), exist_ok=True)
        fp = learning_path(tid)
        line = json.dumps(payload, ensure_ascii=False, default=str)
        try:
            with _lock(fp):
                with open(fp, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception:
            # Lock timeout etc. — an unlocked append is still better than loss.
            with open(fp, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return {"ok": True, "tenant_id": tid, "path": fp}
    except Exception as exc:
        logger.warning("[learning_store] append_learning failed: %s", exc)
        return {"ok": False, "error": str(exc)[:160]}


def read_learning(tenant_id: str, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Return the last ``limit`` learning rows for this tenant (oldest→newest).

    Never raises. Missing file → ``[]``. Corrupt lines are skipped. The read is
    bounded (a ``deque`` of ``limit``) so an unbounded ledger cannot exhaust
    memory.
    """
    tid = str(tenant_id or "").strip()
    if not tid:
        return []
    try:
        cap = max(1, min(int(limit or DEFAULT_LIMIT), DEFAULT_LIMIT))
    except Exception:
        cap = DEFAULT_LIMIT
    try:
        fp = learning_path(tid)
    except Exception:
        return []
    if not os.path.isfile(fp):
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=cap)
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if isinstance(rec, dict):
                    rows.append(rec)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[learning_store] read_learning failed (%s): %s", tid, exc)
    return list(rows)


def count_learning(tenant_id: str) -> int:
    """Total rows on disk for this tenant (best-effort, never raises)."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return 0
    try:
        fp = learning_path(tid)
    except Exception:
        return 0
    if not os.path.isfile(fp):
        return 0
    n = 0
    try:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    n += 1
    except Exception:
        return n
    return n


__all__ = [
    "DEFAULT_LIMIT",
    "append_learning",
    "count_learning",
    "learning_path",
    "read_learning",
]
