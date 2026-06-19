"""B3 - system-health drill-down for the admin dashboard. Flag-gated.

HOT-PATH RULE: O(1) reads only - psutil resource probes (same lib /health
uses), one guarded redis ping, and the cached automation_health snapshot
(worker status + queue depth). No KB/ML/network-heavy/DB-heavy work.
Never raises; missing data degrades to -1 / "unknown".
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


async def _health_ready() -> str:
    try:
        from starlette.responses import Response

        from app.api.health import readiness_check

        rr = await readiness_check(Response())
        if isinstance(rr, dict):
            return str(rr.get("status") or "unknown")
    except Exception as e:
        logger.debug("system_health readiness failed: %s", e)
    return "unknown"


@router.get("/system-health-detail")
async def system_health_detail(_user=Depends(require_admin)) -> dict:
    """B3: live infra detail for the admin System Health panel."""
    if os.getenv("SYS_HEALTH_DETAIL", "0").strip().lower() not in ("1", "true", "yes"):
        return {"enabled": False}
    out: dict = {"enabled": True, "redis_ping_ms": _redis_ping_ms(), "health_ready": await _health_ready()}
    out.update(_resources())
    out.update(_worker_and_queue())
    return out
