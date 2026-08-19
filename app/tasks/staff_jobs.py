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
from typing import Any

from celery import Task, shared_task
from celery.exceptions import SoftTimeLimitExceeded

from app.platform import celery_async
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

from app.tasks.idempotency import idempotent_task


class _SkippedAsyncResult:
    """Minimal AsyncResult stand-in when enqueue is blocked (Beat-safe)."""

    def __init__(self, payload: dict[str, Any]):
        self.id = "owner-schedulers-skipped"
        self._payload = payload

    @property
    def state(self) -> str:
        return "SUCCESS"

    def ready(self) -> bool:
        return True

    def successful(self) -> bool:
        return True

    def failed(self) -> bool:
        return False

    def get(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._payload

    def forget(self) -> None:
        return None


class OwnerSchedulerGuardedTask(Task):
    """Block *scheduled* enqueue of staff jobs when owner_schedulers is engaged.

    Beat, run_due, DLQ redispatch, and `.delay()` all go through apply_async.
    Admin manual run_now may pass headers={"owner_os_manual": True} to bypass.
    Worker entry also re-checks (defense in depth for already-queued messages).
    """

    abstract = True

    def apply_async(self, args=None, kwargs=None, **options: Any):  # type: ignore[override]
        headers = dict(options.get("headers") or {})
        manual = bool(headers.get("owner_os_manual") or (kwargs or {}).get("_owner_os_manual"))
        if not manual:
            try:
                from app.platform.owner_os import record_scheduler_skip, scheduler_dispatch_allowed

                job = None
                if args:
                    job = args[0]
                elif kwargs:
                    job = kwargs.get("job")
                allowed, reason = scheduler_dispatch_allowed(job=str(job or "") or None)
                if not allowed:
                    logger.info(
                        "[staff_jobs] apply_async blocked job=%s reason=%s",
                        job,
                        reason,
                    )
                    payload = record_scheduler_skip(str(job or ""), reason, source="apply_async")
                    return _SkippedAsyncResult(payload)
            except Exception as e:
                # Fail-OPEN on guard errors so a store blip cannot freeze all automation.
                logger.debug("[staff_jobs] scheduler guard skip check failed: %s", e)
        return super().apply_async(args=args, kwargs=kwargs, **options)


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
    "hot_queue_brief",
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
    "approval_email_sweep",  # bounded pending-approval EMAIL sweep, gated APPROVAL_EMAIL_NOTIFY (default OFF); single-flight (2026-07-12)
    "social_drain",  # hourly :10 native social queue drain (gated SOCIAL_ENGINE); Celery+in-process (audit 2026-07-17)
    "sales_autopilot",  # hourly :25 Sales Autopilot canary tick (gated SALES_AUTOPILOT_ENABLED; INERT off)
    "task_lease_reap",  # hourly :05 expired agent-task lease close-out (gated AGENT_TASK_LEASE_REAP; INERT off)
    "daily_video",  # daily 09:45 IST per-client video producer — ENQUEUE-only (gated DAILY_VIDEO_ENABLED; INERT off)
    "gsc_rank",  # daily 00:30 IST Google Search Console rank snapshot (gated GSC_ENABLED; INERT off)
    "hq_auto_chase",  # hourly :28 unactioned inquiry cards -> EMAIL follow-up (gated HQ_AUTO_CHASE; INERT off)
    "reply_auto_send",  # hourly :30 safe known-prospect auto-reply (gated REPLY_AUTO_SEND; INERT off)
    "content_approval_sweep",  # daily 04:30 orphaned-pending retirement (gated CONTENT_APPROVAL_SWEEP; dry_run default)
    "daily_owner_brief",  # daily 08:10 IST owner brief + ntfy push (gated DAILY_OWNER_BRIEF_NTFY; INERT off)
)


def _run_async(coro):
    """Run one coroutine on the Celery process-local event loop.

    The loop intentionally stays alive between tasks so loop-bound DB pools and
    HTTP transports remain valid. Explicit shutdown is reserved for worker
    teardown/tests via ``_reset_worker_loop_for_tests``.
    """
    return celery_async.run(coro)


def _reset_worker_loop_for_tests() -> None:
    celery_async.reset_for_tests()


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
    # Requeue only the tick that owns the distributed slot. A denied tick is
    # usually a duplicate already queued by another chain; requeueing *every*
    # denied duplicate multiplies the queue. The slot owner has already
    # scheduled the next tick, while the watchdog can seed one fresh chain if
    # the owner dies. Fail closed on a denied slot/Redis outage.
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
        elif self_improve.enabled() and not slot_token:
            # Slot denied = duplicate or Redis guard unavailable. The owner (if
            # any) already owns the next requeue; this tick must terminate.
            logger.debug("[self-improve] tick skipped: slot denied; no requeue")
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
    name="app.tasks.staff_jobs.seed_first_week",
    max_retries=0,
    acks_late=False,
)
def seed_first_week(self, cid: str):
    """Customer-clicked "mera pehla 7-din ka plan banao" (Setup Wizard) — SIRF
    content seed (7-din calendar + WhatsApp promo + campaign suggestion), full
    auto_onboard NAHI (KB re-scrape/welcome jaise side-effects nahi chahiye).
    Worker me chalta hai (multi LLM-call — web process kabhi nahi, CLAUDE.md).
    Idempotent: upcoming items pehle se hon to seed skip (re-seed content_approval
    me dupes banata — auto_content.upcoming_item_count hi single-source guard).
    Event-driven (periodic nahi) — dead-man tracked nahi. Never raises."""
    try:
        from app.marketing import auto_content, clients_store

        cid = str(cid or "")
        client = clients_store.get_client(cid)
        if not client:
            return {"ok": False, "client_id": cid, "error": "client not found"}
        pending = auto_content.upcoming_item_count(cid)
        if pending > 0:
            return {
                "ok": True,
                "client_id": cid,
                "skipped": "already_has_upcoming",
                "upcoming": pending,
            }
        added = _run_async(auto_content.seed_client_content(client)) or 0
        return {"ok": True, "client_id": cid, "items_created": int(added)}
    except Exception as e:
        logger.warning(f"[seed_first_week] {cid}: {e}")
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
    base=OwnerSchedulerGuardedTask,
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
    # Defense in depth: already-queued messages still no-op when kill/agent controls engage.
    try:
        from app.platform.owner_os import record_scheduler_skip, scheduler_dispatch_allowed

        allowed, reason = scheduler_dispatch_allowed(job=job)
        if not allowed:
            return record_scheduler_skip(job, reason, source="run_staff_job")
    except Exception:
        pass
    try:
        from app.platform import owner_agent_execution as oae
        from app.platform.owner_os import record_scheduler_skip

        claim_ok, claim_reason = oae.claim_allowed(job=job)
        if not claim_ok:
            return record_scheduler_skip(job, claim_reason, source="run_staff_job_claim")
        # Cooperative cancel before body starts.
        tid = str(getattr(getattr(self, "request", None), "id", "") or "")
        if tid and oae.cancel_requested(tid):
            return {
                "ok": True,
                "skipped": True,
                "reason": "cooperative_cancel_acknowledged",
                "job": job,
                "stopped": True,
            }
    except Exception as e:
        # Fail-closed for Isha/agent-scoped jobs when control check itself breaks.
        try:
            from app.platform.owner_agent_execution import agent_for_job
            from app.platform.owner_os import record_scheduler_skip

            if agent_for_job(job):
                return record_scheduler_skip(
                    job, "agent_control_state_ambiguous", source="run_staff_job_claim"
                )
        except Exception:
            logger.debug("[staff_jobs] claim guard fail-closed path: %s", e)
    try:
        from app.platform import boot_grace

        if boot_grace.should_skip_boot_grace(job):
            delay = boot_grace.defer_seconds(job)
            logger.info(f"[staff_jobs] boot-grace skip job '{job}' — deferred retry in {delay}s")
            deferred = False
            # Keep the real job's dead-man heartbeat truthful. Previously only
            # the optional loop-supervisor emitted a synthetic marker, so the
            # prior day's heartbeat stayed stale and appeared overdue.
            try:
                run_staff_job.apply_async(args=[job], countdown=delay)
                deferred = True
            except Exception as e:
                logger.warning(f"[staff_jobs] boot-grace defer enqueue failed: {e}")
            try:
                from app.platform import automation_health

                automation_health.record_run(
                    job,
                    deferred,
                    0.0,
                    note=("boot_grace" if deferred else "boot_grace_enqueue_failed"),
                )
            except Exception:
                pass
            try:  # SP3: surface the silent boot-grace skip (gated LOOP_SUPERVISOR)
                from app.platform import loop_supervisor as _ls

                _ls.alert_boot_grace_skip(job)
            except Exception:
                pass
            return {"ok": True, "job": job, "skipped": "boot_grace", "deferred_in_s": delay}
    except Exception:
        pass
    aid = None
    tid = str(getattr(getattr(self, "request", None), "id", "") or "")
    try:
        from app.platform import owner_agent_execution as oae
        from app.platform import team_scheduler

        aid = oae.agent_for_job(job)
        if aid and tid:
            oae.register_running_task(aid, job, tid)
        if aid and oae.agent_abort_requested(aid):
            return {
                "ok": True,
                "skipped": True,
                "reason": "agent_abort_acknowledged",
                "job": job,
                "stopped": True,
            }
        ok = _run_async(
            team_scheduler._run_job(
                job,
                retry_count=int(getattr(self.request, "retries", 0) or 0),
                idempotency_key=tid,
            )
        )
        if ok is False:
            raise RuntimeError(f"staff job '{job}' reported failure")
        return {"ok": True, "job": job}
    except SoftTimeLimitExceeded:
        # Soft timeout = WORKLOAD bound problem. Blind Celery retry same workload
        # ko jalata hai (2026-07-17 prospect DLQ storm). Prefer wall-clock budgets
        # in the job body; if SoftTimeLimit still fires, return partial SUCCESS so
        # we do not fill dlq:failed_tasks / burn retries (2026-07-23 onboard/content).
        logger.warning(
            f"[staff_jobs] job '{job}' soft time limit — graceful partial (no retry/DLQ)"
        )
        return {"ok": True, "job": job, "partial": True, "reason": "soft_time_limit"}
    except Exception as e:  # invoke-level failure -> retry, fir DLQ
        logger.warning(f"[staff_jobs] job '{job}' invoke failed: {e}")
        raise self.retry(exc=e)
    finally:
        try:
            if aid and tid:
                from app.platform import owner_agent_execution as oae

                oae.clear_running_task(aid, tid)
        except Exception:
            pass
