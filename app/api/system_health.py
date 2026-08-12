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
            out["disk_pct"] = round(
                psutil.disk_usage(os.getenv("HEALTH_DISK_PATH", "/")).percent, 1
            )
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


# --- Admin-friendly grading: raw numbers -> emoji-able status + Hinglish hint ---
# (A non-technical admin should not have to know that "queue 1200" is bad.)
def _band(value: float, warn: float, bad: float, display: str, hints: dict) -> dict:
    """value vs warn/bad thresholds (higher = worse). Negative value = data nahi mila."""
    if value is None or value < 0:
        return {"value": "—", "status": "unknown", "hint": "Data nahi mila"}
    if value >= bad:
        return {"value": display, "status": "bad", "hint": hints["bad"]}
    if value >= warn:
        return {"value": display, "status": "warn", "hint": hints["warn"]}
    return {"value": display, "status": "ok", "hint": hints.get("ok", "Theek hai")}


def _grade(res: dict, wq: dict, redis_ms: int) -> dict:
    """Pure: build plain-Hinglish rows + overall status + summary. Never raises."""
    cpu, mem, disk = res.get("cpu_pct", -1), res.get("mem_pct", -1), res.get("disk_pct", -1)
    qd = wq.get("celery_queue_depth", -1)
    worker = str(wq.get("worker_alive") or "unknown")

    rows: list[dict] = []
    rows.append(
        {
            "key": "cpu",
            "label": "CPU load",
            **_band(
                cpu,
                75,
                90,
                f"{cpu}%",
                {
                    "bad": "CPU bahut busy — server slow ho sakta",
                    "warn": "CPU thoda high",
                    "ok": "Theek hai",
                },
            ),
        }
    )
    rows.append(
        {
            "key": "mem",
            "label": "Memory",
            **_band(
                mem,
                82,
                92,
                f"{mem}%",
                {
                    "bad": "Memory lagbhag full — crash/OOM risk",
                    "warn": "Memory thodi high",
                    "ok": "Theek hai",
                },
            ),
        }
    )
    rows.append(
        {
            "key": "disk",
            "label": "Disk",
            **_band(
                disk,
                80,
                90,
                f"{disk}%",
                {
                    "bad": "Disk bhar raha — space khaali karo (logs/backups)",
                    "warn": "Disk thodi bhar rahi",
                    "ok": "Theek hai",
                },
            ),
        }
    )

    # Redis: -1 = connection nahi (bad), warna ping ms (higher = worse).
    if redis_ms is None or redis_ms < 0:
        rows.append(
            {
                "key": "redis",
                "label": "Redis",
                "value": "down",
                "status": "bad",
                "hint": "Redis se connection nahi — queue/cache atak sakte",
            }
        )
    else:
        rows.append(
            {
                "key": "redis",
                "label": "Redis",
                **_band(
                    redis_ms,
                    60,
                    250,
                    f"{redis_ms}ms",
                    {
                        "bad": "Redis slow respond kar raha",
                        "warn": "Redis thoda slow",
                        "ok": "Theek hai",
                    },
                ),
            }
        )

    # Celery queue depth: CLAUDE.md rule — >500 backlog = del celery.
    rows.append(
        {
            "key": "queue",
            "label": "Task queue",
            **_band(
                qd,
                200,
                500,
                str(qd),
                {
                    "bad": "Queue me bahut kaam atka — worker restart ya DLQ clear",
                    "warn": "Queue thoda bhara hai",
                    "ok": "Theek hai",
                },
            ),
        }
    )

    # Worker liveness (string status from automation_health, not numeric).
    _wmap = {
        "ok": ("ok", "Chal raha hai"),
        "overdue": ("warn", "Time par nahi chala — worker container check"),
        "last_failed": ("bad", "Pichhla run fail — Events tab me error dekho"),
        "never_ran": ("warn", "Abhi tak nahi chala (naya deploy ke baad normal)"),
    }
    wst, whint = _wmap.get(worker, ("unknown", "Status pata nahi"))
    rows.append({"key": "worker", "label": "Worker", "value": worker, "status": wst, "hint": whint})

    order = {"bad": 3, "warn": 2, "ok": 1, "unknown": 0}
    overall = max((r["status"] for r in rows), key=lambda s: order.get(s, 0)) if rows else "unknown"
    if overall == "bad":
        summary = "❌ Server me dikkat hai — neeche laal cheez fix karo"
    elif overall == "warn":
        summary = "⚠️ Chal raha hai par kuch cheezein dhyan maangti hain"
    elif overall == "ok":
        summary = "✅ Server bilkul theek chal raha hai"
    else:
        summary = "❓ Server ka data abhi nahi mila"
    return {"rows": rows, "status": overall, "summary": summary}


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
    redis_ms = _redis_ping_ms()
    res = _resources()
    wq = _worker_and_queue()
    out: dict = {"enabled": True, "redis_ping_ms": redis_ms}
    out.update(res)
    out.update(wq)
    out["health_ready"] = "ok" if (redis_ms >= 0 and out["cpu_pct"] >= 0) else "degraded"
    # Admin-friendly layer: emoji-able rows + plain-Hinglish summary (never raises).
    try:
        out.update(_grade(res, wq, redis_ms))
    except Exception as e:
        logger.debug("system_health grade failed: %s", e)
        out.setdefault("rows", [])
        out.setdefault("status", "unknown")
        out.setdefault("summary", "❓ Status nahi mila")
    return out
