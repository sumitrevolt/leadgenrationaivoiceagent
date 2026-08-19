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
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=False,
    # Narrow deploy/restart recovery: if beat is restarted just after a cron
    # boundary, allow only the last 15 minutes of missed cron work to catch up.
    # This prevents a near-slot deploy from silently losing a daily run while
    # avoiding broad stale replay (especially prospect harvesting) hours later.
    beat_cron_starting_deadline=900,
    # Task routing by queue (router-fn pehle, fir static dict)
    task_routes=(
        _route_staff_task,
        _route_video_task,
        _route_onboard_task,
        _route_kb_refresh_task,
        _route_self_improve_task,
        {
            "app.tasks.scraping.*": {"queue": "scraping"},
            "app.tasks.calling.*": {"queue": "calling"},
            "app.tasks.reporting.*": {"queue": "reporting"},
            "app.tasks.sync.*": {"queue": "sync"},
            "app.tasks.brain_training.*": {"queue": "training"},
            "app.tasks.dsh_jobs.run_dsh_workforce": {"queue": "dsh"},
            "app.tasks.dsh_jobs.execute_governed_capability": {"queue": "celery"},
        },
    ),
    # Rate limits per task type
    task_annotations={
        "app.tasks.calling.make_call": {"rate_limit": "20/m"},
        "app.tasks.scraping.scrape_leads": {"rate_limit": "5/m"},
        "app.tasks.brain_training.*": {"rate_limit": "10/m"},
    },
    # Reliability settings
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,  # Reject tasks if worker dies
    task_acks_on_failure_or_timeout=True,
    # Celery 5.x + research 2026-08-01: with acks_late, cancel in-flight tasks when
    # the broker connection drops so they can be redelivered instead of hanging.
    # Celery 6.0 flips this default; set explicitly now for launch readiness.
    worker_cancel_long_running_tasks_on_connection_loss=True,
    # Result backend settings
    result_expires=86400,  # 24 hours
    result_extended=True,  # Store task metadata
    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetch for fair scheduling
    worker_max_tasks_per_child=100,  # Restart sooner — long-lived forks accumulate RSS
    # KiB. Recycle only runs BETWEEN tasks; still lower than the 2g cgroup so a
    # quiet child is replaced before four of them sum past the memcg (2026-07-28).
    worker_max_memory_per_child=350000,  # ~350MB
    worker_disable_rate_limits=False,
    # Task execution limits
    task_time_limit=600,  # Hard limit: 10 minutes
    task_soft_time_limit=540,  # Soft limit: 9 minutes (allows cleanup)
    # Connection pooling
    broker_pool_limit=10,
    broker_connection_timeout=10,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    # Result backend connection pooling
    redis_max_connections=20,
    # Visibility timeout for long-running tasks
    broker_transport_options={
        "visibility_timeout": 3600,  # 1 hour
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
    },
    # Event monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# ============================================
# Celery Signals for Production Monitoring
# ============================================


@signals.worker_process_init.connect
def on_worker_process_init(**kwargs):
    """ADR-104 A10 (2026-07-15) — pre-warm the Qdrant/fastembed singleton on
    worker_heavy boot, OFF the task time budget.

    Measured finding: both post-routing-fix `kb_niche_refresh.refresh_niche_task`
    executions on worker_heavy showed an IDENTICAL ~90s silent gap (zero log
    output) ending exactly at the task's own `soft_time_limit=90s`, followed by
    ~26-27s of real (fast) work once forcibly kicked onto the Chroma/keyword
    fallback. That 90s ceiling is the task's OWN soft limit, not any timeout
    inside knowledge_base.py (5s Qdrant client / 20s embed-load) — meaning the
    true hang duration is UNKNOWN and would just grow if the limits were
    raised (the trap: "increase limits to conceal an unresolved hang"). The
    likely cause is first-use-per-process cold cost (qdrant_client/fastembed/
    onnxruntime imports + ONNX model init) in a worker_heavy process that has
    never touched Qdrant before — NOT a per-task workload property.

    Fix: pay that cold cost once at process boot instead of inline during a
    task's window, using the exact same code path a real task hits
    (`get_knowledge_base().backend(namespace)` -> `_get_index` ->
    `_build_index` -> `_try_qdrant` -> `_QdrantIndex()` ->
    `_get_qdrant_client()`/`_get_qdrant_embedder()`), so this is a real warm-up
    of the real singleton, not a separate parallel code path. Bounded by its
    own daemon thread + join timeout so a genuinely broken Qdrant endpoint
    still lets the worker become ready (task-time fallback logic is
    unchanged and remains the safety net). Gated to worker_heavy only
    (default worker/scheduler never run this task, no reason to pay the
    cost) via the dedicated `CELERY_HEAVY_WORKER` process-role marker. The
    routing flag cannot identify the role because app, beat, and the default
    worker all need `CELERY_HEAVY_QUEUE=1` too."""
    if not _is_heavy_worker():
        return

    def _warm() -> None:
        try:
            from app.voice_agent.knowledge_base import get_knowledge_base

            t0 = time.monotonic()
            backend = get_knowledge_base().backend("solar_residential")
            logger.info(
                "[kb-warmup] worker_heavy Qdrant/fastembed warm-up done backend=%s duration_s=%.2f",
                backend,
                time.monotonic() - t0,
            )
        except Exception as e:
            logger.warning(
                "[kb-warmup] worker_heavy warm-up failed (non-fatal): %s", type(e).__name__
            )

    threading.Thread(target=_warm, name="kb-warmup-boot", daemon=True).start()


@signals.worker_ready.connect
def on_worker_ready(**kwargs):
    """Called when worker is ready to accept tasks"""
    logger.info("? Celery worker ready and accepting tasks")


@signals.worker_shutting_down.connect
def on_worker_shutdown(**kwargs):
    """Called when worker is shutting down"""
    logger.info("? Celery worker shutting down gracefully...")


@signals.task_prerun.connect
def on_task_prerun(task_id, task, args, kwargs, **kw):
    """Called before a task starts"""
    logger.debug(f"Starting task {task.name}[{task_id}]")


@signals.task_postrun.connect
def on_task_postrun(task_id, task, args, kwargs, retval, **kw):
    """Called after a task completes"""
    logger.debug(f"Completed task {task.name}[{task_id}]")


@signals.task_failure.connect
def on_task_failure(task_id, exception, args, kwargs, traceback, einfo, **kw):
    """Called when a task fails"""
    logger.error(f"Task failed: {task_id}, error: {exception}")

    # Send to Sentry if configured
    if settings.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.capture_exception(exception)
        except (ImportError, AttributeError) as _e:
            logger.debug("Sentry capture skipped: %s", _e)

    # Dead-letter recorder: failed task ka record Redis list me (inspection/replay).
    # Best-effort + bounded (last 1000). Redis down ho to silent skip.
    try:
        import json as _json
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        import redis as _redis

        _r = _redis.from_url(settings.redis_url, socket_timeout=2)
        _r.lpush(
            "dlq:failed_tasks",
            _json.dumps(
                {
                    "task_id": str(task_id),
                    "error": str(exception)[:500],
                    "args": str(args)[:400],
                    "kwargs": str(kwargs)[:400],
                    "ts": _dt.now(_tz.utc).isoformat(),
                }
            ),
        )
        _r.ltrim("dlq:failed_tasks", 0, 999)
    except (ImportError, ConnectionError, OSError, ValueError) as _e:
        logger.debug("DLQ record skipped: %s", _e)


@signals.task_retry.connect
def on_task_retry(request, reason, einfo, **kwargs):
    """Called when a task is retried"""
    logger.warning(f"Task {request.task} retrying: {reason}")


# Scheduled tasks
celery_app.conf.beat_schedule = {
    # Daily lead scraping (6 AM)
    "daily-lead-scraping": {
        "task": "app.tasks.scraping.scheduled_scrape",
        "schedule": crontab(hour=6, minute=0),
        "args": (),
    },
    # Hourly call queue processing
    "process-call-queue": {
        "task": "app.tasks.calling.process_queue",
        "schedule": crontab(minute=0),  # Every hour
        "args": (),
    },
    # Voice follow-up callbacks (trial day8/9 + interested-not-converted)
    "process-voice-followups": {
        "task": "app.tasks.calling.process_voice_followups",
        "schedule": crontab(minute=25),  # Every hour at :25 IST (celery TZ)
        "args": (20,),
    },
    # Daily report generation (8 PM)
    "daily-report": {
        "task": "app.tasks.reporting.generate_daily_report",
        "schedule": crontab(hour=20, minute=0),
        "args": (),
    },
    # Weekly report (Monday 9 AM)
    "weekly-report": {
        "task": "app.tasks.reporting.generate_weekly_report",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),
        "args": (),
    },
    # CRM sync every 15 minutes
    "crm-sync": {
        "task": "app.tasks.sync.sync_to_crm",
        "schedule": crontab(minute="*/15"),
        "args": (),
    },
    # Clean old logs (daily at midnight)
    "clean-logs": {
        "task": "app.tasks.reporting.clean_old_logs",
        "schedule": crontab(hour=0, minute=0),
        "args": (),
    },
    # ========================================
    # BRAIN TRAINING - Billionaire Mode
    # Continuous, automated brain improvement
    # ========================================
    # Train all brains every 6 hours
    "brain-training-all": {
        "task": "app.tasks.brain_training.train_all_brains",
        "schedule": crontab(hour="*/6", minute=30),  # Every 6 hours at :30
        "args": (),
    },
    # Continuous training health check (every hour)
    "brain-training-check": {
        "task": "app.tasks.brain_training.continuous_training_check",
        "schedule": crontab(minute=45),  # Every hour at :45
        "args": (),
    },
    # Deep web knowledge update (daily at 4 AM)
    "brain-web-knowledge": {
        "task": "app.tasks.brain_training.web_knowledge_update",
        "schedule": crontab(hour=4, minute=0),
        "args": (),
    },
    # Sub-Agent Brain training (every 6 hours, offset)
    "brain-sub-agent": {
        "task": "app.tasks.brain_training.train_brain",
        "schedule": crontab(hour="2,8,14,20", minute=0),
        "args": ("sub_agent", "scheduled"),
    },
    # Voice Agent Brain training (every 6 hours, offset)
    "brain-voice-agent": {
        "task": "app.tasks.brain_training.train_brain",
        "schedule": crontab(hour="2,8,14,20", minute=15),
        "args": ("voice_agent", "scheduled"),
    },
    # Production Brain training (every 6 hours, offset)
    "brain-production": {
        "task": "app.tasks.brain_training.train_brain",
        "schedule": crontab(hour="2,8,14,20", minute=30),
        "args": ("production", "scheduled"),
    },
    # ========================================
    # VERTEX AI PRODUCTION-READY TRAINING
    # Billionaire Mode - Maximum AI Leverage
    # ========================================
    # Vertex AI: Train all brains (every 4 hours for production readiness)
    "vertex-train-all": {
        "task": "app.tasks.brain_training.vertex_train_all",
        "schedule": crontab(hour="*/4", minute=0),  # Every 4 hours
        "args": (),
    },
    # Vertex AI: Continuous health check (every 15 minutes)
    "vertex-continuous-check": {
        "task": "app.tasks.brain_training.vertex_continuous_check",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
        "args": (),
    },
    # Vertex AI: Knowledge update (twice daily)
    "vertex-knowledge-update": {
        "task": "app.tasks.brain_training.vertex_knowledge_update",
        "schedule": crontab(hour="4,16", minute=30),  # 4:30 AM and 4:30 PM
        "args": (),
    },
    # ========================================
    # AI-STAFF JOBS (durable path) — mirrors team_scheduler.py IST cadence.
    # DORMANT unless `celery beat` runs (compose --profile celery). On default
    # deployment the in-process APScheduler still owns these. Switch = set
    # RUN_IN_PROCESS_SCHEDULER=0 + run celery beat (no double-run). Timezone here
    # is Asia/Kolkata (celery_app.conf.timezone) so hours below are IST.
    # ========================================
    "staff-growth-15min": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute="*/15"),
        "args": ("growth",),
    },
    "staff-ops-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=5),
        "args": ("ops",),
    },
    "staff-reply-triage-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=20),
        "args": ("reply_triage",),
    },
    "staff-watchdog-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=35),
        "args": ("watchdog",),
    },
    "staff-onboard-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=50),
        "args": ("onboard",),
    },
    "staff-obsidian-push-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=2, minute=15),
        "args": ("obsidian_push",),
    },
    "staff-call-kpi-digest-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=19, minute=30),
        "args": ("call_kpi_digest",),
    },
    "staff-flow-cron": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute="*/5"),
        "args": ("flow_cron",),
    },
    "staff-qa-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=2, minute=30),
        "args": ("qa",),
    },
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
        "schedule": crontab(hour=9, minute=0),
        "args": ("engineer_finops",),
    },
    "staff-engineer-security-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=30),
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
    "staff-readiness-digest-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=30),
        "args": ("readiness_digest",),
    },
    "staff-pipeline-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=11, minute=0),
        "args": ("pipeline",),
    },
    "staff-email-followup-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour="9,10,11,12,13,14,15,16,17,18,19", minute=20),
        "args": ("email_followup",),
    },
    "staff-kb-refresh-weekly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=5, minute=0, day_of_week=0),
        "args": ("kb_refresh",),
    },
    "staff-platform-dial-daily": {
        # 11:30 IST: self-sale AI cold-call batch — job body no-ops unless
        # PLATFORM_DIAL_DAILY=1 (TRAI window/DND gates live inside the call path).
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=11, minute=30),
        "args": ("platform_dial",),
    },
    "staff-daily-video-daily": {
        # 09:45 IST: per-client DAILY video producer. Deliberately NOT inside the
        # `content` mega-job — that chain runs auto_content first under
        # CONTENT_TIME_BUDGET_S and silently skipped video_ad_cycle for 15 days
        # in prod (see app/marketing/daily_video.py docstring). This job only
        # ENQUEUES to the video queue; job body no-ops unless DAILY_VIDEO_ENABLED=1.
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=9, minute=45),
        "args": ("daily_video",),
    },
    "staff-midday-prospect-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=14, minute=30),
        "args": ("midday_prospect",),
    },
    "staff-afternoon-content-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=15, minute=0),
        "args": ("afternoon_content",),
    },
    "staff-evening-prospect-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=17, minute=0),
        "args": ("evening_prospect",),
    },
    "staff-evening-wrap-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=18, minute=30),
        "args": ("evening_wrap",),
    },
    "staff-weekly-marketing": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=12, minute=30, day_of_week=2),
        "args": ("weekly_marketing",),
    },
    "staff-saturday-hygiene": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=4, minute=0, day_of_week=5),
        "args": ("saturday_hygiene",),
    },
    # Parallel automation batch 2026-06-19 (jobs no-op until their flag is ON)
    "staff-meter-watch-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=55),
        "args": ("meter_watch",),
    },
    # Product 1 Customer Deliverability layer (2026-07-08): Customer Health +
    # Approval Reminder + SLA Recovery sweep. Light/read-mostly — stays on the
    # default queue like "onboard" (whose hourly sweep already calls the same
    # auto_content.seed_client_content() directly, also NOT in HEAVY_STAFF_JOBS)
    # so the health/reminder signal is never delayed behind the heavy content
    # queue. The rare recovery path (paid customer, zero content, 24h+) follows
    # that same existing precedent rather than introducing a new routing rule.
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
}

# ---------------------------------------------------------------------------
# SAFETY GATE: legacy (Cloud-Run/Vertex era) beat entries DEFAULT OFF.
# Bina GCP/Vertex creds ke ye tasks heavy/no-op hain, aur `process_queue`
# jaise entries call-side-effects rakh sakte. Celery-beat switch ka core =
# sirf `staff-*` jobs (team_scheduler._run_job dispatcher — saare naye
# engines included). Puraane entries chahiye to ENABLE_LEGACY_BEAT=1.
# ---------------------------------------------------------------------------
if os.environ.get("ENABLE_LEGACY_BEAT", "0").strip().lower() not in ("1", "true", "yes"):
    celery_app.conf.beat_schedule = {
        k: v for k, v in celery_app.conf.beat_schedule.items() if k.startswith("staff-")
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
