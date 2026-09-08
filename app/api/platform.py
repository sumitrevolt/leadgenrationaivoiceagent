"""
Platform API
Endpoints for platform administration and tenant management
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin, require_super_admin
from app.models.base import get_async_db
from app.models.user import User
from app.platform import SubscriptionTier
from app.platform.tenant_manager import TenantManager
from app.utils.logger import setup_logger

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
    target_niches: list[str] = Field(default_factory=list)
    target_cities: list[str] = Field(default_factory=list)


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

# NOTE: PlatformOrchestrator (Cloud-Run era) REMOVED. Sab scheduling
# team_scheduler handle karta hai — /platform/start = manual growth pulse.
_scheduler_running: bool = False


@router.post("/start")
async def start_platform_api(
    background_tasks: BackgroundTasks, current_user: User = Depends(require_super_admin)
):
    """
    Trigger a manual growth pulse + confirm scheduler is running.
    (Full automation team_scheduler me hoti hai — always-on via Docker.)
    """
    global _scheduler_running
    try:
        from app.platform import growth_engine

        background_tasks.add_task(growth_engine.pulse)
        _scheduler_running = True
    except Exception as _e:
        logger.warning(f"[platform/start] growth pulse trigger failed: {_e}")
    logger.info("🚀 Platform pulse triggered via API")
    return {
        "status": "started",
        "message": "Growth pulse triggered — team_scheduler handles full automation",
    }


@router.post("/stop")
async def stop_platform_api(current_user: User = Depends(require_super_admin)):
    """
    Mark scheduler flag off (informational — Docker-managed processes need
    container stop; this endpoint is kept for API compatibility).
    """
    global _scheduler_running
    _scheduler_running = False
    return {
        "status": "stopped",
        "message": "Flag cleared — to fully stop, bring down the container",
    }


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
        is_running=_scheduler_running,
    )


@router.get("/dashboard")
async def get_dashboard(current_user: User = Depends(require_admin)):
    """
    Get dashboard data — live growth pulse + tenant stats.
    """
    try:
        from app.platform import growth_engine

        pulse = growth_engine.latest_pulse()
    except Exception:
        pulse = {}
    return {
        "platform_stats": {"is_running": _scheduler_running, "pulse": pulse},
        "tenant_stats": tenant_manager.get_platform_stats(),
    }


# =========================================================================
# TENANT MANAGEMENT
# =========================================================================


@router.get("/tenants", response_model=list[dict])
async def list_tenants(
    status: str | None = None,
    tier: str | None = None,
    current_user: User = Depends(require_admin),
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
    current_user: User = Depends(require_admin),
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
        target_cities=tenant.target_cities or ["Mumbai", "Delhi", "Bangalore"],
    )

    return {
        "id": new_tenant.id,
        "company_name": new_tenant.company_name,
        "status": new_tenant.status.value,
        "message": "Tenant created and automation started",
    }


# ============================================================================
# CLIENTS (DB-backed) — onboarding with auto-provisioned agents
# ============================================================================


class ClientCreate(BaseModel):
    """Create a DB client; system auto-provisions its 2 agents (data+leads)."""

    business_name: str
    contact_name: str
    contact_email: str
    contact_phone: str
    industry: str = ""  # free text ya NICHES key — resolve ho jata hai
    niche: str | None = None  # explicit NICHES key (industry se priority)
    city: str | None = None


@router.post("/clients", response_model=dict)
async def create_client(
    payload: ClientCreate,
    db=Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """
    New client onboarding: DB record + uske business ke hisab se 2 agents —
    ek DATA agent (business data/KB) aur ek LEADS agent (end-customer calling).
    """
    import secrets as _secrets
    import uuid as _uuid

    from sqlalchemy import select as _select

    from app.models.client import Client, ClientStatus
    from app.platform.agent_provisioner import provision_agents_for_client

    existing = await db.execute(
        _select(Client).where(Client.contact_email == payload.contact_email)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Client with this email already exists")

    client = Client(
        id=str(_uuid.uuid4()),
        business_name=payload.business_name,
        contact_name=payload.contact_name,
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
        industry=payload.niche or payload.industry,
        city=payload.city,
        status=ClientStatus.TRIAL,
        api_key=_secrets.token_urlsafe(32),
    )
    db.add(client)
    await db.flush()

    agents = await provision_agents_for_client(db, client, niche=payload.niche)

    return {
        "client": {
            "id": client.id,
            "business_name": client.business_name,
            "status": client.status.value,
            "niche": agents["niche_key"],
            "target_type": agents["target_type"],
        },
        "agents": agents["created"] + agents["existing"],
        "message": "Client created — data agent + leads agent provisioned",
    }


@router.post("/clients/{client_id}/provision-agents", response_model=dict)
async def provision_client_agents(
    client_id: str,
    niche: str | None = None,
    db=Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """
    Existing client ke liye 2 agents ensure karo (idempotent) — purane
    (seeded) clients ko backfill karne ke liye.
    """
    from sqlalchemy import select as _select

    from app.models.client import Client
    from app.platform.agent_provisioner import provision_agents_for_client

    result = await db.execute(_select(Client).where(Client.id == client_id))
    client = result.scalar_one_or_none()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    agents = await provision_agents_for_client(db, client, niche=niche)
    return {
        "client_id": client_id,
        "niche": agents["niche_key"],
        "created": agents["created"],
        "existing": agents["existing"],
    }


@router.get("/clients/{client_id}/agents", response_model=dict)
async def list_client_agents(
    client_id: str,
    db=Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Client ke dedicated agents (data + leads) ki list."""
    from sqlalchemy import select as _select

    from app.models.agent import Agent
    from app.platform.agent_provisioner import _agent_dict

    result = await db.execute(_select(Agent).where(Agent.current_client_id == client_id))
    agents = [_agent_dict(a) for a in result.scalars().all()]
    return {"client_id": client_id, "agents": agents, "count": len(agents)}


@router.get("/tenants/{tenant_id}")
async def get_tenant(tenant_id: str, current_user: User = Depends(require_admin)):
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
            "calls_limit": tenant.config.monthly_call_limit,
        },
        "automation": {
            "is_running": tenant.is_running,
            "level": tenant.config.automation_level.value,
            "auto_scrape": tenant.config.auto_scrape,
            "auto_call": tenant.config.auto_call,
        },
        "stats": {
            "total_leads": tenant.total_leads_generated,
            "total_calls": tenant.total_calls_made,
            "appointments": tenant.total_appointments,
        },
        "created_at": tenant.created_at.isoformat(),
    }


@router.post("/tenants/{tenant_id}/upgrade")
async def upgrade_tenant(
    tenant_id: str, request: UpgradeRequest, current_user: User = Depends(require_admin)
):
    """
    Upgrade tenant subscription
    """
    tier_map = {
        "starter": SubscriptionTier.STARTER,
        "growth": SubscriptionTier.GROWTH,
        "enterprise": SubscriptionTier.ENTERPRISE,
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
        "message": f"Tenant upgraded to {tier.value}",
    }


@router.post("/tenants/{tenant_id}/pause")
async def pause_tenant(tenant_id: str, current_user: User = Depends(require_admin)):
    """
    Pause tenant's automation
    """
    await tenant_manager.pause_tenant(tenant_id)
    return {"status": "paused", "message": "Tenant automation paused"}


@router.post("/tenants/{tenant_id}/resume")
async def resume_tenant(tenant_id: str, current_user: User = Depends(require_admin)):
    """
    Resume tenant's automation
    """
    await tenant_manager.resume_tenant(tenant_id)
    return {"status": "resumed", "message": "Tenant automation resumed"}


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, current_user: User = Depends(require_super_admin)):
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
async def trigger_platform_scrape(
    background_tasks: BackgroundTasks, current_user: User = Depends(require_admin)
):
    """
    Manually trigger lead scraping for platform (finding new clients via niche prospector)
    """
    try:
        from app.platform import niche_prospector as _np

        background_tasks.add_task(_np.run)
    except Exception as _e:
        raise HTTPException(status_code=500, detail=f"Scrape trigger failed: {_e}")
    return {"status": "started", "message": "Platform lead scraping started via niche_prospector"}


@router.post("/scrape/tenant/{tenant_id}")
async def trigger_tenant_scrape(
    tenant_id: str, background_tasks: BackgroundTasks, current_user: User = Depends(require_admin)
):
    """
    Manually trigger lead scraping for a specific tenant
    """
    tenant = tenant_manager.tenants.get(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    background_tasks.add_task(tenant_manager._scrape_for_tenant, tenant)
    return {"status": "started", "message": f"Scraping started for {tenant.company_name}"}


@router.get("/health", dependencies=[Depends(require_admin)])
async def health_check():
    """
    Platform health check (admin-only — leaks tenant count + scheduler state).

    NOTE: the PUBLIC liveness probe is the top-level `/health` route (uptime/Caddy);
    this `/api/platform/health` is internal operator state and was anonymously
    reachable (2026-07-06 sec sweep — the "one ungated route in a gated file" trap).
    """
    return {
        "status": "healthy",
        "platform_running": _scheduler_running,
        "total_tenants": len(tenant_manager.tenants),
        "timestamp": datetime.now().isoformat(),
    }
