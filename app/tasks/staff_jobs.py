"""Durable Celery wrappers for the AI-staff periodic jobs.

WHY: aaj AI-staff automation (content, outreach, onboarding, watchdog, etc.)
in-process APScheduler loop (`app/platform/team_scheduler.py`) pe chalti hai —
ek hi process, app restart pe job miss/double ho sakta. Yeh module wahi jobs
Celery beat ke through **durable** chalata hai: dedicated worker, restart-safe
schedule, retry, aur dead-letter (worker.py `on_task_failure` -> Redis DLQ).

ACTIVATION — module import-safe always; beat entries fire only when `celery beat` runs:
  - LIVE VPS (2026-06-10 se): durable path ON — RUN_IN_PROCESS_SCHEDULER=0 +
    leadgen_worker + leadgen_scheduler (beat) containers chal rahe.
  - Beat band ho to in-process APScheduler (RUN_IN_PROCESS_SCHEDULER=1) = rollback fallback.

DURABLE path pe switch (double-run avoid):
    RUN_IN_PROCESS_SCHEDULER=0   # in-process loop band
    docker compose -f docker-compose.vps.yml --profile celery up -d
    # ab celery worker + celery beat owner; web process scheduler nahi chalata

Har job internally defensive hai (team_scheduler._run_job kabhi raise nahi karta);
Celery retry sirf invoke-level failure (import/loop) pe lagta hai.
"""

from __future__ import annotations

import asyncio
import time

from celery import shared_task

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

from app.tasks.idempotency import idempotent_task

# Same job names as team_scheduler._run_job dispatcher.
STAFF_JOBS = (
    "growth",
    "ops",
    "qa",
    "trainer",
    "digest",
    "content",
    "blog",
    "prospect",
    "email_outreach",
    "reply_triage",
    "watchdog",
    "onboard",
    "standup",
    "engineer_sre",
    "engineer_finops",
    "engineer_security",
    "engineer_dbre",  # council: Kabir Postgres reliability (gated DBRE_AGENT)
    "engineer_dataquality",  # council: Diya lead/CRM integrity (gated DATA_INTEGRITY_AGENT)
    "engineer_deps",  # council: Aryan dependency CVE audit (gated DEPS_AGENT)
    "mcp_engineer",  # council 2026-06-26: Arya MCP health (3-layer surface, gated MCP_ENGINEER)
    "readiness_digest",
    "pipeline",
    "email_followup",
    "kb_refresh",
    "midday_prospect",
    "evening_wrap",
    "weekly_marketing",
    "saturday_hygiene",
    "meter_watch",  # SP1 billing meter-failure watcher (gated METER_ALERTS)
    "process_autostart",  # D V1.1 process-engine auto-start (gated PROCESS_AUTOSTART)
    "revenue_snapshot",  # B1 daily MRR/churn snapshot (gated REVENUE_TRENDS)
    "flow_cron",  # Phase-3 Flow Runner cron scan (gated FLOW_RUNNER + FLOW_AUTO_TRIGGERS)
    "afternoon_content",  # 2nd daily content-gen pass (gated AFTERNOON_CONTENT)
    "evening_prospect",  # 3rd daily free lead-harvest pass (gated EVENING_PROSPECT)
    "obsidian_push",  # second-brain compact + push; safe no-op if OBSIDIAN_SYNC/git unavailable
    "platform_dial",  # daily 11:30 IST self-sale AI cold-call batch (gated PLATFORM_DIAL_DAILY)
    "call_kpi_digest",  # daily 19:30 IST Lekha call-KPI digest (was in-process-only → dead on Celery topology, audit 2026-07-04)
    "product_one_health",  # hourly :20 Product 1 Customer Health + Approval Reminder + SLA Recovery sweep (2026-07-08)
)


def _run_async(coro):
    """Async coroutine ko sync Celery task ke andar safely chalao (apna loop).

    Teardown = wahi sequence jo asyncio.run karta hai: pending tasks cancel +
    asyncgens shutdown PHIR close. Bina iske leftover transports (httpx/aiohttp)
    GC pe closed-loop pe call_soon karte → "Event loop is closed" log spam.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        finally:
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.self_improve_tick",
    max_retries=0,
    # acks_late=False (ack-on-receipt) — DELIBERATE: yeh task khud-ko-requeue karne
    # wali chain hai. acks_late=True hota to worker-loss (deploy/recreate) pe in-flight
    # tick REDELIVER hota + chain requeue bhi → DUPLICATE chains → queue flood (2501
    # self_improve_tick dekha gaya). Chain waise bhi ensure_alive() revive se self-heal
    # karti, isliye restart pe ek tick lose hona safe hai. Single-chain = no multiply.
    acks_late=False,
)
def self_improve_tick(self):
    """Self-improve CONTINUOUS loop ka ek tick: run_once → khud ko requeue
    (countdown=gap). Koi cron timing nahi — task complete → agla task.
    Flag OFF ho jaye to chain khud ruk jaati (no requeue). Kabhi raise nahi."""
    t0 = time.monotonic()
    res = {}
    slot_token = ""
    try:
        from app.agents import self_improve

        if self_improve.enabled():
            slot_token = self_improve.acquire_tick_slot()
            if slot_token:
                res = _run_async(self_improve.run_once()) or {}
            else:
                res = {"enabled": True, "skipped": "tick_slot"}
        else:
            res = {"enabled": False}
    except Exception as e:
        logger.warning(f"[self-improve] tick failed: {e}")
        res = {"ok": False, "error": str(e)[:200]}
    # requeue ALWAYS attempt (loop never dies) — sirf flag OFF pe chain stop
    try:
        from app.agents import self_improve

        if self_improve.enabled() and slot_token:
            gap = self_improve.gap_seconds()
            if res.get("skipped") == "daily_cap":
                gap = 3600  # cap hit — ghante me wapas check (naya din = resume)
            queued = False
            try:
                self_improve_tick.apply_async(countdown=gap)
                queued = True
            finally:
                self_improve.release_tick_slot(slot_token)
            if queued:
                self_improve.note_tick_requeue(gap)
        elif slot_token:
            self_improve.release_tick_slot(slot_token)
    except Exception as e:
        logger.warning(f"[self-improve] requeue failed (watchdog revive karega): {e}")
    try:
        from app.platform import automation_health

        ok = bool(res.get("ok", res.get("enabled", False)))
        note = str(res.get("action") or res.get("skipped") or res.get("error") or "")[:120]
        automation_health.record_run("self_improve", ok, time.monotonic() - t0, note=note)
    except Exception:
        pass
    return {
        "ok": bool(res.get("ok", res.get("enabled", False))),
        "action": res.get("action", res.get("skipped", "")),
    }


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.onboard_client",
    max_retries=0,
    acks_late=False,
)
def onboard_client(self, cid: str, send_welcome: bool = True):
    """One-shot per-client auto-onboard, fired on signup / admin-onboard so a NEW
    customer gets day-1 value IMMEDIATELY (website→KB seed + first content pack +
    customer-visible content queue + niche snapshot) instead of an empty portal
    until the AUTO_ONBOARD-gated hourly sweep. Runs in the WORKER (heavy scrape/LLM
    — never the web process, per CLAUDE.md). Idempotent: auto_onboard marks
    setup_done so the hourly sweep skips it. send_welcome=False when the caller
    already sent its own welcome (no double WhatsApp on /signup). Event-driven
    (not a periodic job) so it is NOT dead-man tracked. Never raises."""
    try:
        from app.marketing import onboarding

        res = _run_async(onboarding.auto_onboard(str(cid), send_welcome=bool(send_welcome))) or {}
        return {"ok": bool(res.get("ok")), "client_id": str(cid)}
    except Exception as e:
        logger.warning(f"[onboard_client] {cid}: {e}")
        return {"ok": False, "client_id": str(cid), "error": str(e)[:200]}


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.process_tick",
    max_retries=0,
    acks_late=True,
)
def process_tick(self, run_id: str):
    """Process-engine run ko worker me advance karo (babysitter-pattern).
    RUNNING rahe to khud requeue (10s) — breakpoint/end pe chain rukti.
    Kabhi raise nahi."""
    res = {}
    try:
        from app.agents import flow_dispatch

        res = _run_async(flow_dispatch.advance(run_id)) or {}
    except Exception as e:
        logger.warning(f"[process] tick failed {run_id}: {e}")
        return {"ok": False, "run_id": run_id, "error": str(e)[:150]}
    try:
        if (
            res.get("status") == "running"
            or res.get("note") == "step budget — tick continue karega"
        ):
            process_tick.apply_async(args=[run_id], countdown=10)
    except Exception:
        pass
    return {"ok": True, "run_id": run_id, "status": res.get("status", "")}


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.self_improve_revive",
    max_retries=0,
    acks_late=True,
)
def self_improve_revive(self):
    """Dead-man reviver (beat */20min): heartbeat stale + flag ON → tick enqueue.
    Loop alive ho to no-op. Kabhi raise nahi."""
    try:
        from app.agents import self_improve

        return self_improve.ensure_alive()
    except Exception as e:
        logger.warning(f"[self-improve] revive failed: {e}")
        return {"ok": False, "error": str(e)[:120]}


@shared_task(
    bind=True,
    name="app.tasks.staff_jobs.run_staff_job",
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
)
@idempotent_task("run_staff_job", ttl=3600)
def run_staff_job(self, job: str):
    """Ek AI-staff job durably chalao (team_scheduler._run_job ka Celery wrapper)."""
    if job not in STAFF_JOBS:
        logger.warning(f"[staff_jobs] unknown job '{job}' — skip")
        return {"ok": False, "job": job, "reason": "unknown"}
    try:
        from app.platform import boot_grace

        if boot_grace.should_skip_boot_grace(job):
            delay = boot_grace.defer_seconds(job)
            logger.info(f"[staff_jobs] boot-grace skip job '{job}' — deferred retry in {delay}s")
            try:
                run_staff_job.apply_async(args=[job], countdown=delay)
            except Exception as e:
                logger.warning(f"[staff_jobs] boot-grace defer enqueue failed: {e}")
            try:  # SP3: surface the silent boot-grace skip (gated LOOP_SUPERVISOR)
                from app.platform import loop_supervisor as _ls

                _ls.alert_boot_grace_skip(job)
            except Exception:
                pass
            return {"ok": True, "job": job, "skipped": "boot_grace", "deferred_in_s": delay}
    except Exception:
        pass
    try:
        from app.platform import team_scheduler

        _run_async(team_scheduler._run_job(job))
        return {"ok": True, "job": job}
    except Exception as e:  # invoke-level failure -> retry, fir DLQ
        logger.warning(f"[staff_jobs] job '{job}' invoke failed: {e}")
        raise self.retry(exc=e)
