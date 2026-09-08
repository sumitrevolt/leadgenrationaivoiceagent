"""Webhook/event IDEMPOTENCY guard — at-least-once delivery ko exactly-once *processing*
banata (consumer ki zimmedari).
================================================================================

KYUN: Razorpay/Stripe/Exotel webhooks RETRY karte (at-least-once) — koi vendor
exactly-once nahi deta. Bina dedup ke ek hi `payment.captured` do baar process ho
sakta → `add_topup_leads`/`add_topup_minutes` DOUBLE credit (customer ko +20 leads),
subscription double-activate, etc. (Invoice already `payment_ref` se dedupe hoti, par
USAGE-credit nahi thi — yeh us gap ko band karta.)

DESIGN (best-practice: Stripe/GitHub/Shopify consumer guide):
  - Atomic check-and-set: Redis `SET key val NX EX ttl` (ek hi command me "naya?" + claim).
  - MAIN redis (noeviction, audit P0-1) → idem keys TTL-window me KABHI evict nahi hote.
  - FAIL-OPEN: Redis down/error pe event PROCESS hota (per-process memory fallback) —
    legit payment-event LOSE karna double-process se zyada bura hai. Never raises.
  - TTL = 14 din default (vendor retry-window se kaafi bada). env IDEMPOTENCY_TTL_S.

Usage (async webhook handler ke top pe):
    from app.billing import idempotency
    if await idempotency.seen_before(f"rzp:{event_id}"):
        return {"received": True, "duplicate": True}
"""

from __future__ import annotations

import os
import time

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PREFIX = "idem:"
_DEFAULT_TTL_S = int(os.environ.get("IDEMPOTENCY_TTL_S", str(14 * 24 * 3600)) or (14 * 24 * 3600))
# Per-process fallback (Redis down) — best-effort, multi-worker me perfect nahi (isliye
# Redis primary). Bounded taaki memory leak na ho.
_MEM: dict[str, float] = {}
_MEM_MAX = 5000


def _mem_seen(key: str, ttl_s: int) -> bool:
    """In-memory check-and-set fallback. True = pehle dekha (duplicate)."""
    now = time.time()
    exp = _MEM.get(key, 0.0)
    if exp > now:
        return True
    _MEM[key] = now + ttl_s
    if len(_MEM) > _MEM_MAX:  # bounded cleanup
        for k in [k for k, e in list(_MEM.items()) if e <= now]:
            _MEM.pop(k, None)
        if len(_MEM) > _MEM_MAX:  # still big → hard trim
            for k in list(_MEM.keys())[: len(_MEM) - _MEM_MAX]:
                _MEM.pop(k, None)
    return False


async def seen_before(key: str, ttl_s: int | None = None) -> bool:
    """True agar yeh event-key PEHLE process ho chuki (DUPLICATE → caller skip kare).
    False = naya event (process karo). Atomic. Redis err = FAIL-OPEN (process). Never raises.

    key: provider event-id se banao (e.g. "rzp:evt_..." / "stripe:evt_..."). Empty key =
    dedupe possible nahi → False (process, fail-open).
    """
    key = (key or "").strip()
    if not key:
        return False
    ttl = int(ttl_s or _DEFAULT_TTL_S)
    rk = _PREFIX + key
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        # SET NX EX: key absent ho to hi set (return True); warna None (already exists).
        ok = await r.set(rk, str(int(time.time())), nx=True, ex=ttl)
        if ok:
            return False  # newly claimed = first time = NOT seen before
        return True  # key pehle se thi = duplicate
    except Exception as e:  # Redis down / InMemoryCache (no nx) / any error → fail-open
        logger.warning("[idempotency] redis check failed (%s) — fail-open via memory", e)
        try:
            return _mem_seen(key, ttl)
        except Exception:
            return False


async def forget(key: str) -> None:
    """Idem key hata do (manual replay/testing ke liye). Best-effort, never raises."""
    key = (key or "").strip()
    if not key:
        return
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        await r.delete(_PREFIX + key)
    except Exception:
        pass
    _MEM.pop(key, None)


def _sync_redis():
    """Blocking redis client (Celery tasks are sync — can't await the async one)."""
    import redis as _redis

    from app.config import settings

    return _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)


def seen_before_sync(key: str, ttl_s: int | None = None) -> bool:
    """SYNC twin of seen_before — for Celery tasks (sync context, can't await).

    True = is event-key PEHLE process ho chuki (DUPLICATE → caller skip kare).
    False = naya (process karo). Atomic SET NX EX. Redis err = FAIL-OPEN (process)
    via per-process memory. Never raises. Empty key = False (dedupe possible nahi).

    KYUN: app/billing/idempotency.seen_before async hai; Celery task body sync.
    Isliye external-side-effect tasks (CRM push, etc.) ko retry pe dedupe karne
    ka koi primitive nahi tha (audit: "Queue idempotency 0% coverage"). Yeh wahi
    gap bharta — sync redis + same memory fallback.
    """
    key = (key or "").strip()
    if not key:
        return False
    ttl = int(ttl_s or _DEFAULT_TTL_S)
    rk = _PREFIX + key
    try:
        r = _sync_redis()
        ok = r.set(rk, str(int(time.time())), nx=True, ex=ttl)
        if ok:
            return False  # newly claimed = first time = NOT seen before
        return True  # key pehle se thi = duplicate
    except Exception as e:  # Redis down / any error → fail-open via memory
        logger.warning("[idempotency] sync redis check failed (%s) — fail-open via memory", e)
        try:
            return _mem_seen(key, ttl)
        except Exception:
            return False


def forget_sync(key: str) -> None:
    """SYNC forget — drop idem key (manual replay/testing). Best-effort, never raises."""
    key = (key or "").strip()
    if not key:
        return
    try:
        _sync_redis().delete(_PREFIX + key)
    except Exception:
        pass
    _MEM.pop(key, None)


def backend_status() -> dict:
    """Read-only idempotency durability projection — no credentials.

    Production intent: Redis primary with per-process memory FAIL-OPEN fallback
    when Redis is down (billing webhooks must not lose events). Nikhil canary
    saw no ``idem:*`` KEYS because either Redis SET failed→memory, TTL not
    inspected on the same logical DB, or keys expired/were forgotten after
    cancelled/blocked paths. Do not claim Redis-only without live key proof.
    """
    db_label = "unset"
    try:
        from app.config import settings

        url = str(getattr(settings, "redis_url", "") or os.getenv("REDIS_URL") or "")
        if "/" in url.rsplit("@", 1)[-1]:
            tail = url.rsplit("/", 1)[-1]
            db_label = f"db{tail}" if tail.isdigit() else "url-present"
        elif url:
            db_label = "url-present"
    except Exception:
        db_label = "unknown"
    redis_ok = False
    try:
        redis_ok = bool(_sync_redis().ping())
    except Exception:
        redis_ok = False
    return {
        "idempotency_backend": "redis" if redis_ok else "memory",
        "fallback_active": not redis_ok,
        "redis_database": db_label,
        "key_prefix": _PREFIX,
        "default_ttl_s": _DEFAULT_TTL_S,
        "memory_entries": len(_MEM),
        "fail_open_on_redis_error": True,
    }


__all__ = ["seen_before", "forget", "seen_before_sync", "forget_sync", "backend_status"]
