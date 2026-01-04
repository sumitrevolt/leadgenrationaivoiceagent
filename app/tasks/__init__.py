"""Background Tasks Package

This module exports all Celery tasks for the LeadGen AI Voice Agent.
Tasks are organized by domain:
- brain_training: Continuous AI brain training automation
- calling: Voice call tasks
- reporting: Analytics and reporting tasks
- scraping: Lead scraping tasks
- sync: CRM and integration sync tasks
"""

from app.tasks.brain_training import (
    train_all_brains,
    train_brain,
    continuous_training_check,
    web_knowledge_update,
    get_training_status,
    record_feedback,
)

__all__ = [
    # Brain Training Tasks
    "train_all_brains",
    "train_brain",
    "continuous_training_check",
    "web_knowledge_update",
    "get_training_status",
    "record_feedback",
]
