"""
Celery Worker Configuration
Background task processing
"""
from celery import Celery
from celery.schedules import crontab

from app.config import settings

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

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    
    # Task routing
    task_routes={
        "app.tasks.scraping.*": {"queue": "scraping"},
        "app.tasks.calling.*": {"queue": "calling"},
        "app.tasks.reporting.*": {"queue": "reporting"},
        "app.tasks.sync.*": {"queue": "sync"},
    },
    
    # Rate limits
    task_annotations={
        "app.tasks.calling.make_call": {"rate_limit": "20/m"},
        "app.tasks.scraping.scrape_leads": {"rate_limit": "5/m"},
    },
    
    # Retry policy
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Result expiration
    result_expires=86400,  # 24 hours
)

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
