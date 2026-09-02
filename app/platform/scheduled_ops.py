"""Secondary scheduled automation — evening wrap, weekly marketing bank, Sat hygiene.

Project ke baaki engines (content/digest/prospect) ke ALAWA yeh slots cover
karte hain jo pehle handler the par beat/loop me missing the. Kabhi raise nahi.
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


async def run_evening_wrap() -> dict[str, Any]:
    """18:30 IST — din ka wrap-up Boss event + hot leads recap."""
    out: dict[str, Any] = {"ok": True}
    try:
        from app.platform import team, today_overview

        snap = today_overview.build()
        headline = str(snap.get("headline") or "evening wrap")[:200]
        probs = len(snap.get("problems") or [])
        events = int((snap.get("totals") or {}).get("events_today") or 0)
        team.log_event(
            "manager",
            "evening_wrap",
            f"🌆 {headline}",
            status="warn" if probs else "ok",
            meta={"problems": probs, "events_today": events},
        )
        out["headline"] = headline
    except Exception as e:
        logger.debug(f"[scheduled_ops] evening overview skip: {e}")

    try:
        from app.platform import lead_scoring, team

        hot = await lead_scoring.top_hot_leads(5)
        if hot.get("ok") and int(hot.get("hot_count") or 0) > 0:
            team.log_event(
                "neha",
                "evening_hot",
                f"🔥 EOD {hot['hot_count']} hot leads pending Rohan follow-up",
                status="ok",
            )
        out["hot_count"] = int(hot.get("hot_count") or 0)
    except Exception as e:
        logger.debug(f"[scheduled_ops] evening hot skip: {e}")

    return out


async def run_weekly_marketing() -> dict[str, Any]:
    """Wed 12:30 IST — niche content bank top-up (organic + client packs)."""
    if os.environ.get("WEEKLY_MARKETING_PACK", "1").strip().lower() not in ("1", "true", "yes"):
        return {"ok": True, "skipped": "WEEKLY_MARKETING_PACK off"}
    try:
        from app.marketing import niche_pack
        from app.platform import team

        res = await niche_pack.build_all(tier="S", limit=4)
        n = int(res.get("count") or len(res.get("packs") or []))
        if n:
            team.log_event(
                "isha", "weekly_pack", f"📦 {n} S-tier niche marketing packs ready", status="ok"
            )
        return {"ok": True, **res}
    except Exception as e:
        logger.warning(f"[scheduled_ops] weekly marketing failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def run_saturday_hygiene() -> dict[str, Any]:
    """Sat 04:00 IST — DLQ sweep + celery backlog trim (gated SCHEDULER_HYGIENE)."""
    if os.environ.get("SCHEDULER_HYGIENE", "1").strip().lower() not in ("1", "true", "yes"):
        return {"ok": True, "skipped": "SCHEDULER_HYGIENE off"}
    out: dict[str, Any] = {"ok": True}
    try:
        from app.platform import dlq_retry, team

        dlq = await dlq_retry.run_sweep(max_items=40, force=True)
        out["dlq"] = dlq
        if len(dlq.get("retried") or []) + len(dlq.get("dead") or []) > 0:
            team.log_event(
                "kavya",
                "hygiene_dlq",
                f"🧹 DLQ sweep retried={len(dlq.get('retried') or [])} dead={len(dlq.get('dead') or [])}",
                status="ok",
            )
    except Exception as e:
        logger.debug(f"[scheduled_ops] dlq hygiene skip: {e}")

    try:
        import redis as _redis

        from app.config import settings
        from app.platform import team

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        min_depth = int(os.environ.get("CELERY_TRIM_MIN_DEPTH", "800") or 800)
        # Every queue app/worker.py's task_routes can send work to (2026-07-02)
        # — not just the default "celery" queue. leadgen_worker previously had
        # no -Q flag and silently never consumed calling/scraping/reporting/
        # sync/training/heavy, so those are equally capable of building an
        # unbounded backlog now that a worker actually drains them. BUT: only
        # celery/scraping/reporting/sync/training/heavy are safe to
        # auto-delete unattended — every task on them is beat-driven and
        # re-enqueued on its own schedule regardless. "calling" is NOT: it
        # carries run_campaign_task (admin-launched, never beat-regenerated —
        # deleting a queued one silently drops the campaign AND leaks its
        # launch lock, since the delete skips the task's own `finally:
        # release_campaign_lock()`) and process_callbacks' make_call_task
        # (only re-enqueued while the lead is still inside its 1-hour
        # next_call_at window — past that, gone for good). So "calling" is
        # ALERT-ONLY here; an oversized backlog there needs a human decision,
        # via the one-time `scripts/vps_celery_trim.py` (which does include
        # it, deliberately, as a reviewed manual action) — not an unattended
        # weekly auto-delete.
        trim_queues = ["celery", "scraping", "reporting", "sync", "training", "heavy"]
        alert_only_queues = ["calling"]
        depths: dict[str, int] = {}
        trimmed: dict[str, int] = {}
        alerts: dict[str, int] = {}
        for q in trim_queues:
            depth = int(r.llen(q) or 0)
            depths[q] = depth
            if depth >= min_depth:
                r.delete(q)
                trimmed[q] = depth
        for q in alert_only_queues:
            depth = int(r.llen(q) or 0)
            depths[q] = depth
            if depth >= min_depth:
                alerts[q] = depth
        out["queue_depths"] = depths
        if trimmed:
            team.log_event(
                "kavya",
                "hygiene_queue",
                f"✂️ queues trimmed: {trimmed} (all beat re-scheduled — safe)",
                status="warn",
            )
            out["queues_trimmed"] = trimmed
        if alerts:
            team.log_event(
                "kavya",
                "hygiene_queue_alert",
                f"⚠️ calling queue backlog {alerts} — NOT auto-trimmed (carries "
                f"admin campaigns + callbacks); review + run "
                f"scripts/vps_celery_trim.py manually if stale",
                status="warn",
            )
            out["queues_alerted"] = alerts
    except Exception as e:
        logger.debug(f"[scheduled_ops] celery trim skip: {e}")

    return out


__all__ = ["run_evening_wrap", "run_weekly_marketing", "run_saturday_hygiene"]
