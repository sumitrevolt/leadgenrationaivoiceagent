"""Capacity & approval-policy admin endpoints — Hermes/OpenCode parity (#1, #3).

Mounted by main session under /api/agents-ext. Read-only status + a risk-score preview.
Never exposes key VALUES — counts only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(tags=["AgentCapacity"])

_PROVIDER_ATTRS = [
    "GROQ_API_KEY",
    "CEREBRAS_API_KEY",
    "GEMINI_API_KEY",
    "MISTRAL_API_KEY",
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
]


@router.get("/capacity/status")
async def capacity_status(_user=Depends(require_admin)):
    """Credential-pool key counts (per provider) + flag states. Key values NEVER shown."""
    from app.agents import cred_pool, risk_approve

    return {
        "cred_pools": {
            "enabled": cred_pool.enabled(),
            "key_counts": cred_pool.key_counts(_PROVIDER_ATTRS),
            "runtime": cred_pool.pool_status(),
        },
        "risk_auto_approve": {"enabled": risk_approve.enabled()},
    }


class RiskScoreIn(BaseModel):
    task: str
    cost: float = 0.0
    reason: str = ""


@router.post("/capacity/risk-score")
async def capacity_risk_score(body: RiskScoreIn, _user=Depends(require_admin)):
    """Preview the auto-approve policy for a given action (does not enqueue anything)."""
    from app.agents import risk_approve

    return {
        "task": body.task,
        "score": risk_approve.score(body.task, body.cost, body.reason),
        "auto_approve": risk_approve.should_auto_approve(body.task, body.cost, body.reason),
        "policy_enabled": risk_approve.enabled(),
    }
