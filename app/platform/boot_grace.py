"""Celery worker boot-grace — heavy daily jobs skip on restart inside their window.

Mirrors team_scheduler.scheduler_loop boot-grace for the durable Celery path.
"""

from __future__ import annotations

import time
from datetime import datetime
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")
_WORKER_START = time.time()

# job -> ((hour, minute) start inclusive, end exclusive) — IST
_HEAVY_WINDOWS: dict[str, tuple[tuple[int, int], tuple[int, int]]] = {
    "qa": ((2, 30), (4, 0)),
    "trainer": ((3, 0), (4, 30)),
    "blog": ((6, 30), (8, 30)),
    "content": ((7, 0), (9, 0)),
    "digest": ((8, 30), (10, 30)),
    "prospect": ((9, 30), (11, 30)),
    "pipeline": ((11, 0), (12, 0)),
    "kb_refresh": ((5, 0), (6, 30)),
    "midday_prospect": ((14, 30), (15, 30)),
    "afternoon_content": ((15, 0), (16, 0)),
    "evening_prospect": ((17, 0), (18, 0)),
    "evening_wrap": ((18, 30), (19, 30)),
    "weekly_marketing": ((12, 30), (13, 30)),
    "saturday_hygiene": ((4, 0), (5, 30)),
}


def defer_seconds(job: str) -> int:
    """Seconds until heavy-window ends (+ buffer) — boot-grace skip ke baad retry."""
    win = _HEAVY_WINDOWS.get(job)
    if not win:
        return 600
    _, hi = win
    hm = datetime.now(_IST)
    cur_s = hm.hour * 3600 + hm.minute * 60 + getattr(hm, "second", 0)
    end_s = hi[0] * 3600 + hi[1] * 60
    if cur_s >= end_s:
        return 300
    return max(120, end_s - cur_s + 45)


def should_skip_boot_grace(job: str) -> bool:
    """True = skip this staff job run (worker booted inside heavy window)."""
    win = _HEAVY_WINDOWS.get(job)
    if not win:
        return False
    # Grace applies only shortly after worker process start (restart storm window).
    if time.time() - _WORKER_START > 3600:
        return False
    lo, hi = win
    hm = datetime.now(_IST)
    cur = (hm.hour, hm.minute)
    return lo <= cur < hi


__all__ = ["should_skip_boot_grace", "defer_seconds"]
