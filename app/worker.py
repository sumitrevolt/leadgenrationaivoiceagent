"""
Celery Worker Configuration
Production-ready background task processing
"""

import logging
import os
import threading
import time

from celery import Celery, signals
from celery.schedules import crontab

from app.config import settings

# Setup logging for Celery
logger = logging.getLogger(__name__)

# Create Celery app
celery_app = Celery(
    "voice_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.tasks.scraping",
        "app.tasks.calling",
        "app.tasks.reporting",
        "app.tasks.sync",
        "app.tasks.brain_training",  # Brain training tasks
        "app.tasks.staff_jobs",  # Durable AI-staff jobs (dormant unless celery beat runs)
        "app.social_engine.tasks",  # Native social queue drain task
        "app.tasks.dev_worker",  # Dev control-plane runner (INERT unless DEV_ORCHESTRATOR+DEV_WORKER_ENABLED)
        "app.tasks.video_jobs",  # Video creative-pipeline render task (queue INERT unless CELERY_VIDEO_QUEUE=1)
        "app.tasks.kb_niche_refresh",  # ADR-104 A4.5 — owned single-niche KB catalog refresh (default queue)
        "app.tasks.dsh_jobs",  # Hardened DSH orchestration + governed domain bridge (INERT default)
        "app.tasks.onboard_pipeline",  # Onboarding factory pipeline (INERT unless ONBOARDING_PIPELINE=1)
        "app.marketing.content_os.tasks",  # Daily video automation: leadsgen + customer (INERT unless CONTENT_OS_ENABLED=1)
        "app.tasks.whatsapp_automation",
        "app.tasks.daily_social_post",
        "app.tasks.video_generator",
    ],
)

# ---------------------------------------------------------------------------
# HEAVY/LIGHT queue separation (prod-down qa-job lesson, worker-level):
# heavy staff-jobs (ML/LLM/network-bulk) ek hi worker pool me light jobs
# (alerts/dunning/triage) ko starve kar sakte. Gated `CELERY_HEAVY_QUEUE=1`
# (compose me ON jahan dedicated heavy worker bhi defined hai) → heavy jobs
# `heavy` queue me route hote, jise alag `worker-heavy` (concurrency=1)
# consume karta. Flag OFF (default) = sab default queue = aaj jaisa.
# NOTE: routing SEND-side evaluate hota hai (beat/app) — isliye flag compose
# me scheduler+app+worker sab pe set hai, warna heavy task default me jayega.
# ---------------------------------------------------------------------------
HEAVY_STAFF_JOBS = {
    "qa",
    "trainer",
    "blog",
    "content",
    "hot_queue_brief",
    "hot_queue_owner_pack",
    "digest",
    "prospect",
}


def _heavy_queue_enabled() -> bool:
    return os.environ.get("CELERY_HEAVY_QUEUE", "0").strip().lower() in ("1", "true", "yes")


def _is_heavy_worker() -> bool:
    """True only inside the dedicated heavy consumer process.

    CELERY_HEAVY_QUEUE is a routing flag shared by app, scheduler, and the
    default worker, so it cannot safely identify a worker process role.
    """
    return os.environ.get("CELERY_HEAVY_WORKER", "0").strip().lower() in ("1", "true", "yes")


def _route_staff_task(name, args, kwargs, options, task=None, **kw):
    """Router fn: heavy staff-jobs → 'heavy' queue (sirf flag ON pe)."""
    try:
        if (
            name == "app.tasks.staff_jobs.run_staff_job"
            and _heavy_queue_enabled()
            and args
            and str(args[0]) in HEAVY_STAFF_JOBS
        ):
            return {"queue": "heavy"}
    except (TypeError, IndexError) as _e:
        logger.debug("_route_staff_task routing failed, using default queue: %s", _e)
    return None


def _video_queue_enabled() -> bool:
    return os.environ.get("CELERY_VIDEO_QUEUE", "0").strip().lower() in ("1", "true", "yes")


def _route_video_task(name, args, kwargs, options, task=None, **kw):
    """Router fn: video-pipeline render task -> 'video' queue (sirf flag ON pe).
    Mirrors _route_staff_task's heavy-queue pattern exactly — separate router
    (not the static dict) so it's flag-gated with a safe unset->default-queue
    fallback, matching this project's INERT-default feature convention."""
    try:
        if (
            name
            in (
                "app.tasks.video_jobs.build_creative_video_task",
                "app.tasks.video_jobs.render_creative_os_task",
                "app.tasks.video_jobs.daily_video_client_task",
            )
            and _video_queue_enabled()
        ):
            return {"queue": "video"}
    except Exception as _e:
        logger.debug("_route_video_task routing failed, using default queue: %s", _e)
    return None


def _onboard_queue_enabled() -> bool:
    """INERT default. When ON, Day-1 onboard_client uses the existing heavy worker.

    50 simulated/live onboardings on the default celery pool (conc=4) can delay
    alerts/triage. Do NOT invent a new queue name — an unconsumed queue orphans
    tasks. heavy is already drained by worker-heavy. Flag OFF = today's celery
    default. Arm only after a measured enqueue→start >5 min burst.
    """
    return os.environ.get("CELERY_ONBOARD_QUEUE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def _route_onboard_task(name, args, kwargs, options, task=None, **kw):
    """Router fn: onboard_client -> heavy when CELERY_ONBOARD_QUEUE=1."""
    try:
        if name == "app.tasks.staff_jobs.onboard_client" and _onboard_queue_enabled():
            return {"queue": "heavy"}
    except Exception as _e:
        logger.debug("_route_onboard_task routing failed, using default queue: %s", _e)
    return None


def _route_kb_refresh_task(name, args, kwargs, options, task=None, **kw):
    """Router fn: ADR-104 kb_niche_refresh -> 'heavy' queue (sirf flag ON pe).
    2026-07-15 live-prod finding: refresh_niche_task loads its own fastembed
    model inside the fork on top of whatever the default queue's staff-job
    battery is doing concurrently — 3x observed SIGKILL/WorkerLostError in the
    leadgen_worker container's 2GB memcg limit (host had 5.2GB free; this was
    a per-container cap collision, not host exhaustion). WorkerLostError
    bypasses this task's own max_retries entirely (broker-level redelivery of
    the same task id), so under sustained contention this could retry
    indefinitely, each cycle burning ~90-120s and risking collateral OOM of
    unrelated concurrent tasks sharing the container. worker-heavy already
    exists (concurrency=1, 2.44GB, near-idle) for exactly this class of
    problem — mirrors _route_video_task's exact pattern. Never touches
    HEAVY_STAFF_JOBS or the default queue's existing routing."""
    try:
        if name == "app.tasks.kb_niche_refresh.refresh_niche_task" and _heavy_queue_enabled():
            return {"queue": "heavy"}
    except Exception as _e:
        logger.debug("_route_kb_refresh_task routing failed, using default queue: %s", _e)
    return None


def _route_self_improve_task(name, args, kwargs, options, task=None, **kw):
    """Router: self-improve tick/revive → heavy when CELERY_HEAVY_QUEUE=1.

    2026-07-28 prod evidence: leadgen_worker (2g, concurrency=4) took 14
    memcg OOM/SIGKILL in 24h while SELF_IMPROVE_LOOP=1. worker_max_memory_per_child
    only recycles *between* tasks; a single LLM-heavy tick can grow past the
    shared cgroup before recycle, and four forks amplify that. worker-heavy is
    concurrency=1 + 2500m — the right isolation for this continuous chain.
    Flag OFF keeps today's default-queue behaviour (local/dev without heavy).
    """
    try:
        if (
            name
            in (
                "app.tasks.staff_jobs.self_improve_tick",
                "app.tasks.staff_jobs.self_improve_revive",
            )
            and _heavy_queue_enabled()
        ):
            return {"queue": "heavy"}
    except Exception as _e:
        logger.debug("_route_self_improve_task routing failed, using default queue: %s", _e)
    return None


# Production-ready configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    result_expires=3600,
    beat_schedule_filename="/app/data/celerybeat-schedule",
)

# ---------------------------------------------------------------------------
# BEAT SCHEDULE — all `staff-*` jobs (team_scheduler._run_job dispatcher)
# ---------------------------------------------------------------------------
celery_app.conf.beat_schedule = {
    # System health / housekeeping
    "staff-heartbeat-5m": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute="*/5"),
        "args": ("heartbeat",),
    },

    # Core daily beats (IST timezone)
    "staff-trainer-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=3, minute=0),
        "args": ("trainer",),
    },
    "staff-blog-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=6, minute=30),
        "args": ("blog",),
    },
    "staff-content-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=7, minute=0),
        "args": ("content",),
    },
    "staff-hot-queue-brief-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=15),
        "args": ("hot_queue_brief",),
    },
    # ADR-OWNER-1: 09:00 IST — CSV+MD+nfty push so owner has click-ready WA packs
    # for the day's hot leads by 9:05 AM. Closes the loop on `calling_flagged`
    # cards that previously sat un-actioned for days.
    "staff-hot-queue-owner-pack-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=0),
        "args": ("hot_queue_owner_pack",),
    },
    "staff-digest-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=30),
        "args": ("digest",),
    },
    "staff-prospect-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=30),
        "args": ("prospect",),
    },
    "staff-email-outreach-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour="9,10,11,12,13,14,15,16,17,18,19", minute=5),
        "args": ("email_outreach",),
    },
    "staff-revenue-snapshot-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=0, minute=15),  # B1 MRR snapshot (gated REVENUE_TRENDS)
        "args": ("revenue_snapshot",),
    },
    "staff-gsc-rank-daily": {
        # 00:30 IST: Google Search Console rank/impression snapshot — SEO
        # observability (programmatic pages abhi untracked the). Job body
        # no-ops unless GSC_ENABLED=1 + service-account creds (INERT off).
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=0, minute=30),
        "args": ("gsc_rank",),
    },
    # Boss daily standup — in-process loop ke saath parity (gated AGENT_STANDUP;
    # flag OFF = run_staff_job no-op early return, zero behaviour change).
    "staff-standup-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=0),
        "args": ("standup",),
    },
    "staff-engineer-sre-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=45),
        "args": ("engineer_sre",),
    },
    "staff-engineer-finops-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=5),
        "args": ("engineer_finops",),
    },
    "staff-engineer-security-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=35),
        "args": ("engineer_security",),
    },
    # council 2026-06-25 — 3 new engineer agents (gated INERT in run_X())
    "staff-engineer-dbre-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=10, minute=0),
        "args": ("engineer_dbre",),
    },
    "staff-engineer-dataquality-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=10, minute=30),
        "args": ("engineer_dataquality",),
    },
    "staff-engineer-deps-weekly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(day_of_week="sun", hour=4, minute=30),
        "args": ("engineer_deps",),
    },
    # council 2026-06-26: Arya MCP Engineer hourly :40 (gated MCP_ENGINEER).
    # Offset from Pranav SRE :45 so they don't co-fire on the same minute.
    "staff-mcp-engineer-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=40),
        "args": ("mcp_engineer",),
    },
    # Content-approval notifications (2026-07-13) — gated CONTENT_APPROVAL_NOTIFY
    # INERT flag = run_staff_job no-op; no duplicate route/page.
    "staff-content-approval-notify-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=35),
        "args": ("content_approval_notify",),
    },
    "staff-readiness-digest-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=35),
        "args": ("readiness_digest",),
    },
    # Product One health monitor (2026-07-14) — gated PRODUCT_ONE_HEALTH (INERT default).
    # Re-uses `product_one_health` task — no new code path, just beat registration.
    "staff-product-one-health-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=20),
        "args": ("product_one_health",),
    },
    # Bounded pending-approval EMAIL sweep (single-flight). INERT unless
    # APPROVAL_EMAIL_NOTIFY=1 — the job runs but the sweep no-ops when off.
    "staff-approval-email-sweep-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=40),
        "args": ("approval_email_sweep",),
    },
    # Sales Autopilot canary tick. INERT unless SALES_AUTOPILOT_ENABLED=1
    # (run_tick no-ops when off). Dry-run default; no catch-up flood.
    "staff-sales-autopilot-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=25),
        "args": ("sales_autopilot",),
    },
    # Hot Queue auto-chase. INERT unless HQ_AUTO_CHASE=1 (run_auto_chase no-ops).
    # Email-only follow-up for unactioned inquiry cards; WhatsApp stays 1-click human.
    "staff-hq-auto-chase-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=28),
        "args": ("hq_auto_chase",),
    },
    # Safe known-prospect auto-reply sweep — DECOUPLED from IMAP triage so
    # replies still fire even if IMAP is down/gated. INERT unless REPLY_AUTO_SEND=1.
    "staff-reply-auto-send-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=30),
        "args": ("reply_auto_send",),
    },
    # Orphaned-pending approval retirement — daily 04:30 IST. dry_run default;
    # CONTENT_APPROVAL_SWEEP_LIVE=1 actuates writes (fail-closed otherwise).
    "staff-content-approval-sweep-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=4, minute=30),
        "args": ("content_approval_sweep",),
    },
    # Daily owner brief + ntfy push (08:10 IST). Gated DAILY_OWNER_BRIEF_NTFY.
    # Pushes P0/P1 exceptions to owner phone; always saves data/daily_owner_brief.txt.
    "staff-daily-owner-brief": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=10),
        "args": ("daily_owner_brief",),
    },
    # Trial-to-paid nudge — BLK-02 (2026-08-23). INERT unless TRIAL_NUDGE_ENABLED=1
    # (run_trial_nudge no-ops when off / TRIAL_NUDGE_HARD_OFF=1 blocks always).
    # Email-only; WhatsApp text sirf owner 1-click human ke liye return hota hai.
    "staff-trial-nudge-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=50),
        "args": ("trial_nudge",),
    },
    # Expired agent-task lease close-out (ADR-150). MUST be here, not only in the
    # in-process scheduler_loop: production runs `celery -A app.worker beat` with
    # RUN_IN_PROCESS_SCHEDULER=0, so an in-process-only job is DEAD in prod — the
    # exact fault call_kpi_digest hit (audit 2026-07-04). Job body no-ops unless
    # AGENT_TASK_LEASE_REAP=1.
    "staff-task-lease-reap-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=5),
        "args": ("task_lease_reap",),
    },
    # Periodic social-engine drain (audit 2026-07-17): enqueue fires a one-shot
    # Celery drain, but retry/dead/queued jobs need a scheduled sweep independent
    # of VIDEO_AD_CYCLE. STAFF_JOB path so prod_check + dead-man + admin toggle
    # all see it; social_engine.drain task remains for one-shot enqueue.
    "staff-social-drain-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=10),
        "args": ("social_drain",),
    },
    "staff-process-autostart-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(
            hour=11, minute=30
        ),  # 11:30 IST (timezone=Asia/Kolkata set in celery config)
        "args": ("process_autostart",),
    },
    # Self-improve CONTINUOUS loop ka dead-man REVIVER (loop khud self-requeue
    # chain hai — yeh sirf stale-heartbeat pe restart karta; flag OFF = no-op).
    "staff-selfimprove-revive": {
        "task": "app.tasks.staff_jobs.self_improve_revive",
        "schedule": crontab(minute="*/20"),
    },

    # Daily social + video posting — 3x within 9am–7pm TRAI window
    # GATED: POSTIZ_API_KEY + VIDEO_AD_CYCLE=1 (auto-post gate)
    # Generates branded videos + posts via Postiz (own brand + clients)
    "staff-daily-social-post-morning": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=9, minute=30),
        "options": {"expires": 10800},
    },
    "staff-daily-social-post-midday": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=13, minute=0),
        "options": {"expires": 10800},
    },
    "staff-daily-social-post-evening": {
        "task": "app.tasks.daily_social_post.run_daily_social_post",
        "schedule": crontab(hour=16, minute=0),
        "options": {"expires": 10800},
    },

    # WhatsApp full automation — hourly within 9am–7pm TRAI window
    # GATED: WHATSAPP_AUTO_SEND=1 + WHATSAPP_AUTO_SEND_HARD_OFF=0
    # ⚠️ HIGH RISK: cold/bulk auto-send = number ban in 72 hours
    "staff-whatsapp-automation-hourly": {
        "task": "app.tasks.whatsapp_automation.run_whatsapp_automation",
        "schedule": crontab(hour="9,10,11,12,13,14,15,16,17,18,19", minute=0),
        "options": {"expires": 3600},
    },
}

# ---------------------------------------------------------------------------
# SAFETY GATE: legacy (Cloud-Run/Vertex era) beat entries DEFAULT OFF.
# Bina GCP/Vertex creds ke ye tasks heavy/no-op hain, aur `process_queue`
# jaise entries call-side-effects rakh sakte. Celery-beat switch ka core =
# sirf `staff-*` jobs (team_scheduler._run_job dispatcher — saare naye
# engines included) + `process-voice-followups` (production-critical
# transactional callback drain, not a legacy entry). Puraane entries chahiye
# to ENABLE_LEGACY_BEAT=1.
# ---------------------------------------------------------------------------
if os.environ.get("ENABLE_LEGACY_BEAT", "0").strip().lower() not in ("1", "true", "yes"):
    _KEEP_KEYS = {"process-voice-followups"}  # production-critical, not legacy
    celery_app.conf.beat_schedule = {
        k: v
        for k, v in celery_app.conf.beat_schedule.items()
        if k.startswith("staff-") or k in _KEEP_KEYS
    }

# Boss autonomy sweep — always scheduled; the TASK is flag-gated inert itself
# (BOSS_FULL_AUTONOMY=1 AND BOSS_DECISION_GOVERNANCE=1 required). Never a second
# scheduler: this only drives app.platform.boss_autonomy.run_once().
celery_app.conf.beat_schedule["boss-autonomy-sweep"] = {
    "task": "app.tasks.staff_jobs.boss_autonomy_sweep",
    "schedule": crontab(minute="*/5"),
    "args": (),
}

# ContentOS daily video automation tasks
celery_app.conf.beat_schedule["content_os.daily_video_run"] = {
    "task": "content_os.daily_video_run",
    "schedule": crontab(hour=9, minute=0),
    "args": (),
}
celery_app.conf.beat_schedule["content_os.scan_inbox"] = {
    "task": "content_os.scan_inbox",
    "schedule": crontab(minute="*/2"),
    "args": (),
}
celery_app.conf.beat_schedule["content_os.notify_owner"] = {
    "task": "content_os.notify_owner",
    "schedule": crontab(minute="*/15"),
    "args": (),
}


# Task definitions
@celery_app.task(bind=True, max_retries=3)
def example_task(self, data):
    """Example task"""
    try:
        # Process data
        return {"status": "success", "data": data}
    except Exception as e:
        raise self.retry(exc=e, countdown=60)