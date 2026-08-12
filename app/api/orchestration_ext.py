"""Orchestration-ext endpoints — agent consensus (N-voter quorum) + trajectory
learning (record / best / replay-hint / dataset export).

Standalone admin router — coordinator se ALAG. Main session ise optionally
/api/agents-ext prefix pe mount karega (yahan mount NAHI hota). Saare modules
lazy-import hote handlers ke andar (import-safe, web process light). Routes
require_admin (export = super_admin, kyunki yeh disk pe training-file likhta).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["OrchestrationExt"])


# ----------------------------- Consensus (N-voter quorum) ------------------- #
class ConsensusIn(BaseModel):
    question: str
    options: list[str]
    voters: int = 3


@router.post("/consensus")
async def consensus_vote(body: ConsensusIn, _user=Depends(require_admin)):
    """N-voter quorum decision — har voter alag persona/temperature pe ek option
    chunta, votes tally → winner + confidence + quorum. options<2 → error,
    voter LLM fail → abstain. Never raises."""
    from app.agents import agent_consensus

    return await agent_consensus.vote(body.question, body.options, body.voters)


# ----------------------------- Trajectory learning -------------------------- #
@router.get("/trajectories")
async def trajectories_best(action: str, k: int = 3, _user=Depends(require_admin)):
    """Us action ke top-k winning traces (reward desc, fir recency)."""
    from app.agents import trajectory

    hits = trajectory.best_trajectories(action, k=k)
    return {
        "ok": True,
        "action": action,
        "grounding_enabled": trajectory.enabled(),
        "count": len(hits),
        "trajectories": hits,
    }


class TrajectoryRecordIn(BaseModel):
    action: str
    steps: list[dict] = []
    outcome: str = ""
    reward: float = 0.0
    meta: dict | None = None


@router.post("/trajectory/record")
async def trajectory_record(body: TrajectoryRecordIn, _user=Depends(require_admin)):
    """Ek pura agent-run trace record karo → data/agent_trajectories.jsonl."""
    from app.agents import trajectory

    tid = trajectory.record_trajectory(
        body.action, body.steps, body.outcome, body.reward, body.meta
    )
    return {"ok": bool(tid), "id": tid}


class TrajectoryExportIn(BaseModel):
    min_reward: float = 0.5


@router.post("/trajectory/export")
async def trajectory_export(body: TrajectoryExportIn, _user=Depends(require_super_admin)):
    """Winning traces ko JSONL training-dataset me export karo (local ML fine-tune).
    Disk-write → SUPER_ADMIN only (RBAC design)."""
    from app.agents import trajectory

    return trajectory.export_dataset(min_reward=body.min_reward)
