"""ADR-104 Phase A4.5 — owned, deduplicated single-niche KB catalog refresh.

WHY THIS IS A SEPARATE TASK (not app/platform/kb_refresh.py): that job re-ingests
CUSTOMER WEBSITE content (`onboarding._seed_kb_from_website`, zero references to
`NICHES`/niche in its source) — a different domain entirely. Mixing niche-catalog
seeding into it would couple two unrelated jobs into one blast radius. See
memory/decisions.md ADR-104 addendum #5 CORRECTION 1 (this exact mistake was made
and retracted before this module was written).

WHY THIS EXISTS AT ALL: the live voice reply path (telecaller_brain._kb_facts)
must never seed a cold niche inline — that was the original incident (39-niche
catalog-wide embed/upsert blocking the spoken-turn hot path, then an abandoned
background thread blocking Celery's executor shutdown until the 600s hard
kill). A cold niche now gets ONE owned, deduplicated refresh request here
instead; the reply returns immediately, degraded-but-honest, on this turn.

Dedup lease (Redis SET NX EX, owner-token compare-and-delete — mirrors
app/agents/self_improve.py's acquire_tick_slot/release_tick_slot):
    kb:niche_refresh:lease:<niche>  -> owner token; TTL bounds a dead-worker leak
    kb:niche_refresh:state:<niche>  -> "queued"|"running"|"ready"|"failed"
                                        (observability only — Qdrant's exact
                                        count via kb_readiness.py remains the
                                        SOLE readiness authority; this state
                                        string is never trusted as "ready").
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from app.utils.logger import setup_logger
from app.worker import celery_app

logger = setup_logger(__name__)

_LEASE_PREFIX = "kb:niche_refresh:lease"
_STATE_PREFIX = "kb:niche_refresh:state"
# Lease TTL must comfortably exceed the task's own time_limit below, else a
# still-running-but-slow attempt could have its lease expire and let a SECOND
# worker start re-embedding the same niche concurrently.
_LEASE_TTL_S = int(os.getenv("KB_NICHE_REFRESH_LEASE_TTL_S", "180") or 180)
_STATE_TTL_S = int(os.getenv("KB_NICHE_REFRESH_STATE_TTL_S", "3600") or 3600)


def _redis_client():
    try:
        import redis as _redis

        from app.config import settings

        return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=2)
    except Exception:
        return None


def _redis_value(val: Any) -> str:
    if isinstance(val, bytes):
        try:
            return val.decode("utf-8")
        except Exception:
            return ""
    return str(val or "")


def _set_state(niche: str, state: str) -> None:
    r = _redis_client()
    if r is None:
        return
    try:
        r.set(f"{_STATE_PREFIX}:{niche}", state, ex=_STATE_TTL_S)
    except Exception:
        pass


def _release_lease(niche: str, token: str) -> None:
    if not token:
        return
    r = _redis_client()
    if r is None:
        return
    try:
        if _redis_value(r.get(f"{_LEASE_PREFIX}:{niche}")) == token:
            r.delete(f"{_LEASE_PREFIX}:{niche}")
    except Exception:
        pass


def request_niche_refresh(niche: str) -> bool:
    """Atomically dispatch ONE owned refresh task for `niche` if none is
    already queued/running. Fail-CLOSED on Redis error (no dedupe guarantee
    available => skip rather than risk a duplicate-embed storm). Never raises.

    Callers (telecaller_brain._kb_facts) are expected to have already gated
    this on `is_supported_niche`/cold-readiness — this function re-checks
    `is_supported_niche` defensively so it is safe to call directly, but a
    ready niche is the CALLER's responsibility to never reach this path
    (this function does not re-query Qdrant readiness itself — that would
    add a second blocking round-trip to a fire-and-forget dispatch).

    Returns True iff THIS call actually queued a new task.
    """
    from app.voice_agent.kb_readiness import is_supported_niche

    niche = (niche or "").strip()
    if not is_supported_niche(niche):
        # Unsupported niches must never create a Redis key or a Celery task.
        return False

    r = _redis_client()
    if r is None:
        logger.debug("[kb-niche-refresh] request skipped niche=%s reason=no_redis", niche)
        return False

    token = uuid.uuid4().hex
    lease_key = f"{_LEASE_PREFIX}:{niche}"
    try:
        acquired = r.set(lease_key, token, nx=True, ex=_LEASE_TTL_S)
    except Exception as e:
        logger.debug(
            "[kb-niche-refresh] lease acquire error niche=%s error_class=%s",
            niche,
            type(e).__name__,
        )
        return False
    if not acquired:
        return False  # already queued/running elsewhere — dedupe, no new task

    _set_state(niche, "queued")
    try:
        refresh_niche_task.apply_async(args=(niche,), kwargs={"_lease_token": token})
    except Exception as e:
        # Broker publish failed -> nothing will ever run to release this lease,
        # so release it here immediately instead of leaving it stuck for the
        # full TTL with no task actually in flight.
        logger.warning(
            "[kb-niche-refresh] dispatch failed niche=%s error_class=%s", niche, type(e).__name__
        )
        _release_lease(niche, token)
        _set_state(niche, "failed")
        return False

    logger.info("[kb-niche-refresh] requested niche=%s", niche)
    return True


@celery_app.task(
    bind=True,
    name="app.tasks.kb_niche_refresh.refresh_niche_task",
    autoretry_for=(Exception,),
    retry_backoff=30,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    # ADR-104 A10 (2026-07-15) — measured, not guessed. worker_heavy's first-use-
    # per-process Qdrant/fastembed init is a reproducible ~97-99s cost (proven
    # via a bare, non-Celery script -- independent of Celery's own soft-limit,
    # which was previously just an incidental near-match, not the true bound).
    # worker_process_init now warms this once per process (see app/worker.py's
    # on_worker_process_init), so in the common case a task arrives long after
    # boot and only pays the ~26s of real work. Worst case is a task racing a
    # fresh pool-respawn's still-in-flight warm-up: it blocks on the SAME
    # _QDRANT_LOCK the warm-up holds (correct -- prevents duplicate slow work),
    # then does its own ~26s -> ~97+26=123s observed worst case. 90/120 left
    # ZERO margin for that case (it would hard-kill mid-finalization, right
    # when it's trying to release the lease). 180/240 gives ~45% margin above
    # the measured 123s worst case while still bounding genuine runaway work.
    soft_time_limit=180,
    time_limit=240,
)
def refresh_niche_task(self, niche: str, _lease_token: str = "") -> dict[str, Any]:
    """Seed exactly ONE niche's catalog content, verify via the SAME
    authoritative Qdrant count the voice path trusts, and release its lease
    on every terminal outcome (ready or retries-exhausted) — never on a
    still-pending retry, since that is the same logical attempt continuing,
    not a new dispatch. Never touches any other niche."""
    from app.voice_agent.kb_loader import seed_niche
    from app.voice_agent.kb_readiness import (
        STATE_READY,
        count_niche_catalog_points,
        is_supported_niche,
        reset_client_cache,
    )
    from app.voice_agent.knowledge_base import get_knowledge_base

    t0 = time.monotonic()
    niche = (niche or "").strip()

    if not is_supported_niche(niche):
        # request_niche_refresh() gates this before dispatch — this is a
        # defensive fallback for direct/manual invocation with a bad niche.
        _set_state(niche, "failed")
        _release_lease(niche, _lease_token)
        return {"niche": niche, "ok": False, "error_class": "UnsupportedNiche"}

    _set_state(niche, "running")
    try:
        kb = get_knowledge_base()
        result = seed_niche(kb, niche)  # never raises; {"ok","chunks","error_class",...}
        if not result.get("ok"):
            raise RuntimeError(result.get("error_class") or "seed_failed")

        # Verify against the SAME authoritative source the voice path trusts —
        # a "successful" embed call that didn't actually persist must never
        # report ready. reset_client_cache() forces a fresh count in case this
        # worker process is long-lived and cached a stale bare client.
        reset_client_cache()
        readiness = count_niche_catalog_points(niche)
        if readiness.state != STATE_READY:
            raise RuntimeError(f"post_seed_not_ready:{readiness.state}")
    except Exception as e:
        error_class = type(e).__name__
        is_final_attempt = self.request.retries >= self.max_retries
        logger.warning(
            "[kb-niche-refresh] niche=%s attempt=%s/%s failed error_class=%s",
            niche,
            self.request.retries + 1,
            self.max_retries + 1,
            error_class,
        )
        if is_final_attempt:
            _set_state(niche, "failed")
            _release_lease(niche, _lease_token)
        raise  # autoretry_for=(Exception,) reschedules unless retries are exhausted
    else:
        _set_state(niche, "ready")
        _release_lease(niche, _lease_token)
        return {
            "niche": niche,
            "ok": True,
            "chunks": result.get("chunks"),
            "verified_count": readiness.count,
            "duration_s": round(time.monotonic() - t0, 3),
        }


__all__ = ["request_niche_refresh", "refresh_niche_task"]
