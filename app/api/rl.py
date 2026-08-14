"""RL Flywheel admin API (Phase 0) — read-only visibility into the reward spine.

Mirrors app/api/eval_gate.py. No policy control here; observability only.
Admin-gated. INERT data when RL_ENGINE unset (reward.* returns empty).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agents.rl import reward
from app.api.auth_deps import require_admin

router = APIRouter(prefix="/api/rl", tags=["Infrastructure"])


@router.get("/summary")
async def rl_summary(_user=Depends(require_admin)) -> dict:
    """Totals + per-domain graduation status (samples vs RL_GRADUATION_N)."""
    return reward.summary()


@router.get("/arms")
async def rl_arms(domain: str = "voice", _user=Depends(require_admin)) -> dict:
    """Per-arm n / mean_reward / Laplace success_rate / Beta(alpha,beta)."""
    return {"domain": domain, "arms": reward.arm_stats(domain)}


@router.get("/recent")
async def rl_recent(domain: str = "", n: int = 50, _user=Depends(require_admin)) -> dict:
    """Recent reward rows (optionally filtered by domain)."""
    n = max(1, min(int(n), 500))
    return {"domain": domain or "all", "rows": reward.recent(domain or None, n=n)}


@router.get("/dev")
async def rl_dev(n: int = 50, _user=Depends(require_admin)) -> dict:
    """Recent Claude dev-session feedback, scored on read via reward.dev_reward."""
    n = max(1, min(int(n), 500))
    rows = reward._read(reward._DEV, n=n)
    for r in rows:
        r["reward"] = reward.dev_reward(r)
    return {"count": len(rows), "rows": rows[::-1]}


__all__ = ["router"]
