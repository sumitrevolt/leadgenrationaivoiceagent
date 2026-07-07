"""
Leads API
Endpoints for lead scraping + a lightweight in-memory scrape/summary view.

CRUD (create/list/get/update/delete a single lead) was removed 2026-07-01: it
wrote to an in-memory `leads_storage` dict with zero real callers (no frontend
page, no other API module, only its own test suite) and was silently lost on
every process restart. The real, DB-backed lead path is the SQLAlchemy `Lead`
model (app/models/lead.py) via app/platform/prospector.py, app/tasks/sync.py,
and app/api/public_site.py — use those instead of adding new CRUD here.
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import get_current_user, require_manager
from app.lead_scraper.scraper_manager import LeadScraperManager
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()  # No prefix - main.py adds /api/leads


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


# In-memory only — holds scrape results for /stats/summary, not a durable lead store.
leads_storage: dict = {}
scrape_tasks: dict = {}
scraper = LeadScraperManager()


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_leads(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_manager),
):
    """
    Start a background scraping task (requires manager role)
    """
    import uuid

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

            # Store scraped leads
            for lead in leads:
                lead_dict = lead.to_dict()
                lead_dict["status"] = "new"
                lead_dict["lead_score"] = 0
                lead_dict["created_at"] = datetime.now()
                lead_dict["updated_at"] = datetime.now()
                leads_storage[lead.id] = lead_dict

            scrape_tasks[task_id] = {
                "status": "completed",
                "leads_found": len(leads),
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
    Get leads summary statistics
    """
    all_leads = list(leads_storage.values())

    return {
        "total": len(all_leads),
        "by_status": {
            "new": len([l for l in all_leads if l.get("status") == "new"]),
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
