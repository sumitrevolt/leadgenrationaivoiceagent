"""
Leads API
Endpoints for lead scraping + a real-DB-backed summary view.

CRUD (create/list/get/update/delete a single lead) was removed 2026-07-01: it
wrote to an in-memory `leads_storage` dict with zero real callers (no frontend
page, no other API module, only its own test suite) and was silently lost on
every process restart. The real, DB-backed lead path is the SQLAlchemy `Lead`
model (app/models/lead.py) via app/platform/prospector.py, app/tasks/sync.py,
and app/api/public_site.py.

This module's `/scrape` NOW also persists into the real `Lead` table (dedup-by-
phone, mirroring app/api/public_site.py::_save_lead_db) so scraped leads survive
restarts. `/stats/summary` reads the real `Lead` table, not a volatile dict.
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_user, require_manager
from app.lead_scraper.scraper_manager import LeadScraperManager
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()  # No prefix - main.py adds /api/leads

# Job-status cache for in-flight scrape tasks. This is intentionally ephemeral
# (a scrape id only matters for the duration of the request's background task)
# and MUST NOT be the source of truth for lead data — that is the `Lead` table.
scrape_tasks: dict = {}
scraper = LeadScraperManager()


class ScrapeRequest(BaseModel):
    """Scrape leads request"""

    niche: str
    cities: list[str] = Field(default_factory=list)
    max_leads: int = 100


class ScrapeResponse(BaseModel):
    """Scrape response"""

    task_id: str
    status: str
    message: str


def _save_scraped_lead_to_db(lead_dict: dict) -> None:
    """Persist a scraped lead into the real `Lead` table (dedup-by-phone).

    Mirrors app/api/public_site.py::_save_lead_db: a repeat phone appends to the
    existing lead's notes instead of creating a duplicate row. Fail-safe — any
    DB error is logged and swallowed; the scrape job must never crash because of
    one bad lead row. Returns the lead id (new or existing) or None.
    """
    phone = (lead_dict.get("phone") or "").strip()
    if not phone:
        return None
    try:
        from app.models.base import _get_sync_engine, _SessionLocal
        from app.models.lead import Lead, LeadSource, LeadStatus

        engine = _get_sync_engine()
        if engine is None or _SessionLocal is None:
            return None
        db = _SessionLocal()
        try:
            company = (lead_dict.get("company_name") or "Unknown")[:255]
            city = (lead_dict.get("city") or None) or None
            niche = (lead_dict.get("niche") or None) or None
            source_raw = str(lead_dict.get("source") or "google_maps").lower()
            try:
                source = LeadSource(source_raw)
            except Exception:
                source = LeadSource.GOOGLE_MAPS
            existing = db.query(Lead).filter(Lead.phone == phone).first()
            if existing is not None:
                stamp = datetime.utcnow().isoformat()
                existing.notes = (
                    f"{existing.notes or ''}\n[Scrape re-found {stamp}] {company}".strip()
                )
                existing.updated_at = datetime.utcnow()
                db.commit()
                return existing.id
            lead = Lead(
                id=str(__import__("uuid").uuid4()),
                company_name=company,
                phone=phone,
                city=city,
                niche=niche,
                source=source,
                status=LeadStatus.NEW,
                notes=f"Scraped via /api/leads/scrape (source={source_raw})",
            )
            db.add(lead)
            db.commit()
            return lead.id
        finally:
            db.close()
    except Exception as e:
        logger.warning("scraped lead DB save failed (skipped, not fatal): %s", e)
        return None


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_leads(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_manager),
):
    """
    Start a background scraping task (requires manager role).
    Persists discovered leads into the real `Lead` table (dedup-by-phone).
    """
    task_id = str(uuid.uuid4())

    scrape_tasks[task_id] = {"status": "running", "started_at": datetime.now(), "leads_found": 0}

    async def run_scrape():
        try:
            leads = await scraper.scrape_leads(
                niche=request.niche,
                cities=request.cities if request.cities else None,
                max_leads=request.max_leads,
                # ToS-safe: is endpoint se JustDial/IndiaMart auto-scrape KABHI nahi (ban risk).
                # Sirf google_maps (andar OSM fallback). Blocked sources ka path = manual CSV import.
                # (Pehle sources=None tha → default ["google_maps","indiamart","justdial"] = ToS landmine.)
                sources=["google_maps"],
            )

            # Persist scraped leads into the real `Lead` table (survives restart).
            persisted = 0
            for lead in leads:
                if _save_scraped_lead_to_db(lead.to_dict()):
                    persisted += 1

            scrape_tasks[task_id] = {
                "status": "completed",
                "leads_found": persisted,
                "completed_at": datetime.now(),
            }

        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            scrape_tasks[task_id] = {"status": "failed", "error": str(e)}

    background_tasks.add_task(run_scrape)

    return ScrapeResponse(
        task_id=task_id,
        status="started",
        message=f"Scraping {request.niche} leads from {len(request.cities) or 'default'} cities",
    )


@router.get("/scrape/{task_id}")
async def get_scrape_status(task_id: str, current_user: User = Depends(get_current_user)):
    """
    Get scraping task status
    """
    task = scrape_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/stats/summary")
async def get_leads_summary(current_user: User = Depends(get_current_user)):
    """
    Get leads summary statistics — reads the REAL `Lead` table, not a volatile dict.
    """
    try:
        from app.models.base import _get_sync_engine, _SessionLocal
        from app.models.lead import Lead

        if _get_sync_engine() is None or _SessionLocal is None:
            return {
                "total": 0,
                "by_status": {
                    "new": 0,
                    "contacted": 0,
                    "qualified": 0,
                    "converted": 0,
                    "rejected": 0,
                },
                "by_source": {},
                "by_city": {},
                "avg_score": 0.0,
            }
        db = _SessionLocal()
        try:
            rows = db.query(Lead).all()
        finally:
            db.close()
    except Exception as e:
        logger.warning("leads summary read failed: %s", e)
        return {
            "total": 0,
            "by_status": {"new": 0, "contacted": 0, "qualified": 0, "converted": 0, "rejected": 0},
            "by_source": {},
            "by_city": {},
            "avg_score": 0.0,
        }

    all_leads = [r.to_dict() for r in rows]
    return {
        "total": len(all_leads),
        "by_status": {
            "new": len([l for l in all_leads if (l.get("status") or "new") == "new"]),
            "contacted": len([l for l in all_leads if l.get("status") == "contacted"]),
            "qualified": len([l for l in all_leads if l.get("status") == "qualified"]),
            "converted": len([l for l in all_leads if l.get("status") == "converted"]),
            "rejected": len([l for l in all_leads if l.get("status") == "rejected"]),
        },
        "by_source": _group_by(all_leads, "source"),
        "by_city": _group_by(all_leads, "city"),
        "avg_score": (
            sum(l.get("lead_score", 0) for l in all_leads) / len(all_leads) if all_leads else 0
        ),
    }


def _group_by(items: list, key: str) -> dict:
    """Group items by a key"""
    result = {}
    for item in items:
        value = item.get(key, "unknown")
        result[value] = result.get(value, 0) + 1
    return result
