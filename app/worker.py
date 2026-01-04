"""
Celery Worker Configuration
Production-ready background task processing
"""
from celery import Celery, signals
from celery.schedules import crontab
import os
import sys
import logging

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
    ]
)

# Production-ready configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone
    timezone="Asia/Kolkata",
    enable_utc=True,
    
    # Task routing by queue
    task_routes={
        "app.tasks.scraping.*": {"queue": "scraping"},
        "app.tasks.calling.*": {"queue": "calling"},
        "app.tasks.reporting.*": {"queue": "reporting"},
        "app.tasks.sync.*": {"queue": "sync"},
        "app.tasks.brain_training.*": {"queue": "training"},
    },
    
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
    
    # Result backend settings
    result_expires=86400,  # 24 hours
    result_extended=True,  # Store task metadata
    
    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetch for fair scheduling
    worker_max_tasks_per_child=1000,  # Restart worker after N tasks (memory leaks)
    worker_max_memory_per_child=512000,  # 512MB memory limit
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
    
    # Retry policy for broker connection
    broker_connection_retry_on_startup=True,
    
    # Event monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
)

# ============================================
# Celery Signals for Production Monitoring
# ============================================

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
        except Exception:
            pass


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
