"""eval_gate admin API — close-the-loop visibility for /app/automation.

Surfaces what `app/agents/eval_gate.py` records: per-suite/metric baseline
medians, latest score, latest decision (accept/reject/no_baseline), and
recent decision counts. Read-only, admin-gated.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents import eval_gate
from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(prefix="/api/eval-gate", tags=["Infrastructure"])


@router.get("/summary")
async def eval_gate_summary(window: int = 20, _user=Depends(require_admin)) -> dict:
    """Recent history rollup. `window` = how many recent rows feed the median."""
    return eval_gate.summary(window=max(5, min(window, 200)))


@router.get("/recent")
async def eval_gate_recent(
    suite: str = "rag_quality",
    metric: str = "faithfulness",
    n: int = 50,
    _user=Depends(require_admin),
) -> dict:
    """Per-(suite, metric) recent score series — for sparkline / trend plot."""
    n = max(1, min(n, 500))
    samples = eval_gate.recent_scores(suite, metric, n=n)
    base = eval_gate.baseline(suite, metric)
    return {
        "suite": suite,
        "metric": metric,
        "count": len(samples),
        "scores": samples,
        "baseline_median": base,
        "enabled": eval_gate.enabled(),
        "hard_mode": eval_gate.hard_mode(),
    }


class ResetIn(BaseModel):
    suite: str = Field(..., min_length=1, max_length=80)
    metric: str = Field(..., min_length=1, max_length=80)


@router.post("/reset")
async def reset(body: ResetIn, _user=Depends(require_super_admin)) -> dict:
    """L.4: clear baseline history for one (suite, metric). Super-admin only —
    a wrong reset wipes the regression-detection signal for that metric until
    fresh scores accumulate. Returns removed/remaining counts."""
    out = eval_gate.reset_baseline(body.suite, body.metric)
    if not out.get("ok"):
        raise HTTPException(status_code=500, detail=out.get("error", "reset failed"))
    return out


__all__ = ["router"]
