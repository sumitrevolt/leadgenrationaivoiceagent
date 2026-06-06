"""Automation Package"""
from app.automation.campaign_manager import CampaignManager
from app.automation.scheduler import CallScheduler
from app.automation.orchestrator_pipeline import LeadGenPipeline, CampaignResult
from app.automation.agent_pool import (
    AgentWorkerPool,
    CampaignSpec,
    AgentInfo,
    AgentStatus,
)

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
