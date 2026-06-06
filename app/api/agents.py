"""
Agents API — LangGraph supervisor endpoints.

POST /agents/run    (admin) — route a task through the supervisor graph
GET  /agents/status          — engine availability + node list

Returns HTTP 501 when the langgraph engine is not installed (graceful path).
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.supervisor import AGENTS_AVAILABLE, GRAPH_NODES, run_supervisor_task
from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/agents", tags=["Agents"])


class AgentRunRequest(BaseModel):
    """Task to route through the supervisor graph."""
    task: str = Field(..., min_length=3, max_length=2000, description="What the agent should do")
    client_id: Optional[str] = Field(None, description="Client ID (uses client KB namespace)")
    niche: Optional[str] = Field("general", description="Niche key or loose name (e.g. 'solar')")


@router.post("/run")
async def run_agent_task(
    request: AgentRunRequest,
    user: User = Depends(require_admin),
) -> Dict[str, Any]:
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
async def agents_status() -> Dict[str, Any]:
    """Engine availability — safe to call without auth (no secrets exposed)."""
    return {
        "available": AGENTS_AVAILABLE,
        "engine": "langgraph-supervisor",
        "nodes": GRAPH_NODES,
    }
