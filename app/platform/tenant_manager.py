"""
Tenant Manager
Manages multi-tenant operations for the platform

Flow:
1. Platform scrapes B2B leads (potential clients)
2. Platform calls leads to sell voice agent service
3. Interested leads become CLIENTS (tenants)
4. Each client gets automated voice agent for their leads
5. Everything runs 24/7 with minimal human intervention
"""
import asyncio
from typing import Optional, Dict, List, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid

from app.platform import TenantConfig, TenantType, SubscriptionTier, AutomationLevel, PLATFORM_CONFIG
from app.automation.campaign_manager import CampaignManager
from app.lead_scraper.scraper_manager import LeadScraperManager
from app.telephony.call_manager import CallManager
from app.integrations.whatsapp import WhatsAppIntegration
from app.integrations.email_sender import EmailSender
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TenantStatus(Enum):
    """Status of a tenant"""
    PENDING = "pending"  # Just signed up
    TRIAL = "trial"  # 7-day trial
    ACTIVE = "active"  # Paying customer
    PAUSED = "paused"  # Payment issue
    CHURNED = "churned"  # Left the platform


@dataclass
class Tenant:
    """Represents a client/tenant on the platform"""
    id: str
    company_name: str
    contact_name: str
    contact_phone: str
    contact_email: str
    industry: str
    status: TenantStatus
    config: TenantConfig
    
    # Stats
    total_leads_generated: int = 0
    total_calls_made: int = 0
    total_appointments: int = 0
    total_conversions: int = 0
    
    # Automation state
    is_running: bool = False
    last_scrape: Optional[datetime] = None
    last_call: Optional[datetime] = None
    
    created_at: datetime = field(default_factory=datetime.now)


class TenantManager:
    """
    Manages all tenants on the platform
    
    Responsibilities:
    1. Onboard new tenants automatically
    2. Setup automated campaigns for each tenant
    3. Monitor and manage tenant usage
    4. Handle billing and limits
    5. Generate reports
    """
    
    def __init__(self):
        self.tenants: Dict[str, Tenant] = {}
        self.campaign_managers: Dict[str, CampaignManager] = {}
        
        # Initialize platform's own lead generation
        self.platform_campaign = CampaignManager()
        self.scraper = LeadScraperManager()
        self.whatsapp = WhatsAppIntegration()
        self.email = EmailSender()
        
        logger.info("🏢 Tenant Manager initialized")
    
    async def auto_onboard_tenant(
        self,
        company_name: str,
        contact_name: str,
        contact_phone: str,
        contact_email: str,
        industry: str,
        target_niches: List[str],
        target_cities: List[str]
    ) -> Tenant:
        """
        Automatically onboard a new client as tenant
        Called when a lead shows interest in our service
        """
        tenant_id = str(uuid.uuid4())
        
        # Create tenant config
        config = TenantConfig(
            tenant_id=tenant_id,
            company_name=company_name,
            tenant_type=TenantType.CLIENT,
            industry=industry,
            target_audience="B2B",
            services=[],
            target_niches=target_niches,
            target_cities=target_cities,
            automation_level=AutomationLevel.FULL_AUTO,
            subscription_tier=SubscriptionTier.TRIAL,
            monthly_call_limit=100  # Trial limit
        )
        
        # Create tenant
        tenant = Tenant(
            id=tenant_id,
            company_name=company_name,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            industry=industry,
            status=TenantStatus.TRIAL,
            config=config
        )
        
        self.tenants[tenant_id] = tenant
        
        # Initialize campaign manager for this tenant
        self.campaign_managers[tenant_id] = CampaignManager()
        
        logger.info(f"✅ New tenant onboarded: {company_name} ({tenant_id})")
        
        # Send welcome messages
        await self._send_welcome_messages(tenant)
        
        # Start automated lead generation for this tenant
        if config.auto_scrape:
            asyncio.create_task(self._start_tenant_automation(tenant))
        
        return tenant
    
    async def _send_welcome_messages(self, tenant: Tenant):
        """Send welcome messages to new tenant"""
        welcome_data = {
            "company_name": tenant.company_name,
            "contact_name": tenant.contact_name,
            "tenant_id": tenant.id,
            "trial_days": 7,
            "monthly_calls": tenant.config.monthly_call_limit
        }
        
        # WhatsApp welcome
        try:
            await self.whatsapp.send_template(
                to=tenant.contact_phone,
                template_name="tenant_welcome",
                data=welcome_data
            )
        except Exception as e:
            logger.error(f"Failed to send WhatsApp welcome: {e}")
        
        # Email welcome
        try:
            await self.email.send_welcome_email(
                to=[tenant.contact_email],
                data=welcome_data
            )
        except Exception as e:
            logger.error(f"Failed to send email welcome: {e}")
    
    async def _start_tenant_automation(self, tenant: Tenant):
        """
        Start fully automated lead generation for a tenant
        This runs continuously with no human intervention
        """
        tenant.is_running = True
        logger.info(f"🚀 Starting automation for tenant: {tenant.company_name}")
        
        campaign_manager = self.campaign_managers[tenant.id]
        
        while tenant.is_running and tenant.status in [TenantStatus.TRIAL, TenantStatus.ACTIVE]:
            try:
                # Check if within daily limits
                if not self._check_limits(tenant):
                    logger.warning(f"Tenant {tenant.id} reached limits, pausing...")
                    await asyncio.sleep(3600)  # Wait an hour
                    continue
                
                # Step 1: Scrape leads for tenant's target niche
                if self._should_scrape(tenant):
                    await self._scrape_for_tenant(tenant)
                
                # Step 2: Call scraped leads
                if self._should_call(tenant):
                    await self._call_for_tenant(tenant)
                
                # Step 3: Process results and follow-ups
                await self._process_results(tenant)
                
                # Step 4: Send daily report
                if self._should_send_report(tenant):
                    await self._send_daily_report(tenant)
                
                # Wait before next cycle
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                logger.error(f"Automation error for tenant {tenant.id}: {e}")
                await asyncio.sleep(60)
        
        logger.info(f"⏹️ Stopped automation for tenant: {tenant.company_name}")
    
    def _check_limits(self, tenant: Tenant) -> bool:
        """Check if tenant is within usage limits"""
        return tenant.config.calls_used < tenant.config.monthly_call_limit
    
    def _should_scrape(self, tenant: Tenant) -> bool:
        """Check if we should scrape new leads"""
        if not tenant.config.auto_scrape:
            return False
        
        if tenant.last_scrape is None:
            return True
        
        # Scrape once per day
        hours_since_scrape = (datetime.now() - tenant.last_scrape).total_seconds() / 3600
        return hours_since_scrape >= 24
    
    def _should_call(self, tenant: Tenant) -> bool:
        """Check if we should make calls"""
        if not tenant.config.auto_call:
            return False
        
        # Check working hours
        from app.automation.scheduler import CallScheduler
        scheduler = CallScheduler()
        return scheduler.is_working_time()
    
    def _should_send_report(self, tenant: Tenant) -> bool:
        """Check if we should send daily report"""
        if not tenant.config.notify_daily_report:
            return False
        
        now = datetime.now()
        return now.hour == 20 and now.minute < 10  # 8 PM daily
    
    async def _scrape_for_tenant(self, tenant: Tenant):
        """Scrape leads for a tenant"""
        logger.info(f"📊 Scraping leads for tenant: {tenant.company_name}")
        
        for niche in tenant.config.target_niches:
            leads = await self.scraper.scrape_leads(
                niche=niche,
                cities=tenant.config.target_cities,
                max_leads=50  # 50 per niche
            )
            
            tenant.total_leads_generated += len(leads)
            logger.info(f"Found {len(leads)} leads for {tenant.company_name} in {niche}")
        
        tenant.last_scrape = datetime.now()
    
    async def _call_for_tenant(self, tenant: Tenant):
        """Make calls for a tenant"""
        campaign_manager = self.campaign_managers[tenant.id]
        
        # Process call queue
        stats = await campaign_manager.call_manager.process_queue()
        
        if stats.get("calls_made", 0) > 0:
            tenant.config.calls_used += stats["calls_made"]
            tenant.total_calls_made += stats["calls_made"]
            tenant.last_call = datetime.now()
    
    async def _process_results(self, tenant: Tenant):
        """Process call results - appointments, callbacks, etc."""
        campaign_manager = self.campaign_managers[tenant.id]
        
        # Get hot leads
        hot_leads = []  # TODO: Get from database
        
        # Notify tenant about hot leads
        for lead in hot_leads:
            if tenant.config.notify_on_hot_lead:
                await self.whatsapp.send_lead_alert(
                    tenant.contact_phone,
                    lead
                )
    
    async def _send_daily_report(self, tenant: Tenant):
        """Send daily performance report to tenant"""
        report = {
            "date": datetime.now().date().isoformat(),
            "company_name": tenant.company_name,
            "leads_scraped": tenant.total_leads_generated,
            "calls_made": tenant.total_calls_made,
            "appointments_booked": tenant.total_appointments,
            "calls_remaining": tenant.config.monthly_call_limit - tenant.config.calls_used
        }
        
        if "whatsapp" in tenant.config.notification_channels:
            await self.whatsapp.send_daily_report(tenant.contact_phone, report)
        
        if "email" in tenant.config.notification_channels:
            await self.email.send_daily_report([tenant.contact_email], report)
    
    async def upgrade_tenant(
        self,
        tenant_id: str,
        new_tier: SubscriptionTier
    ) -> bool:
        """Upgrade tenant subscription"""
        tenant = self.tenants.get(tenant_id)
        if not tenant:
            return False
        
        tier_limits = {
            SubscriptionTier.STARTER: 500,
            SubscriptionTier.GROWTH: 2000,
            SubscriptionTier.ENTERPRISE: 10000,
        }
        
        tenant.config.subscription_tier = new_tier
        tenant.config.monthly_call_limit = tier_limits.get(new_tier, 500)
        tenant.status = TenantStatus.ACTIVE
        
        logger.info(f"📈 Tenant {tenant.company_name} upgraded to {new_tier.value}")
        return True
    
    async def pause_tenant(self, tenant_id: str):
        """Pause a tenant's automation"""
        tenant = self.tenants.get(tenant_id)
        if tenant:
            tenant.is_running = False
            tenant.status = TenantStatus.PAUSED
            logger.info(f"⏸️ Paused tenant: {tenant.company_name}")
    
    async def resume_tenant(self, tenant_id: str):
        """Resume a tenant's automation"""
        tenant = self.tenants.get(tenant_id)
        if tenant and tenant.status == TenantStatus.PAUSED:
            tenant.status = TenantStatus.ACTIVE
            asyncio.create_task(self._start_tenant_automation(tenant))
            logger.info(f"▶️ Resumed tenant: {tenant.company_name}")
    
    def get_all_tenants(self) -> List[Dict]:
        """Get all tenants summary"""
        return [
            {
                "id": t.id,
                "company_name": t.company_name,
                "status": t.status.value,
                "tier": t.config.subscription_tier.value,
                "calls_used": t.config.calls_used,
                "calls_limit": t.config.monthly_call_limit,
                "is_running": t.is_running
            }
            for t in self.tenants.values()
        ]
    
    def get_platform_stats(self) -> Dict:
        """Get overall platform statistics"""
        active_tenants = len([t for t in self.tenants.values() if t.status == TenantStatus.ACTIVE])
        trial_tenants = len([t for t in self.tenants.values() if t.status == TenantStatus.TRIAL])
        
        total_calls = sum(t.total_calls_made for t in self.tenants.values())
        total_leads = sum(t.total_leads_generated for t in self.tenants.values())
        total_appointments = sum(t.total_appointments for t in self.tenants.values())
        
        return {
            "total_tenants": len(self.tenants),
            "active_tenants": active_tenants,
            "trial_tenants": trial_tenants,
            "total_calls_made": total_calls,
            "total_leads_generated": total_leads,
            "total_appointments": total_appointments,
            "platform_running": True
        }
