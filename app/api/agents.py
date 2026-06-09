"""
Agents API — LangGraph supervisor endpoints.

POST /agents/run    (admin) — route a task through the supervisor graph
GET  /agents/status          — engine availability + node list

Returns HTTP 501 when the langgraph engine is not installed (graceful path).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents import coordinator
from app.agents.supervisor import AGENTS_AVAILABLE, GRAPH_NODES, run_supervisor_task
from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentRunRequest(BaseModel):
    """Task to route through the supervisor graph."""

    task: str = Field(..., min_length=3, max_length=2000, description="What the agent should do")
    client_id: str | None = Field(None, description="Client ID (uses client KB namespace)")
    niche: str | None = Field("general", description="Niche key or loose name (e.g. 'solar')")


@router.post("/run")
async def run_agent_task(
    request: AgentRunRequest,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Route a task to the data/leads agent via the rule-based supervisor."""
    if not AGENTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="agents engine not installed")
    try:
        return await run_supervisor_task(
            task=request.task,
            client_id=request.client_id,
            niche=request.niche or "general",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"Agent run failed: {e}")
        raise HTTPException(status_code=500, detail="agent run failed")


@router.get("/status")
async def agents_status() -> dict[str, Any]:
    """Engine availability — safe to call without auth (no secrets exposed)."""
    return {
        "available": AGENTS_AVAILABLE,
        "engine": "langgraph-supervisor",
        "nodes": GRAPH_NODES,
    }


# ============================================================================
# Multi-agent COORDINATOR — free-stack coordination over the STAFF roster.
# plan -> sequential handoff (shared blackboard) | parallel fan-out -> aggregate.
# Always available (no langgraph dep). SAFE default (execute=False = drafts only).
# ============================================================================
class CoordinateRequest(BaseModel):
    """High-level goal for the agent team to coordinate on."""

    goal: str = Field(..., min_length=3, max_length=2000)
    execute: bool = Field(
        False, description="True = agents ki SAFE capabilities bhi chalao (warna sirf drafts)"
    )
    max_steps: int = Field(5, ge=1, le=8)


class FanOutRequest(BaseModel):
    """Goal to fan out to multiple agents in parallel."""

    goal: str = Field(..., min_length=3, max_length=2000)
    agents: list[str] | None = Field(None, description="STAFF keys; default dev/rohan/isha/kavya")


@router.get("/roster")
async def agents_roster() -> dict[str, Any]:
    """STAFF roster + executable-capability flag + recent coordination runs (no secrets)."""
    return {"roster": coordinator.roster(), "recent_runs": coordinator.recent_runs(10)}


@router.post("/coordinate", dependencies=[Depends(rate_limit("agents", 15, 60))])
async def coordinate_agents(
    req: CoordinateRequest, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Decompose a goal -> assign STAFF agents -> sequential handoff (shared blackboard) -> Boss aggregate."""
    return await coordinator.coordinate(req.goal, execute=req.execute, max_steps=req.max_steps)


@router.post("/fanout", dependencies=[Depends(rate_limit("agents", 15, 60))])
async def fanout_agents(req: FanOutRequest, user: User = Depends(require_admin)) -> dict[str, Any]:
    """Parallel coordination — multiple agents work the same goal at once, then aggregate."""
    return await coordinator.fan_out(req.goal, agents=req.agents)


# ============================================================================
# ADVANCED orchestration (2026 SOTA): Reflexion loop (plan→execute→verify→reflect→retry)
# + episodic memory + critic, and debate/consensus. Free-stack, admin + rate-limited.
# ============================================================================
class AdvancedRequest(BaseModel):
    """Goal for the Reflexion-style self-correcting agent team."""

    goal: str = Field(..., min_length=3, max_length=2000)
    max_iterations: int = Field(2, ge=1, le=3, description="Reflexion retries (critic<quality_bar pe)")
    quality_bar: float = Field(0.7, ge=0.0, le=1.0, description="Early-stop score threshold")
    execute: bool = Field(False, description="True = agents ki SAFE capabilities bhi chalao")
    max_steps: int = Field(4, ge=1, le=8)


class DebateRequest(BaseModel):
    """A proposal/decision for pro-vs-con debate + Boss verdict."""

    question: str = Field(..., min_length=3, max_length=2000)
    rounds: int = Field(1, ge=1, le=2)


@router.post("/coordinate-advanced", dependencies=[Depends(rate_limit("agents", 10, 60))])
async def coordinate_advanced_agents(
    req: AdvancedRequest, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Reflexion orchestration: plan → execute (handoff) → critic verify → reflect + retry → aggregate.
    Episodic memory recall/persist + guardrails (max_iterations, quality_bar)."""
    return await coordinator.coordinate_advanced(
        req.goal,
        max_iterations=req.max_iterations,
        quality_bar=req.quality_bar,
        execute=req.execute,
        max_steps=req.max_steps,
    )


@router.post("/debate", dependencies=[Depends(rate_limit("agents", 10, 60))])
async def debate_agents(req: DebateRequest, user: User = Depends(require_admin)) -> dict[str, Any]:
    """Consensus pattern — pro vs con agents argue, Boss judges with a clear verdict."""
    return await coordinator.debate(req.question, rounds=req.rounds)


@router.get("/memory")
async def agents_memory(limit: int = 30, user: User = Depends(require_admin)) -> dict[str, Any]:
    """Recent episodic agent memory (Reflexion reflections + scores)."""
    return {"memory": coordinator.memory_log(limit=limit)}


class HierRequest(BaseModel):
    """Goal for hierarchical (Boss → sub-teams → members) orchestration."""

    goal: str = Field(..., min_length=3, max_length=2000)
    execute: bool = Field(False, description="True = agents ki SAFE capabilities bhi chalao")


@router.post("/coordinate-hierarchical", dependencies=[Depends(rate_limit("agents", 10, 60))])
async def coordinate_hierarchical_agents(
    req: HierRequest, user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Hierarchical: Boss -> domain sub-teams (growth/ops/sales, PARALLEL) -> members -> unified merge."""
    return await coordinator.coordinate_hierarchical(req.goal, execute=req.execute)
