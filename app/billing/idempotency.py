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


__all__ = ["seen_before", "forget"]
