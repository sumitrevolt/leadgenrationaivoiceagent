"""H.4 admin API — warm-DR health + LiteLLM cost rollup.

Mounted under /api/h4 (single namespace for both since they're operationally
related — "platform survival + margin discipline").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin
from app.platform import dr_health, litellm_costs

router = APIRouter(prefix="/api/h4", tags=["Infrastructure"])


@router.get("/dr-status")
async def dr_status(_user=Depends(require_admin)) -> dict:
    """Warm-DR replica lag probe. NEUTRAL when unconfigured (no DR_REPLICA_URL)."""
    return dr_health.probe()


@router.get("/litellm-health")
async def litellm_health(_user=Depends(require_admin)) -> dict:
    """LiteLLM gateway reachability — no auth required to the gateway probe."""
    return await litellm_costs.gateway_health()


@router.get("/litellm-spend")
async def litellm_spend(hours: int = 24, _user=Depends(require_admin)) -> dict:
    """Per-virtual-key spend rollup over the last `hours`. INERT (returns
    `{available: False, reason}`) when LITELLM_COSTS unset or gateway down."""
    hours = max(1, min(int(hours), 24 * 60))
    return await litellm_costs.per_key_spend(hours=hours)


@router.get("/margin-alerts")
async def margin_alerts(_user=Depends(require_admin)) -> dict:
    """Flag clients whose LLM cost > revenue. Today returns the structural
    payload; the revenue dict will be wired from billing in a follow-up."""
    return await litellm_costs.margin_alerts()


__all__ = ["router"]
