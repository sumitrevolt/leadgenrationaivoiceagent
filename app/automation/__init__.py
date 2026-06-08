"""Automation Package"""

from app.automation.agent_pool import (
    AgentInfo,
    AgentStatus,
    AgentWorkerPool,
    CampaignSpec,
)
from app.automation.campaign_manager import CampaignManager
from app.automation.orchestrator_pipeline import CampaignResult, LeadGenPipeline
from app.automation.scheduler import CallScheduler

__all__ = [
    "CampaignManager",
    "CallScheduler",
    "LeadGenPipeline",
    "CampaignResult",
    "AgentWorkerPool",
    "CampaignSpec",
    "AgentInfo",
    "AgentStatus",
]
