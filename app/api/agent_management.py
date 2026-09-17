"""FastAPI Endpoints for Agent Management.

Provides REST API for:
- Worker bot management
- Agent bot management
- Skill registry operations
- Performance tracking
- Self-improvement loop control
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agents"])


# ============================================================================
# WORKER BOT ENDPOINTS
# ============================================================================

class WorkerListResponse(BaseModel):
    workers: list[dict[str, Any]]


class WorkerExecuteRequest(BaseModel):
    worker_id: str
    skill_name: str
    input_data: dict[str, Any]


class WorkerExecuteResponse(BaseModel):
    success: bool
    task_id: Optional[str] = None
    status: Optional[str] = None
    error: Optional[str] = None


@router.get("/workers")
async def list_workers(_user=Depends(require_admin)) -> WorkerListResponse:
    """List all 9 worker bots with their skills."""
    from app.agents.workers import list_workers
    return WorkerListResponse(workers=list_workers())


@router.post("/workers/execute")
async def execute_worker_task(
    request: WorkerExecuteRequest,
    _user=Depends(require_admin),
) -> WorkerExecuteResponse:
    """Execute a task on a worker bot."""
    from app.agents.workers import execute_task
    
    result = execute_task(request.worker_id, request.skill_name, request.input_data)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return WorkerExecuteResponse(
        success=result.get("success", True),
        task_id=result.get("task_id"),
        status=result.get("status"),
    )


# ============================================================================
# AGENT BOT ENDPOINTS
# ============================================================================

class AgentListResponse(BaseModel):
    agents: list[dict[str, Any]]
    total: int


class AgentStatsResponse(BaseModel):
    agent_id: str
    name: str
    role: str
    product: str
    status: str
    skills: list[str]
    tasks_completed_today: int
    tasks_completed_total: int


class DailySummaryResponse(BaseModel):
    date: str
    total_agents: int
    active_agents: int
    total_tasks_today: int
    total_tasks_all: int
    breakdown: dict[str, Any]


@router.get("/agents")
async def list_agents(
    product: Optional[str] = None,
    _user=Depends(require_admin),
) -> AgentListResponse:
    """List all 31 agent bots."""
    from app.agents.agents import list_agents
    
    agents = list_agents(product)
    return AgentListResponse(agents=agents, total=len(agents))


@router.get("/agents/{agent_id}/stats")
async def get_agent_stats(
    agent_id: str,
    _user=Depends(require_admin),
) -> AgentStatsResponse:
    """Get detailed stats for an agent."""
    from app.agents.agents import get_agent_manager
    
    manager = get_agent_manager()
    agent = manager.get_agent(agent_id)
    
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    
    return AgentStatsResponse(
        agent_id=agent.agent_id,
        name=agent.name,
        role=agent.role,
        product=agent.product,
        status=agent.status,
        skills=agent.skills,
        tasks_completed_today=agent.tasks_completed_today,
        tasks_completed_total=agent.tasks_completed_total,
    )


@router.get("/agents/summary")
async def get_daily_summary(_user=Depends(require_admin)) -> DailySummaryResponse:
    """Get daily summary of all agent activity."""
    from app.agents.agents import daily_summary
    
    summary = daily_summary()
    return DailySummaryResponse(**summary)


@router.post("/agents/{agent_id}/activate")
async def activate_agent(
    agent_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Activate an agent."""
    from app.agents.agents import get_agent_manager
    
    manager = get_agent_manager()
    result = manager.activate_agent(agent_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.post("/agents/{agent_id}/pause")
async def pause_agent(
    agent_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Pause an agent."""
    from app.agents.agents import get_agent_manager
    
    manager = get_agent_manager()
    result = manager.pause_agent(agent_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


# ============================================================================
# SKILL REGISTRY ENDPOINTS
# ============================================================================

class SkillListResponse(BaseModel):
    skills: list[dict[str, Any]]
    total: int


class SkillExecuteRequest(BaseModel):
    skill_name: str
    executor_id: str
    input_data: dict[str, Any]


class SkillExecuteResponse(BaseModel):
    success: bool
    execution: Optional[dict[str, Any]] = None
    error: Optional[str] = None


@router.get("/skills")
async def list_skills(
    category: Optional[str] = None,
    _user=Depends(require_admin),
) -> SkillListResponse:
    """List all registered skills."""
    from app.agents.skills import list_skills
    from app.agents.skills import SkillCategory
    
    category_enum = None
    if category:
        try:
            category_enum = SkillCategory(category)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
    
    skills = list_skills(category_enum)
    return SkillListResponse(skills=skills, total=len(skills))


@router.post("/skills/execute")
async def execute_skill(
    request: SkillExecuteRequest,
    _user=Depends(require_admin),
) -> SkillExecuteResponse:
    """Execute a skill."""
    from app.agents.skills import execute_skill
    
    result = execute_skill(request.skill_name, request.executor_id, request.input_data)
    
    if "error" in result:
        return SkillExecuteResponse(success=False, error=result["error"])
    
    return SkillExecuteResponse(
        success=result.get("success", True),
        execution=result.get("execution"),
    )


@router.get("/skills/{skill_name}/stats")
async def get_skill_stats(
    skill_name: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Get statistics for a skill."""
    from app.agents.skills import get_skill_stats
    
    return get_skill_stats(skill_name)


@router.get("/skills/registry/summary")
async def get_registry_summary(_user=Depends(require_admin)) -> dict[str, Any]:
    """Get skill registry summary."""
    from app.agents.skills import get_skill_registry
    
    return get_skill_registry().get_registry_summary()


# ============================================================================
# SELF-IMPROVEMENT ENDPOINTS
# ============================================================================

class LoopStatusResponse(BaseModel):
    loop_enabled: bool
    total_feedback_records: int
    today_feedback: int
    total_proposals: int
    today_proposals: int
    pending_proposals: int
    approved_proposals: int
    quality_threshold: float
    auto_approve_threshold: float


class ToggleLoopRequest(BaseModel):
    enabled: bool


class FeedbackRecordRequest(BaseModel):
    task_id: str
    agent_id: str
    skill_name: str
    input_data: dict[str, Any]
    success: bool = True
    quality_score: Optional[float] = None
    duration_seconds: Optional[float] = None
    feedback_text: Optional[str] = None


@router.get("/improve/status")
async def get_loop_status(_user=Depends(require_admin)) -> LoopStatusResponse:
    """Get self-improvement loop status."""
    from app.feedback.loop import get_loop_status
    
    status = get_loop_status()
    return LoopStatusResponse(**status)


@router.post("/improve/toggle")
async def toggle_loop(
    request: ToggleLoopRequest,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Enable or disable self-improvement loop."""
    from app.feedback.loop import toggle_loop
    
    return toggle_loop(request.enabled)


@router.post("/improve/feedback")
async def record_feedback(
    request: FeedbackRecordRequest,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Record feedback for a task."""
    from app.feedback.loop import record_feedback
    
    result = record_feedback(
        task_id=request.task_id,
        agent_id=request.agent_id,
        skill_name=request.skill_name,
        input_data=request.input_data,
        success=request.success,
        quality_score=request.quality_score,
        duration_seconds=request.duration_seconds,
        feedback_text=request.feedback_text,
    )
    
    return {"success": True, "feedback_id": result.task_id}


@router.get("/improve/proposals")
async def get_proposals(
    agent_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    _user=Depends(require_admin),
) -> list[dict[str, Any]]:
    """Get improvement proposals."""
    from app.feedback.loop import get_loop
    
    return get_loop().get_proposals(agent_id, status, limit)


@router.post("/improve/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Approve an improvement proposal."""
    from app.feedback.loop import get_loop
    
    return get_loop().approve_proposal(proposal_id, approved_by=_user.email if hasattr(_user, 'email') else 'admin')


@router.post("/improve/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Reject an improvement proposal."""
    from app.feedback.loop import get_loop
    
    return get_loop().reject_proposal(proposal_id)


@router.get("/improve/performance/{agent_id}")
async def get_performance(
    agent_id: str,
    skill_name: Optional[str] = None,
    _user=Depends(require_admin),
) -> list[dict[str, Any]]:
    """Get performance metrics for an agent."""
    from app.feedback.loop import get_performance
    
    return get_performance(agent_id, skill_name)


@router.get("/improve/performance/all")
async def get_all_performance(_user=Depends(require_admin)) -> list[dict[str, Any]]:
    """Get all agent performance metrics."""
    from app.feedback.loop import get_loop
    
    return get_loop().get_all_performance()
