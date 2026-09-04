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
        "app.tasks.whatsapp_automation",  # 1-click human WA queue drain (GATED: WHATSAPP_AUTO_SEND=1; cold bulk = ban)
        "app.tasks.daily_social_post",  # 3x daily branded social posting via Postiz (GATED: POSTIZ_API_KEY + VIDEO_AD_CYCLE=1)
        "app.tasks.video_generator",  # Creative video render helper for daily_social_post
    ],
)

# ============================================
# Celery Signals for Production Monitoring


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
    "staff-readiness-digest-daily": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(hour=8, minute=35),
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

    # System heartbeat (main-line 2026-09: 5-min liveness tick into staff_jobs).
    "staff-heartbeat-5m": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute="*/5"),
        "args": ("heartbeat",),
    },
    # Content-approval notifications — gated CONTENT_APPROVAL_NOTIFY
    # INERT flag = run_staff_job no-op; no duplicate route/page.
    "staff-content-approval-notify-hourly": {
        "task": "app.tasks.staff_jobs.run_staff_job",
        "schedule": crontab(minute=35),
        "args": ("content_approval_notify",),
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
