"""
assessment.py — REST API for dashboard assessment system.
GET /api/assessment/run   — run full assessment + save report
GET /api/assessment/latest — return latest assessment JSON metrics
GET /api/assessment/history — list past assessments
GET /api/assessment/diff  — compare latest vs baseline
"""

from __future__ import annotations

import json
import logging
import pathlib

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.api.admin import require_admin

log = logging.getLogger(__name__)
router = APIRouter(prefix="/assessment", tags=["Dashboard Assessment"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"
DATA = ROOT / "data"
HISTORY = DATA / "assessment_history"


def _latest_metrics() -> dict:
    path = DOCS / "dashboard_metrics.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _run_assessment_bg():
    """Background task: import orchestrator lazily to avoid startup overhead."""
    try:
        from app.platform.dashboard_assessment import DashboardAssessment

        assessor = DashboardAssessment()
        assessor.run_full()
        log.info("Background assessment complete.")
    except Exception as e:
        log.error(f"Background assessment failed: {e}")


@router.post("/run")
async def run_assessment(
    background_tasks: BackgroundTasks,
    _admin=Depends(require_admin),
):
    """Trigger a full dashboard assessment. Runs in background, returns job_id."""
    background_tasks.add_task(_run_assessment_bg)
    return {
        "status": "queued",
        "message": "Assessment running in background. Poll /api/assessment/latest in ~5s.",
    }


@router.get("/latest")
async def get_latest(_admin=Depends(require_admin)):
    """Return the latest assessment JSON metrics."""
    data = _latest_metrics()
    if not data:
        raise HTTPException(
            status_code=404, detail="No assessment found. Run POST /api/assessment/run first."
        )
    return data


@router.get("/report")
async def get_report_markdown(_admin=Depends(require_admin)):
    """Return the latest Markdown assessment report as plain text."""
    path = DOCS / "DASHBOARD_ASSESSMENT_REPORT.md"
    if not path.exists():
        raise HTTPException(status_code=404, detail="No report found.")
    return {"report": path.read_text(encoding="utf-8")}


@router.get("/history")
async def list_history(_admin=Depends(require_admin)):
    """List past assessments from data/assessment_history/."""
    HISTORY.mkdir(parents=True, exist_ok=True)
    files = sorted(HISTORY.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    items = []
    for f in files[:20]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            items.append(
                {
                    "assessment_id": data.get("assessment_id", f.stem),
                    "generated_at": data.get("generated_at"),
                    "scores": data.get("scores", {}),
                    "file": f.name,
                }
            )
        except Exception:
            pass
    return {"history": items, "count": len(items)}


@router.get("/diff")
async def get_diff(baseline: str = "latest", _admin=Depends(require_admin)):
    """Compare current assessment against a baseline. Returns regression report."""
    try:
        from app.platform.dashboard_assessment import DashboardAssessment

        assessor = DashboardAssessment()
        result = assessor.run_diff(baseline_id=baseline)
        return result
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Baseline '{baseline}' not found.")
    except Exception as e:
        log.error(f"Diff failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scores")
async def get_scores(_admin=Depends(require_admin)):
    """Quick scores summary for dashboard widgets."""
    data = _latest_metrics()
    if not data:
        return {
            "customer_completeness": None,
            "admin_completeness": None,
            "competitive_parity": None,
            "ux_quality": None,
            "assessment_id": None,
            "generated_at": None,
        }
    return {
        **data.get("scores", {}),
        "assessment_id": data.get("assessment_id"),
        "generated_at": data.get("generated_at"),
        "counts": data.get("counts", {}),
    }
