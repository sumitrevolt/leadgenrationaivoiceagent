"""
Leads API
Endpoints for lead management
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from app.lead_scraper.scraper_manager import LeadScraperManager, UnifiedLead
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/leads", tags=["Leads"])

# Pydantic Models
class LeadCreate(BaseModel):
    """Create lead request"""
    company_name: str
    contact_name: Optional[str] = None
    phone: str
    email: Optional[str] = None
    website: Optional[str] = None
    city: str
    category: str
    source: str = "manual"
    notes: Optional[str] = None


class LeadUpdate(BaseModel):
    """Update lead request"""
    status: Optional[str] = None
    lead_score: Optional[int] = None
    notes: Optional[str] = None
    assigned_to: Optional[str] = None
    website: Optional[str] = None


class LeadResponse(BaseModel):
    """Lead response"""
    id: str
    company_name: str
    contact_name: Optional[str]
    phone: str
    email: Optional[str]
    website: Optional[str]
    city: str
    category: str
    source: str
    status: str
    lead_score: int
    verified: bool
    created_at: datetime
    updated_at: datetime


class ScrapeRequest(BaseModel):
    """Scrape leads request"""
    niche: str
    cities: List[str] = Field(default_factory=list)
    max_leads: int = 100


class ScrapeResponse(BaseModel):
    """Scrape response"""
    task_id: str
    status: str
    message: str


# In-memory storage (replace with database in production)
leads_storage: dict = {}
scrape_tasks: dict = {}
scraper = LeadScraperManager()

def load_growth_engine_leads():
    """Load leads from Growth Engine CSVs"""
    import csv
    import glob
    import os
    
    try:
        # Find all master_leads csv files
        list_of_files = glob.glob('revenue_pipeline/master_leads_*.csv') 
        if not list_of_files:
            return

        # Load all of them or just the latest? Let's load the latest for now to avoid duplicates if running multiple times
        # actually, let's load all unique phone numbers
        
        for csv_file in list_of_files:
            with open(csv_file, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Use phone or name as unique key to prevent duplicates
                    lead_id = f"csv_{row.get('Phone', row.get('Name'))}".replace(" ", "_")
                    
                    if lead_id not in leads_storage:
                        leads_storage[lead_id] = {
                            "id": lead_id,
                            "company_name": row.get("Name"),
                            "phone": row.get("Phone"),
                            "city": row.get("City", "Unknown"),
                            "category": row.get("Niche", "Unknown"),
                            "website": row.get("Website"),
                            "source": "Growth Engine",
                            "status": "new",
                            "lead_score": int(row.get("Lead Score", 0) or 0),
                            "verified": False,
                            "created_at": datetime.now(),
                            "updated_at": datetime.now(),
                            "notes": row.get("Efficiency Report"),
                            "email": None,
                            "contact_name": None
                        }
        logger.info(f"Loaded {len(leads_storage)} leads from revenue_pipeline")
    except Exception as e:
        logger.error(f"Error loading CSV leads: {e}")


@router.get("/", response_model=List[LeadResponse])
async def list_leads(
    status: Optional[str] = None,
    city: Optional[str] = None,
    category: Optional[str] = None,
    min_score: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500)
):
    """
    List all leads with optional filters
    """
    # Auto-load leads if empty
    if not leads_storage:
        load_growth_engine_leads()
        
    filtered = list(leads_storage.values())
    
    if status:
        filtered = [l for l in filtered if l.get("status") == status]
    if city:
        filtered = [l for l in filtered if l.get("city", "").lower() == city.lower()]
    if category:
        filtered = [l for l in filtered if l.get("category", "").lower() == category.lower()]
    if min_score:
        filtered = [l for l in filtered if l.get("lead_score", 0) >= min_score]
    
    return filtered[skip:skip + limit]


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(lead_id: str):
    """
    Get a specific lead by ID
    """
    lead = leads_storage.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.post("/", response_model=LeadResponse)
async def create_lead(lead: LeadCreate):
    """
    Create a new lead manually
    """
    import uuid
    
    lead_id = str(uuid.uuid4())
    now = datetime.now()
    
    lead_data = {
        "id": lead_id,
        **lead.model_dump(),
        "status": "new",
        "lead_score": 0,
        "verified": False,
        "created_at": now,
        "updated_at": now
    }
    
    leads_storage[lead_id] = lead_data
    logger.info(f"Lead created: {lead_id}")
    
    return lead_data


@router.put("/{lead_id}", response_model=LeadResponse)
async def update_lead(lead_id: str, update: LeadUpdate):
    """
    Update an existing lead
    """
    lead = leads_storage.get(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    update_data = update.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now()
    
    lead.update(update_data)
    leads_storage[lead_id] = lead
    
    logger.info(f"Lead updated: {lead_id}")
    return lead


@router.delete("/{lead_id}")
async def delete_lead(lead_id: str):
    """
    Delete a lead
    """
    if lead_id not in leads_storage:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    del leads_storage[lead_id]
    logger.info(f"Lead deleted: {lead_id}")
    
    return {"message": "Lead deleted successfully"}


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_leads(
    request: ScrapeRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a background scraping task
    """
    import uuid
    
    task_id = str(uuid.uuid4())
    
    scrape_tasks[task_id] = {
        "status": "running",
        "started_at": datetime.now(),
        "leads_found": 0
    }
    
    async def run_scrape():
        try:
            leads = await scraper.scrape_leads(
                niche=request.niche,
                cities=request.cities if request.cities else None,
                max_leads=request.max_leads
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
                "completed_at": datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Scrape failed: {e}")
            scrape_tasks[task_id] = {
                "status": "failed",
                "error": str(e)
            }
    
    background_tasks.add_task(run_scrape)
    
    return ScrapeResponse(
        task_id=task_id,
        status="started",
        message=f"Scraping {request.niche} leads from {len(request.cities) or 'default'} cities"
    )


@router.get("/scrape/{task_id}")
async def get_scrape_status(task_id: str):
    """
    Get scraping task status
    """
    task = scrape_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.get("/stats/summary")
async def get_leads_summary():
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
            "rejected": len([l for l in all_leads if l.get("status") == "rejected"])
        },
        "by_source": _group_by(all_leads, "source"),
        "by_city": _group_by(all_leads, "city"),
        "avg_score": sum(l.get("lead_score", 0) for l in all_leads) / len(all_leads) if all_leads else 0
    }


def _group_by(items: list, key: str) -> dict:
    """Group items by a key"""
    result = {}
    for item in items:
        value = item.get(key, "unknown")
        result[value] = result.get(value, 0) + 1
    return result
