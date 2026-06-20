"""Process-engine endpoints (process-as-code: deterministic + breakpoints).

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/process/*).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Growth"])


# ------------- Process engine (babysitter-pattern: deterministic + breakpoints) ------------- #
@router.get("/process/definitions")
async def process_definitions(_user=Depends(require_admin)):
    """Available process-as-code workflows (steps + gates + breakpoints)."""
    from app.agents import process_library

    return {"processes": process_library.list_processes()}


class ProcessStartIn(BaseModel):
    process: str
    inputs: dict = {}


@router.post("/process/start")
async def process_start(body: ProcessStartIn, _user=Depends(require_admin)):
    """Run start + Celery worker me advance enqueue; worker down ho to inline advance."""
    from app.agents import process_engine

    r = process_engine.start_run(body.process, body.inputs)
    if r.get("ok"):
        run_id = r.get("run_id") or ""
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            try:
                adv = await process_engine.advance(run_id)
                r["queued"] = False
                r["fallback"] = "in_process"
                r["advance"] = adv
            except Exception as e2:
                r["queued"] = False
                r["hint"] = f"worker+inline fail: {str(e2)[:100]}"
    return r


@router.get("/process/runs")
async def process_runs(limit: int = 20, _user=Depends(require_admin)):
    """Recent runs + journal-derived live status."""
    from app.agents import process_engine

    return {"runs": process_engine.list_runs(limit)}


@router.get("/process/run/{run_id}")
async def process_run_detail(run_id: str, _user=Depends(require_admin)):
    """Run state (replay) + full immutable journal."""
    from app.agents import process_engine

    return {"state": process_engine.replay(run_id), "journal": process_engine.journal(run_id)}


class ProcessApproveIn(BaseModel):
    note: str = ""


@router.post("/process/run/{run_id}/approve")
async def process_approve(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint APPROVE → run resume (Celery tick)."""
    from app.agents import process_engine

    r = process_engine.approve(
        run_id, approved_by=getattr(_user, "email", "admin") or "admin", note=body.note
    )
    if r.get("ok"):
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            try:
                adv = await process_engine.advance(run_id)
                r["queued"] = False
                r["fallback"] = "in_process"
                r["advance"] = adv
            except Exception:
                r["queued"] = False
    return r


@router.post("/process/run/{run_id}/reject")
async def process_reject(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint REJECT → run failed (audit trail)."""
    from app.agents import process_engine

    return process_engine.reject(
        run_id, by=getattr(_user, "email", "admin") or "admin", reason=body.note
    )
