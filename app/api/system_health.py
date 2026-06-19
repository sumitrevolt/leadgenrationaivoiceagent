"""B3 - system-health drill-down for the admin dashboard. Flag-gated.

HOT-PATH RULE: O(1) reads only - psutil resource probes (same lib /health
uses), one guarded redis ping, and the automation_health snapshot (a
heartbeat-file read + one queue-depth read). NO live DB query, no KB/ML/
network-heavy work. Never raises; missing data degrades to -1 / "unknown".
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Infrastructure"])


def _resources() -> dict:
    out = {"cpu_pct": -1.0, "mem_pct": -1.0, "disk_pct": -1.0}
    try:
        import psutil  # already a dep (health.py uses it)

        out["cpu_pct"] = round(psutil.cpu_percent(interval=0.0), 1)
        out["mem_pct"] = round(psutil.virtual_memory().percent, 1)
        try:
            out["disk_pct"] = round(psutil.disk_usage(os.getenv("HEALTH_DISK_PATH", "/")).percent, 1)
        except Exception:
            out["disk_pct"] = round(psutil.disk_usage(os.getcwd()).percent, 1)
    except Exception as e:
        logger.debug("system_health resources failed: %s", e)
    return out


def _worker_and_queue() -> dict:
    """Reuse the cached automation_health snapshot (worker status + queue)."""
    out = {"worker_alive": "unknown", "celery_queue_depth": -1}
    try:
        from app.platform import automation_health

        h = automation_health.health()
        if isinstance(h, dict):
            out["worker_alive"] = str(h.get("status") or "unknown")
            q = h.get("queue") or {}
            if isinstance(q, dict):
                out["celery_queue_depth"] = int(q.get("celery", -1))
    except Exception as e:
        logger.debug("system_health worker/queue failed: %s", e)
    return out


def _redis_ping_ms() -> int:
    try:
        import time

        import redis as _redis

        url = os.getenv("REDIS_URL") or "redis://localhost:6379/0"
        r = _redis.from_url(url, socket_connect_timeout=1, socket_timeout=1)
        t0 = time.monotonic()
        r.ping()
        return int((time.monotonic() - t0) * 1000)
    except Exception as e:
        logger.debug("system_health redis ping failed: %s", e)
        return -1


@router.get("/system-health-detail")
async def system_health_detail(_user=Depends(require_admin)) -> dict:
    """B3: live infra detail for the admin System Health panel.

    Cheap by design: this does NOT call /health/ready (that probe runs a live
    DB query + extra redis connect, which would turn this admin poll into a
    hot-path DB load — the project's #1 prod-down pattern). health_ready is
    derived from the O(1) signals already gathered.
    """
    if os.getenv("SYS_HEALTH_DETAIL", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False}
    out: dict = {"enabled": True, "redis_ping_ms": _redis_ping_ms()}
    out.update(_resources())
    out.update(_worker_and_queue())
    out["health_ready"] = "ok" if (out["redis_ping_ms"] >= 0 and out["cpu_pct"] >= 0) else "degraded"
    return out
