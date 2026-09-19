"""9 Specialized Worker Bots with TypeSafe skills registry.

Each worker bot has a specific role and skill set for enterprise automation.
Type-safe through Pydantic models and structured task definitions.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class WorkerRole(str, Enum):
    """9 specialized worker roles."""
    DATA_ANALYST = "data_analyst"
    CONTENT_CREATOR = "content_creator"
    LEAD_GENERATOR = "lead_generator"
    QUALITY_ASSURANCE = "quality_assurance"
    EMAIL_SPECIALIST = "email_specialist"
    SOCIAL_MEDIA = "social_media"
    VOICE_AGENT = "voice_agent"
    CRM_MANAGER = "crm_manager"
    REPORTING = "reporting"


class SkillTypeDef(BaseModel):
    """Type-safe skill definition."""
    name: str
    description: str
    parameters: dict[str, Any]
    output_schema: dict[str, Any]
    timeout_seconds: int = 300
    retry_count: int = 3


class WorkerTask(BaseModel):
    """Task definition for worker bots."""
    task_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    worker_id: str
    role: WorkerRole
    skill_name: str
    input_data: dict[str, Any]
    status: str = "pending"
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class WorkerBot:
    """Base worker bot with common functionality."""
    
    def __init__(self, worker_id: str, role: WorkerRole, name: str):
        self.worker_id = worker_id
        self.role = role
        self.name = name
        self.tasks: list[WorkerTask] = []
        self.skills: dict[str, SkillTypeDef] = {}
    
    def register_skill(self, skill: SkillTypeDef) -> None:
        """Register a type-safe skill."""
        self.skills[skill.name] = skill
    
    def create_task(self, skill_name: str, input_data: dict[str, Any]) -> WorkerTask:
        """Create a new task for this worker."""
        if skill_name not in self.skills:
            raise ValueError(f"Skill '{skill_name}' not registered for {self.name}")
        
        task = WorkerTask(
            worker_id=self.worker_id,
            role=self.role,
            skill_name=skill_name,
            input_data=input_data,
        )
        self.tasks.append(task)
        return task
    
    def execute_task(self, task: WorkerTask) -> WorkerTask:
        """Execute a task (override in subclasses)."""
        now_iso = datetime.now(timezone.utc).isoformat()
        task.status = "completed"
        task.started_at = now_iso
        task.completed_at = now_iso
        task.result = {"status": "ok"}
        return task


# ============================================================================
# 9 WORKER BOT IMPLEMENTATIONS
# ============================================================================

class DataAnalystWorker(WorkerBot):
    """Worker for data analysis tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_data_analyst",
            role=WorkerRole.DATA_ANALYST,
            name="Data Analyst Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        """Register default skills for data analysis."""
        self.register_skill(SkillTypeDef(
            name="analyze_prospects",
            description="Analyze prospect data for insights",
            parameters={"dataset": "list", "filters": "dict"},
            output_schema={"insights": "list", "summary": "dict"},
        ))
        self.register_skill(SkillTypeDef(
            name="score_leads",
            description="Score leads based on criteria",
            parameters={"leads": "list", "criteria": "dict"},
            output_schema={"scored_leads": "list"},
        ))
        self.register_skill(SkillTypeDef(
            name="generate_report",
            description="Generate analytics report",
            parameters={"report_type": "str", "data": "dict"},
            output_schema={"report": "dict", "charts": "list"},
        ))


class ContentCreatorWorker(WorkerBot):
    """Worker for content creation tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_content_creator",
            role=WorkerRole.CONTENT_CREATOR,
            name="Content Creator Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="create_social_post",
            description="Create social media post",
            parameters={"niche": "str", "topic": "str"},
            output_schema={"caption": "str", "hashtags": "list"},
        ))
        self.register_skill(SkillTypeDef(
            name="generate_email",
            description="Generate email content",
            parameters={"subject": "str", "context": "str"},
            output_schema={"body": "str", "subject": "str"},
        ))


class LeadGeneratorWorker(WorkerBot):
    """Worker for lead generation tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_lead_generator",
            role=WorkerRole.LEAD_GENERATOR,
            name="Lead Generator Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="harvest_prospects",
            description="Harvest prospects from sources",
            parameters={"source": "str", "criteria": "dict"},
            output_schema={"prospects": "list", "count": "int"},
        ))
        self.register_skill(SkillTypeDef(
            name="enrich_lead",
            description="Enrich lead data",
            parameters={"lead": "dict"},
            output_schema={"enriched_lead": "dict"},
        ))


class QualityAssuranceWorker(WorkerBot):
    """Worker for QA and validation tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_qa",
            role=WorkerRole.QUALITY_ASSURANCE,
            name="QA Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="validate_content",
            description="Validate content quality",
            parameters={"content": "str", "rules": "list"},
            output_schema={"valid": "bool", "issues": "list"},
        ))
        self.register_skill(SkillTypeDef(
            name="check_compliance",
            description="Check TRAI/DLP compliance",
            parameters={"campaign": "dict"},
            output_schema={"compliant": "bool", "violations": "list"},
        ))


class EmailSpecialistWorker(WorkerBot):
    """Worker for email automation tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_email",
            role=WorkerRole.EMAIL_SPECIALIST,
            name="Email Specialist Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="send_cold_email",
            description="Send cold outreach email",
            parameters={"recipient": "str", "template": "str"},
            output_schema={"sent": "bool", "message_id": "str"},
        ))
        self.register_skill(SkillTypeDef(
            name="track_email",
            description="Track email opens/clicks",
            parameters={"campaign_id": "str"},
            output_schema={"opens": "int", "clicks": "int"},
        ))


class SocialMediaWorker(WorkerBot):
    """Worker for social media tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_social",
            role=WorkerRole.SOCIAL_MEDIA,
            name="Social Media Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="schedule_post",
            description="Schedule social media post",
            parameters={"platform": "str", "content": "str", "time": "str"},
            output_schema={"scheduled": "bool", "post_id": "str"},
        ))
        self.register_skill(SkillTypeDef(
            name="analyze_engagement",
            description="Analyze social engagement",
            parameters={"post_id": "str"},
            output_schema={"likes": "int", "shares": "int", "comments": "int"},
        ))


class VoiceAgentWorker(WorkerBot):
    """Worker for voice/calling tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_voice",
            role=WorkerRole.VOICE_AGENT,
            name="Voice Agent Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="make_call",
            description="Make AI voice call",
            parameters={"phone": "str", "script": "str"},
            output_schema={"call_id": "str", "duration": "int"},
        ))
        self.register_skill(SkillTypeDef(
            name="process_call_recording",
            description="Process call recording",
            parameters={"recording_id": "str"},
            output_schema={"transcript": "str", "sentiment": "str"},
        ))


class CRMManagerWorker(WorkerBot):
    """Worker for CRM management tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_crm",
            role=WorkerRole.CRM_MANAGER,
            name="CRM Manager Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="sync_leads",
            description="Sync leads to CRM",
            parameters={"leads": "list", "crm_provider": "str"},
            output_schema={"synced": "int", "errors": "list"},
        ))
        self.register_skill(SkillTypeDef(
            name="update_lead_status",
            description="Update lead status in CRM",
            parameters={"lead_id": "str", "status": "str"},
            output_schema={"updated": "bool"},
        ))


class ReportingWorker(WorkerBot):
    """Worker for reporting tasks."""
    
    def __init__(self):
        super().__init__(
            worker_id="worker_reporting",
            role=WorkerRole.REPORTING,
            name="Reporting Bot",
        )
        self._register_default_skills()
    
    def _register_default_skills(self):
        self.register_skill(SkillTypeDef(
            name="generate_daily_report",
            description="Generate daily performance report",
            parameters={"date": "str", "metrics": "list"},
            output_schema={"report": "dict", "charts": "list"},
        ))
        self.register_skill(SkillTypeDef(
            name="export_csv",
            description="Export data to CSV",
            parameters={"data": "list", "filename": "str"},
            output_schema={"path": "str", "rows": "int"},
        ))


# ============================================================================
# WORKER MANAGER
# ============================================================================

class WorkerManager:
    """Manage all 9 worker bots."""
    
    def __init__(self):
        self.workers: dict[str, WorkerBot] = {}
        self._initialize_workers()
    
    def _initialize_workers(self):
        """Initialize all 9 worker bots."""
        workers = [
            DataAnalystWorker(),
            ContentCreatorWorker(),
            LeadGeneratorWorker(),
            QualityAssuranceWorker(),
            EmailSpecialistWorker(),
            SocialMediaWorker(),
            VoiceAgentWorker(),
            CRMManagerWorker(),
            ReportingWorker(),
        ]
        for worker in workers:
            self.workers[worker.worker_id] = worker
    
    def get_worker(self, worker_id: str) -> Optional[WorkerBot]:
        """Get worker by ID."""
        return self.workers.get(worker_id)
    
    def list_workers(self) -> list[dict[str, Any]]:
        """List all workers with their skills."""
        result = []
        for worker in self.workers.values():
            result.append({
                "worker_id": worker.worker_id,
                "name": worker.name,
                "role": worker.role.value,
                "skills": list(worker.skills.keys()),
                "active_tasks": len([t for t in worker.tasks if t.status == "running"]),
            })
        return result
    
    def execute_task(self, worker_id: str, skill_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
        """Execute a task on a worker."""
        worker = self.get_worker(worker_id)
        if not worker:
            return {"error": f"Worker {worker_id} not found"}
        
        task = worker.create_task(skill_name, input_data)
        task = worker.execute_task(task)
        
        return {
            "success": not bool(task.error) and task.status == "completed",
            "task_id": task.task_id,
            "worker_id": task.worker_id,
            "status": task.status,
            "skill": task.skill_name,
            "result": task.result,
        }


# Module-level singleton
_workers_manager: Optional[WorkerManager] = None


def get_workers_manager() -> WorkerManager:
    """Get or create singleton WorkerManager."""
    global _workers_manager
    if _workers_manager is None:
        _workers_manager = WorkerManager()
    return _workers_manager


def list_workers() -> list[dict[str, Any]]:
    """Convenience function to list workers."""
    return get_workers_manager().list_workers()


def execute_task(worker_id: str, skill_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Convenience function to execute task."""
    return get_workers_manager().execute_task(worker_id, skill_name, input_data)
