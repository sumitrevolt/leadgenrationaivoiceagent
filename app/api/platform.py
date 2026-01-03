"""
Platform API
Endpoints for platform administration and tenant management
"""
from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from app.platform.tenant_manager import TenantManager, TenantStatus
from app.platform.orchestrator import PlatformOrchestrator, start_platform, stop_platform
from app.platform import SubscriptionTier, AutomationLevel
from app.utils.logger import setup_logger
from app.api.auth_deps import get_current_user, require_admin, require_super_admin
from app.models.user import User

logger = setup_logger(__name__)
router = APIRouter(prefix="/platform", tags=["Platform"])


# Pydantic Models
class TenantCreate(BaseModel):
    """Create tenant request"""
    company_name: str
    contact_name: str
    contact_phone: str
    contact_email: str
    industry: str
    target_niches: List[str] = Field(default_factory=list)
    target_cities: List[str] = Field(default_factory=list)


class TenantResponse(BaseModel):
    """Tenant response"""
    id: str
    company_name: str
    status: str
    subscription_tier: str
    calls_used: int
    calls_limit: int
    is_running: bool
    total_leads: int
    total_appointments: int


class PlatformStatsResponse(BaseModel):
    """Platform statistics response"""
    total_tenants: int
    active_tenants: int
    trial_tenants: int
    total_calls_made: int
    total_leads_generated: int
    is_running: bool


class UpgradeRequest(BaseModel):
    """Upgrade subscription request"""
    tier: str  # starter, growth, enterprise


# Global instances
tenant_manager = TenantManager()
orchestrator: Optional[PlatformOrchestrator] = None


@router.post("/start")
async def start_platform_api(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_super_admin)
):
    """
    Start the entire platform automation (requires super admin)
    This starts all automated processes
    """
    global orchestrator
    
    if orchestrator and orchestrator.is_running:
        return {"status": "already_running", "message": "Platform is already running"}
    
    orchestrator = PlatformOrchestrator()
    background_tasks.add_task(orchestrator.start)
    
    logger.info("🚀 Platform started via API")
    return {
        "status": "started",
        "message": "Platform automation started successfully"
    }


@router.post("/stop")
async def stop_platform_api(current_user: User = Depends(require_super_admin)):
    """
    Stop the platform automation gracefully (requires super admin)
    """
    global orchestrator
    
    if orchestrator:
        await orchestrator.stop()
        return {"status": "stopped", "message": "Platform stopped successfully"}
    
    return {"status": "not_running", "message": "Platform was not running"}


@router.get("/stats", response_model=PlatformStatsResponse)
async def get_platform_stats(current_user: User = Depends(require_admin)):
    """
    Get platform-wide statistics (requires admin)
    """
    stats = tenant_manager.get_platform_stats()
    
    return PlatformStatsResponse(
        total_tenants=stats["total_tenants"],
        active_tenants=stats["active_tenants"],
        trial_tenants=stats["trial_tenants"],
        total_calls_made=stats["total_calls_made"],
        total_leads_generated=stats["total_leads_generated"],
        is_running=orchestrator.is_running if orchestrator else False
    )


@router.get("/dashboard")
async def get_dashboard(current_user: User = Depends(require_admin)):
    """
    Get dashboard data for admin panel (requires admin)
    """
    if orchestrator:
        return orchestrator.get_dashboard_data()
    
    return {
        "platform_stats": {
            "is_running": False,
            "message": "Platform not started"
        },
        "tenant_stats": tenant_manager.get_platform_stats()
    }


# =========================================================================
# TENANT MANAGEMENT
# =========================================================================

@router.get("/tenants", response_model=List[dict])
async def list_tenants(
    status: Optional[str] = None,
    tier: Optional[str] = None,
    current_user: User = Depends(require_admin)
):
    """
    List all tenants on the platform (requires admin)
    """
    tenants = tenant_manager.get_all_tenants()
    
    if status:
        tenants = [t for t in tenants if t["status"] == status]
    if tier:
        tenants = [t for t in tenants if t["tier"] == tier]
    
    return tenants


@router.post("/tenants", response_model=dict)
async def create_tenant(
    tenant: TenantCreate, 
    background_tasks: BackgroundTasks,
    current_user: User = Depends(require_admin)
):
    """
    Manually onboard a new tenant/client (requires admin)
    """
    new_tenant = await tenant_manager.auto_onboard_tenant(
        company_name=tenant.company_name,
        contact_name=tenant.contact_name,
        contact_phone=tenant.contact_phone,
        contact_email=tenant.contact_email,
        industry=tenant.industry,
        target_niches=tenant.target_niches or ["general"],
        target_cities=tenant.target_cities or ["Mumbai", "Delhi", "Bangalore"]
    )
    
    return {
        "id": new_tenant.id,
        "company_name": new_tenant.company_name,
        "status": new_tenant.status.value,
        "message": "Tenant created and automation started"
    }


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str):
    """
    Get tenant details
    """
    tenant = tenant_manager.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {
        "id": tenant.id,
        "company_name": tenant.company_name,
        "contact_name": tenant.contact_name,
        "contact_phone": tenant.contact_phone,
        "contact_email": tenant.contact_email,
        "industry": tenant.industry,
        "status": tenant.status.value,
        "subscription": {
            "tier": tenant.config.subscription_tier.value,
            "calls_used": tenant.config.calls_used,
            "calls_limit": tenant.config.monthly_call_limit
        },
        "automation": {
            "is_running": tenant.is_running,
            "level": tenant.config.automation_level.value,
            "auto_scrape": tenant.config.auto_scrape,
            "auto_call": tenant.config.auto_call
        },
        "stats": {
            "total_leads": tenant.total_leads_generated,
            "total_calls": tenant.total_calls_made,
            "appointments": tenant.total_appointments
        },
        "created_at": tenant.created_at.isoformat()
    }


@router.post("/tenants/{tenant_id}/upgrade")
async def upgrade_tenant(tenant_id: str, request: UpgradeRequest):
    """
    Upgrade tenant subscription
    """
    tier_map = {
        "starter": SubscriptionTier.STARTER,
        "growth": SubscriptionTier.GROWTH,
        "enterprise": SubscriptionTier.ENTERPRISE
    }
    
    tier = tier_map.get(request.tier.lower())
    if not tier:
        raise HTTPException(status_code=400, detail="Invalid tier")
    
    success = await tenant_manager.upgrade_tenant(tenant_id, tier)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return {
        "status": "upgraded",
        "new_tier": tier.value,
        "message": f"Tenant upgraded to {tier.value}"
    }


@router.post("/tenants/{tenant_id}/pause")
async def pause_tenant(tenant_id: str):
    """
    Pause tenant's automation
    """
    await tenant_manager.pause_tenant(tenant_id)
    return {"status": "paused", "message": "Tenant automation paused"}


@router.post("/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str):
    """
    Resume tenant's automation
    """
    await tenant_manager.resume_tenant(tenant_id)
    return {"status": "resumed", "message": "Tenant automation resumed"}


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str):
    """
    Remove a tenant from the platform
    """
    if tenant_id not in tenant_manager.tenants:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    # Pause automation first
    await tenant_manager.pause_tenant(tenant_id)
    
    # Remove tenant
    tenant = tenant_manager.tenants.pop(tenant_id)
    
    logger.info(f"Tenant removed: {tenant.company_name}")
    return {"status": "deleted", "message": f"Tenant {tenant.company_name} removed"}


# =========================================================================
# PLATFORM AUTOMATION CONTROLS
# =========================================================================

@router.post("/scrape/platform")
async def trigger_platform_scrape(background_tasks: BackgroundTasks):
    """
    Manually trigger lead scraping for platform (finding new clients)
    """
    if not orchestrator:
        raise HTTPException(status_code=400, detail="Platform not started")
    
    background_tasks.add_task(orchestrator._scrape_potential_clients)
    return {"status": "started", "message": "Platform lead scraping started"}


@router.post("/scrape/tenant/{tenant_id}")
async def trigger_tenant_scrape(tenant_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger lead scraping for a specific tenant
    """
    tenant = tenant_manager.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    background_tasks.add_task(tenant_manager._scrape_for_tenant, tenant)
    return {"status": "started", "message": f"Scraping started for {tenant.company_name}"}


@router.get("/health")
async def health_check():
    """
    Platform health check
    """
    return {
        "status": "healthy",
        "platform_running": orchestrator.is_running if orchestrator else False,
        "total_tenants": len(tenant_manager.tenants),
        "timestamp": datetime.now().isoformat()
    }
