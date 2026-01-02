"""
Campaigns API
Endpoints for campaign management
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from app.automation.campaign_manager import CampaignManager, CampaignStatus, CampaignType
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/campaigns", tags=["Campaigns"])

# Pydantic Models
class CampaignCreate(BaseModel):
    """Create campaign request"""
    name: str
    niche: str
    client_name: str
    client_service: str
    target_cities: List[str] = Field(default_factory=list)
    target_lead_count: int = 500
    daily_call_limit: int = 100
    notify_whatsapp: List[str] = Field(default_factory=list)
    notify_email: List[str] = Field(default_factory=list)
    sync_to_sheets: bool = True
    sync_to_hubspot: bool = False


class CampaignResponse(BaseModel):
    """Campaign response"""
    id: str
    name: str
    niche: str
    status: str
    client_name: str
    leads_scraped: int
    leads_called: int
    leads_qualified: int
    appointments_booked: int
    progress: float
    created_at: datetime


class CampaignStats(BaseModel):
    """Campaign statistics"""
    id: str
    name: str
    status: str
    leads_scraped: int
    leads_called: int
    leads_qualified: int
    appointments_booked: int
    callbacks_scheduled: int
    connection_rate: float
    qualification_rate: float
    conversion_rate: float


# Initialize campaign manager
campaign_manager = CampaignManager()


@router.get("/", response_model=List[dict])
async def list_campaigns(
    status: Optional[str] = None,
    niche: Optional[str] = None
):
    """
    List all campaigns
    """
    campaigns = campaign_manager.list_campaigns()
    
    if status:
        campaigns = [c for c in campaigns if c["status"] == status]
    if niche:
        campaigns = [c for c in campaigns if c["niche"] == niche]
    
    return campaigns


@router.get("/{campaign_id}")
async def get_campaign(campaign_id: str):
    """
    Get campaign details
    """
    stats = await campaign_manager.get_campaign_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return stats


@router.post("/", response_model=dict)
async def create_campaign(campaign: CampaignCreate):
    """
    Create a new campaign
    """
    created = await campaign_manager.create_campaign(
        name=campaign.name,
        niche=campaign.niche,
        client_name=campaign.client_name,
        client_service=campaign.client_service,
        target_cities=campaign.target_cities if campaign.target_cities else None,
        target_lead_count=campaign.target_lead_count,
        daily_call_limit=campaign.daily_call_limit,
        notify_whatsapp=campaign.notify_whatsapp,
        notify_email=campaign.notify_email,
        sync_to_sheets=campaign.sync_to_sheets,
        sync_to_hubspot=campaign.sync_to_hubspot
    )
    
    logger.info(f"Campaign created: {created.id}")
    
    return {
        "id": created.id,
        "name": created.name,
        "status": created.status.value,
        "message": "Campaign created successfully"
    }


@router.post("/{campaign_id}/start")
async def start_campaign(campaign_id: str, background_tasks: BackgroundTasks):
    """
    Start a campaign (begins scraping and calling)
    """
    try:
        started = await campaign_manager.start_campaign(campaign_id)
        if started:
            return {"status": "started", "message": "Campaign started successfully"}
        else:
            return {"status": "already_running", "message": "Campaign is already running"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{campaign_id}/pause")
async def pause_campaign(campaign_id: str):
    """
    Pause a running campaign
    """
    paused = await campaign_manager.pause_campaign(campaign_id)
    if paused:
        return {"status": "paused", "message": "Campaign paused"}
    raise HTTPException(status_code=404, detail="Campaign not found or not running")


@router.post("/{campaign_id}/resume")
async def resume_campaign(campaign_id: str):
    """
    Resume a paused campaign
    """
    resumed = await campaign_manager.resume_campaign(campaign_id)
    if resumed:
        return {"status": "resumed", "message": "Campaign resumed"}
    raise HTTPException(status_code=404, detail="Campaign not found or not paused")


@router.get("/{campaign_id}/stats", response_model=CampaignStats)
async def get_campaign_stats(campaign_id: str):
    """
    Get detailed campaign statistics
    """
    stats = await campaign_manager.get_campaign_stats(campaign_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Campaign not found")
    
    # Calculate rates
    leads_scraped = stats.get("leads_scraped", 0)
    leads_called = stats.get("leads_called", 0)
    leads_qualified = stats.get("leads_qualified", 0)
    appointments = stats.get("appointments_booked", 0)
    
    return CampaignStats(
        id=stats["id"],
        name=stats["name"],
        status=stats["status"],
        leads_scraped=leads_scraped,
        leads_called=leads_called,
        leads_qualified=leads_qualified,
        appointments_booked=appointments,
        callbacks_scheduled=stats.get("callbacks_scheduled", 0),
        connection_rate=leads_called / leads_scraped if leads_scraped > 0 else 0,
        qualification_rate=leads_qualified / leads_called if leads_called > 0 else 0,
        conversion_rate=appointments / leads_qualified if leads_qualified > 0 else 0
    )


@router.get("/niches/available")
async def get_available_niches():
    """
    Get list of available niches with scripts
    """
    from app.lead_scraper.scraper_manager import LeadScraperManager
    
    return {
        "niches": list(LeadScraperManager.NICHE_QUERIES.keys()),
        "description": {
            "real_estate": "Real estate developers, brokers, property dealers",
            "solar": "Solar installation and energy companies",
            "logistics": "Logistics, transport, freight companies",
            "digital_marketing": "Digital marketing agencies",
            "manufacturing": "Manufacturing and industrial businesses",
            "insurance": "Insurance agencies and brokers"
        }
    }


@router.get("/cities/available")
async def get_available_cities():
    """
    Get list of available target cities
    """
    from app.lead_scraper.scraper_manager import LeadScraperManager
    
    return {
        "cities": LeadScraperManager.INDIAN_CITIES,
        "tier1": ["Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata"],
        "tier2": ["Pune", "Ahmedabad", "Jaipur", "Lucknow", "Chandigarh", "Indore"]
    }
