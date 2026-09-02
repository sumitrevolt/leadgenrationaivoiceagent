"""social_engine.scheduling — Phase 8 completeness helpers.

  - `next_retry_delay(attempts)`  → exponential-backoff seconds
  - `next_ready_at(job)`          → epoch second the job is eligible again
  - `is_ready_for_retry(job)`     → True iff we're past the backoff wall
  - `_PLATFORM_QPM` / `check_platform_qpm(platform)` → rate limit gate
  - `recover_stale_processing(store, older_than_min=15)` → reset stuck rows

Backoff pattern: 30s → 60s → 120s → 300s → 900s → cap 3600s. Small enough
that transient provider blips clear quickly; big enough to let 429s cool.
All timings are UTC epoch seconds. NEVER raises.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_BACKOFF_LADDER = (30, 60, 120, 300, 900, 1800, 3600)  # seconds by attempt


def next_retry_delay(attempts: int) -> int:
    """Return the seconds to wait before the next retry. `attempts` = number of
    prior FAILED attempts (0 = never tried, 1 = one failure done). Capped at
    the last ladder value."""
    try:
        a = max(0, int(attempts))
    except Exception:
        a = 0
    idx = min(a, len(_BACKOFF_LADDER) - 1)
    return int(_BACKOFF_LADDER[idx])


def next_ready_at(job: dict[str, Any]) -> float:
    """Epoch second when the job's retry-backoff clock expires. If the job has
    never been retried (attempts=0) OR is not currently 'retry' status, returns
    the past (immediately eligible)."""
    try:
        st = str((job or {}).get("status") or "").lower()
        if st != "retry":
            return 0.0
        att = int((job or {}).get("attempts") or 0)
        last = str((job or {}).get("updated_at") or (job or {}).get("created_at") or "")
        # Parse "YYYY-MM-DDTHH:MM:SS" (store format) → epoch. Best-effort.
        # Store writes UTC ISO strings; treat parsed naive datetime as UTC so
        # timestamp() doesn't apply local-timezone offset (IST = +5:30 = 19800s
        # of drift that would make backoff misfire on non-UTC machines).
        import datetime as _dt

        try:
            t = _dt.datetime.fromisoformat(last)
        except Exception:
            return 0.0
        if t.tzinfo is None:
            t = t.replace(tzinfo=_dt.timezone.utc)
        return t.timestamp() + next_retry_delay(att)
    except Exception:
        return 0.0


def is_ready_for_retry(job: dict[str, Any], now: float | None = None) -> bool:
    """True iff the job is either not in retry backoff, or its backoff is done."""
    now = float(now if now is not None else time.time())
    return now >= next_ready_at(job)


# --------------------------------------------------------------------------- #
# Per-platform QPM rate limiter (Phase 8: provider-aware rate limiting).      #
# Meta, LI, and GBP publish limits are ~200/hour = ~3.3/min. Keep conservative.#
# X free write is heavily rate-limited (~50 tweets/24h) — safe cap 5/hour.    #
# In-process only (per-worker); prod-scale distributed limiter would use Redis.#
# --------------------------------------------------------------------------- #
_PLATFORM_QPM: dict[str, int] = {
    "facebook": 20,  # ~1200/hr headroom vs 200/hr policy
    "instagram": 20,
    "gbp": 10,
    "linkedin": 15,
    "x": 5,  # tight — free tier can't sustain more
    "youtube": 5,
    "whatsapp": 30,  # self-host — owner phone 1-to-1
    "postiz": 30,  # gateway internal-fanout
}

_hits: dict[str, deque[float]] = {}


def check_platform_qpm(platform: str, now: float | None = None) -> tuple[bool, int, int]:
    """Sliding 60-second window rate check for a platform.
    Returns (allowed, current_count_in_window, cap).
    Non-blocking: caller decides whether to skip/defer."""
    p = str(platform or "").strip().lower()
    if not p:
        return True, 0, 0
    cap = _PLATFORM_QPM.get(p, 60)
    now = float(now if now is not None else time.time())
    q = _hits.setdefault(p, deque(maxlen=cap * 3 + 4))
    # Trim to 60s window.
    while q and now - q[0] > 60.0:
        q.popleft()
    if len(q) >= cap:
        return False, len(q), cap
    q.append(now)
    return True, len(q), cap


def _clear_qpm_state() -> None:  # test-only helper
    _hits.clear()


# --------------------------------------------------------------------------- #
# Stale-job recovery (Phase 8: stale-job recovery for stuck 'processing' rows).#
# --------------------------------------------------------------------------- #
def recover_stale_processing(store_mod, older_than_min: int = 15) -> dict[str, int]:
    """Any job stuck in 'processing' longer than `older_than_min` is presumed
    dead (worker crashed mid-publish). Reset to 'queued' so the next drain
    picks it up. Idempotent: relies on the store's latest-wins semantics.
    Returns {'recovered': N, 'checked': M}. Never raises."""
    recovered = 0
    checked = 0
    try:
        import datetime as _dt

        cutoff = _dt.datetime.utcnow() - _dt.timedelta(minutes=max(1, int(older_than_min)))
        for r in store_mod.list_jobs(status="processing", limit=500):
            checked += 1
            claimed = str(r.get("claimed_at") or r.get("updated_at") or r.get("created_at") or "")
            try:
                when = _dt.datetime.fromisoformat(claimed)
            except Exception:
                continue
            if when < cutoff:
                store_mod.mark(
                    str(r.get("id") or ""),
                    "queued",
                    last_error=f"stale-recovery: processing > {older_than_min}m",
                )
                recovered += 1
    except Exception as e:
        logger.warning(f"[scheduling] recover_stale_processing failed: {e}")
    return {"recovered": recovered, "checked": checked}
