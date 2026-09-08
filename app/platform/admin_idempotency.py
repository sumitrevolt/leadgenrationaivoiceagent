"""Tier-1 governance — Idempotency-Key protection for mutating admin commands.

Cross-worker (Redis) dedup so the same *actor + endpoint scope + normalized payload +
Idempotency-Key* executes at most once. A duplicate replays the stored result; a
concurrent duplicate is rejected while the first is in-flight; reusing a key with a
different payload fails safely; keys expire on a bounded TTL.

REDIS-FAILURE POLICY (explicit, per Tier-1 spec):
  Default is **FAIL-OPEN-BUT-LOUD** — if Redis is unreachable we log a warning and let
  the action proceed WITHOUT dedup, because refusing a legitimate destructive admin
  action on a transient cache outage harms operability more than a rare duplicate, and
  the Slice-A audit trail records every attempt so duplicates remain detectable. Set
  ``ADMIN_IDEMPOTENCY_FAIL_CLOSED=1`` to flip to fail-closed (HTTP 503) for stricter
  environments. Both behaviours are regression-tested.

Server-side only. The Idempotency-Key itself is never persisted as a secret; only the
payload *hash* is stored, never the raw payload.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# Lock TTL bounds a crashed in-flight request so a later retry isn't blocked forever.
_LOCK_TTL = int(os.getenv("ADMIN_IDEM_LOCK_TTL", "120"))
# Done TTL bounds how long a completed result is replayable.
_DONE_TTL = int(os.getenv("ADMIN_IDEM_DONE_TTL", "86400"))


class Replay:
    """Sentinel: a stored result exists → caller should return it without re-executing."""

    __slots__ = ("response",)

    def __init__(self, response: Any):
        self.response = response


class _Owner:
    """Sentinel: caller won the execution slot → run the action then call store()."""

    __slots__ = ("rkey", "phash")

    def __init__(self, rkey: str, phash: str):
        self.rkey = rkey
        self.phash = phash


def _redis():
    import redis as _r

    from app.config import settings

    return _r.Redis.from_url(
        str(settings.redis_url),
        socket_timeout=3,
        socket_connect_timeout=3,
        decode_responses=True,
    )


def _canonical(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    except Exception:
        return str(payload)


def _phash(payload: Any) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


def key_of(request: Any) -> str | None:
    """Extract the client-supplied Idempotency-Key header (bounded length)."""
    try:
        k = request.headers.get("idempotency-key") or request.headers.get("x-idempotency-key")
        k = (k or "").strip()[:128]
        return k or None
    except Exception:
        return None


def begin(*, request: Any, actor_id: Any, scope: str, payload: Any):
    """Start an idempotent operation.

    Returns:
      - ``None``   → no Idempotency-Key sent (or Redis down + fail-open): execute normally.
      - ``_Owner`` → caller owns execution; run the action then ``store(token, response)``.
      - ``Replay`` → a stored result exists; caller must return ``.response`` unchanged.
    Raises ``HTTPException`` 409 (payload mismatch / concurrent in-progress) or 503
    (Redis down + fail-closed).
    """
    key = key_of(request)
    if not key:
        return None
    ph = _phash(payload)
    rkey = f"idem:admin:{actor_id or 'anon'}:{scope}:{key}"
    try:
        r = _redis()
        lock = json.dumps({"state": "in_progress", "phash": ph, "ts": time.time()})
        if r.set(rkey, lock, nx=True, ex=_LOCK_TTL):
            return _Owner(rkey, ph)
        raw = r.get(rkey)
    except HTTPException:
        raise
    except Exception as e:
        fail_closed = os.getenv("ADMIN_IDEMPOTENCY_FAIL_CLOSED", "0") == "1"
        logger.warning(
            "idem: redis unavailable scope=%s fail_closed=%s err=%s", scope, fail_closed, e
        )
        if fail_closed:
            raise HTTPException(
                status_code=503, detail="idempotency store unavailable (fail-closed)"
            )
        return None  # fail-open: proceed without dedup

    try:
        existing = json.loads(raw) if raw else {}
    except Exception:
        existing = {}

    if existing.get("phash") and existing.get("phash") != ph:
        raise HTTPException(
            status_code=409, detail="Idempotency-Key reused with a different payload"
        )
    if existing.get("state") == "done":
        return Replay(existing.get("response"))
    # still in_progress → concurrent duplicate; do not execute a second time
    raise HTTPException(status_code=409, detail="duplicate request already in progress")


def store(token: Any, response: Any) -> None:
    """Persist the completed result against the owner's key (no-op if token is not an owner)."""
    if not isinstance(token, _Owner):
        return
    try:
        r = _redis()
        r.set(
            token.rkey,
            json.dumps(
                {"state": "done", "phash": token.phash, "response": response, "ts": time.time()}
            ),
            ex=_DONE_TTL,
        )
    except Exception as e:
        # Best-effort: a lost store just means the in_progress lock expires and a later
        # retry re-executes (acceptable — never blocks, never double-counts within lock TTL).
        logger.warning("idem: store failed key=%s err=%s", getattr(token, "rkey", "?"), e)
