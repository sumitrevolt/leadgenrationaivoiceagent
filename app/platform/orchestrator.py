"""
Platform Orchestrator
The MASTER controller that runs everything automatically

This is the "brain" of the entire platform that:
1. Runs YOUR company's lead generation (finding clients)
2. Manages all client campaigns automatically
3. Handles onboarding, billing, monitoring
4. Operates 24/7 with minimal human intervention
"""
import asyncio
from typing import Dict, List, Optional
from datetime import datetime, time
from dataclasses import dataclass

from app.platform.tenant_manager import TenantManager, Tenant, TenantStatus
from app.platform import PLATFORM_CONFIG, TenantType, SubscriptionTier, AutomationLevel
from app.automation.campaign_manager import CampaignManager, Campaign
from app.automation.scheduler import CallScheduler
from app.lead_scraper.scraper_manager import LeadScraperManager
from app.telephony.call_manager import CallManager
from app.integrations.whatsapp import WhatsAppIntegration
from app.integrations.email_sender import EmailSender
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class PlatformStats:
    """Platform-wide statistics"""
    platform_leads_scraped: int = 0
    platform_calls_made: int = 0
    platform_appointments: int = 0
    new_clients_today: int = 0
    active_campaigns: int = 0
    total_revenue: float = 0


class PlatformOrchestrator:
    """
    Master Controller - Runs the entire platform automatically
    
    Key Responsibilities:
    1. Find B2B clients for YOUR company (platform's own lead gen)
    2. Auto-onboard interested leads as clients
    3. Start automated campaigns for each client
    4. Monitor all operations
    5. Generate reports and alerts
    
    Runs 24/7 with ZERO human intervention required
    """
    
    def __init__(self):
        # Core components
        self.tenant_manager = TenantManager()
        self.platform_campaign = CampaignManager()
        self.scheduler = CallScheduler()
        self.scraper = LeadScraperManager()
        self.call_manager = CallManager()
        
        # Notifications
        self.whatsapp = WhatsAppIntegration()
        self.email = EmailSender()
        
        # State
        self.is_running = False
        self.stats = PlatformStats()
        self.start_time: Optional[datetime] = None
        
        logger.info("🎯 Platform Orchestrator initialized")
        logger.info(f"   Company: {PLATFORM_CONFIG['company_name']}")
        logger.info(f"   Services: {', '.join(PLATFORM_CONFIG['services'])}")
    
    async def start(self):
        """
        Start the entire platform - everything runs automatically from here
        """
        self.is_running = True
        self.start_time = datetime.now()
        
        logger.info("=" * 60)
        logger.info("🚀 PLATFORM STARTING - FULLY AUTOMATED MODE")
        logger.info("=" * 60)
        
        # Start call processor background task
        asyncio.create_task(self.call_manager.start_call_processor())
        
        # Start all automated processes in parallel
        await asyncio.gather(
            self._run_platform_lead_generation(),  # Find clients for us
            self._run_tenant_monitor(),  # Monitor all client campaigns
            self._run_daily_tasks(),  # Daily maintenance
            self._run_health_check()  # System monitoring
        )
    
    async def stop(self):
        """Stop the platform gracefully"""
        logger.info("⏹️ Platform stopping...")
        self.is_running = False
        
        # Stop all tenant campaigns
        for tenant_id in self.tenant_manager.tenants:
            await self.tenant_manager.pause_tenant(tenant_id)
    
    # =========================================================================
    # PLATFORM'S OWN LEAD GENERATION (Finding clients for YOUR company)
    # =========================================================================
    
    async def _run_platform_lead_generation(self):
        """
        Find B2B leads (potential clients) for YOUR company
        These are businesses that might want to buy our voice agent service
        """
        logger.info("📊 Starting platform's own lead generation...")
        
        while self.is_running:
            try:
                # Check if it's time to scrape (daily at 6 AM)
                # For demo/dev purposes, we might want to trigger this manually or more often
                now = datetime.now()
                if now.hour == 6 and now.minute < 10:
                    await self._scrape_potential_clients()
                
                # Check completed calls for interested leads
                # (Call processor runs in background, we just verify results here)
                await self._check_call_results()
                
                # Wait before next check
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Platform lead gen error: {e}")
                await asyncio.sleep(60)
    
    async def _scrape_potential_clients(self):
        """Scrape potential clients and QUEUE them for calling"""
        logger.info("🔍 Scraping potential clients for platform...")
        
        from app.telephony.call_manager import CallRequest
        
        # Target niches - businesses that need lead generation
        target_niches = PLATFORM_CONFIG.get("target_niches", ["Real Estate"])
        target_cities = PLATFORM_CONFIG.get("target_cities", ["Mumbai"])
        
        total_leads = 0
        company_name = PLATFORM_CONFIG.get("company_name", "LeadGen AI")

        for niche in target_niches:
            try:
                leads = await self.scraper.scrape_leads(
                    niche=niche,
                    cities=target_cities,
                    max_leads=5  # Small batch for safety
                )
                
                for lead in leads:
                    if not lead.phone:
                        continue
                        
                    # QUEUE THE CALL!
                    await self.call_manager.queue_call(CallRequest(
                        lead_id=lead.id,
                        phone_number=lead.phone,
                        campaign_id="platform_growth_engine",
                        niche=niche,
                        client_name=company_name,
                        client_service="AI Lead Gen SAAS",
                        script_name="saas_sales_agent", # Triggers "Maya"
                        lead_data=lead.to_dict(),
                        priority=1 # High priority for our own growth
                    ))
                    
                total_leads += len(leads)
                logger.info(f"Queued {len(leads)} calls for {niche}")
                
            except Exception as e:
                logger.error(f"Failed to scrape {niche}: {e}")
        
        self.stats.platform_leads_scraped += total_leads
        logger.info(f"✅ Total potential clients queued: {total_leads}")
    
    async def _check_call_results(self):
        """Check for interested leads from completed calls"""
        # In a real app, we'd consume from a queue or DB
        # Here we just check the manager's in-memory list
        
        # Get appointments/interested leads
        interested = await self.call_manager.get_hot_leads()
        appointments = await self.call_manager.get_appointments()
        
        # Process them
        await self._process_interested_leads(interested + appointments)
        
        # Clear them from memory to avoid double processing (in a real app, use DB flags)
        # self.call_manager.completed_calls = [c for c in self.call_manager.completed_calls if c not in interested and c not in appointments]
    
    async def _process_interested_leads(self, call_results: List):
        """
        Process interested leads - Auto-onboard them as clients
        This is where leads become PAYING CLIENTS
        """
        for result in call_results:
            if result.get("outcome") in ["interested", "appointment"]:
                try:
                    # Auto-onboard as trial client
                    await self.tenant_manager.auto_onboard_tenant(
                        company_name=result.get("company_name", "Unknown"),
                        contact_name=result.get("contact_name", ""),
                        contact_phone=result.get("phone_number"),
                        contact_email=result.get("email", ""),
                        industry=result.get("niche", "general"),
                        target_niches=[result.get("niche", "general")],
                        target_cities=["Mumbai", "Delhi", "Bangalore"]
                    )
                    
                    self.stats.new_clients_today += 1
                    logger.info(f"🎉 New client onboarded: {result.get('company_name')}")
                    
                except Exception as e:
                    logger.error(f"Failed to onboard client: {e}")
    
    # =========================================================================
    # TENANT MONITORING (Managing all client campaigns)
    # =========================================================================
    
    async def _run_tenant_monitor(self):
        """Monitor and manage all tenant campaigns"""
        logger.info("👁️ Starting tenant monitor...")
        
        while self.is_running:
            try:
                tenants = self.tenant_manager.tenants.values()
                
                for tenant in tenants:
                    await self._check_tenant_health(tenant)
                    await self._check_tenant_limits(tenant)
                
                # Update active campaign count
                self.stats.active_campaigns = len([
                    t for t in tenants if t.is_running
                ])
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Tenant monitor error: {e}")
                await asyncio.sleep(30)
    
    async def _check_tenant_health(self, tenant: Tenant):
        """Check if tenant's automation is running properly"""
        if tenant.status == TenantStatus.ACTIVE and not tenant.is_running:
            # Restart if stopped unexpectedly
            logger.warning(f"Restarting automation for {tenant.company_name}")
            await self.tenant_manager.resume_tenant(tenant.id)
    
    async def _check_tenant_limits(self, tenant: Tenant):
        """Check tenant usage limits"""
        usage_percent = (tenant.config.calls_used / tenant.config.monthly_call_limit) * 100
        
        if usage_percent >= 80 and usage_percent < 90:
            # Warn at 80%
            await self.whatsapp.send_template(
                to=tenant.contact_phone,
                template_name="usage_warning",
                data={"percent": int(usage_percent)}
            )
        
        elif usage_percent >= 100:
            # Pause and notify at 100%
            await self.tenant_manager.pause_tenant(tenant.id)
            await self.whatsapp.send_template(
                to=tenant.contact_phone,
                template_name="limit_reached",
                data={"tier": tenant.config.subscription_tier.value}
            )
    
    # =========================================================================
    # DAILY AUTOMATED TASKS
    # =========================================================================
    
    async def _run_daily_tasks(self):
        """Run daily maintenance tasks"""
        logger.info("📅 Starting daily tasks scheduler...")
        
        while self.is_running:
            now = datetime.now()
            
            try:
                # 6 AM - Scrape leads for all active tenants
                if now.hour == 6 and now.minute < 5:
                    await self._daily_scrape_all_tenants()
                
                # 8 PM - Send daily reports
                if now.hour == 20 and now.minute < 5:
                    await self._send_all_daily_reports()
                
                # 12 AM - Reset daily counters, check trial expirations
                if now.hour == 0 and now.minute < 5:
                    await self._midnight_maintenance()
                
                # First of month - Reset monthly limits
                if now.day == 1 and now.hour == 0 and now.minute < 5:
                    await self._monthly_reset()
                
            except Exception as e:
                logger.error(f"Daily task error: {e}")
            
            await asyncio.sleep(60)  # Check every minute
    
    async def _daily_scrape_all_tenants(self):
        """Scrape leads for all active tenants"""
        logger.info("🔄 Daily scrape for all tenants starting...")
        
        for tenant in self.tenant_manager.tenants.values():
            if tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
                if tenant.config.auto_scrape:
                    await self.tenant_manager._scrape_for_tenant(tenant)
    
    async def _send_all_daily_reports(self):
        """Send daily reports to all tenants"""
        logger.info("📧 Sending daily reports to all tenants...")
        
        for tenant in self.tenant_manager.tenants.values():
            if tenant.status in [TenantStatus.ACTIVE, TenantStatus.TRIAL]:
                await self.tenant_manager._send_daily_report(tenant)
        
        # Also send platform-wide report to admin
        await self._send_platform_admin_report()
    
    async def _send_platform_admin_report(self):
        """Send platform performance report to admin"""
        stats = self.tenant_manager.get_platform_stats()
        stats.update({
            "platform_leads": self.stats.platform_leads_scraped,
            "platform_calls": self.stats.platform_calls_made,
            "new_clients_today": self.stats.new_clients_today
        })
        
        # TODO: Send to admin WhatsApp/email
        logger.info(f"📊 Platform Stats: {stats}")
    
    async def _midnight_maintenance(self):
        """Midnight maintenance tasks"""
        logger.info("🌙 Running midnight maintenance...")
        
        # Check trial expirations
        for tenant in self.tenant_manager.tenants.values():
            if tenant.status == TenantStatus.TRIAL:
                days_active = (datetime.now() - tenant.created_at).days
                if days_active >= 7:
                    # Trial expired
                    await self.tenant_manager.pause_tenant(tenant.id)
                    tenant.status = TenantStatus.PAUSED
                    
                    # Send trial ended notification
                    await self.whatsapp.send_template(
                        to=tenant.contact_phone,
                        template_name="trial_ended",
                        data={"company": tenant.company_name}
                    )
        
        # Reset daily stats
        self.stats.new_clients_today = 0
    
    async def _monthly_reset(self):
        """Reset monthly limits for all tenants"""
        logger.info("📆 Monthly reset for all tenants...")
        
        for tenant in self.tenant_manager.tenants.values():
            tenant.config.calls_used = 0
            
            # Send monthly summary
            await self.email.send_monthly_summary(
                to=[tenant.contact_email],
                data={
                    "company": tenant.company_name,
                    "total_calls": tenant.total_calls_made,
                    "appointments": tenant.total_appointments,
                    "month": datetime.now().strftime("%B %Y")
                }
            )
    
    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================
    
    async def _run_health_check(self):
        """Monitor system health"""
        logger.info("💓 Starting health monitor...")
        
        while self.is_running:
            try:
                health = {
                    "status": "healthy",
                    "uptime_hours": (datetime.now() - self.start_time).total_seconds() / 3600 if self.start_time else 0,
                    "active_tenants": len([t for t in self.tenant_manager.tenants.values() if t.is_running]),
                    "total_calls_today": self.stats.platform_calls_made,
                    "memory_usage": "OK",  # TODO: Add actual memory check
                    "database": "OK"  # TODO: Add actual DB health check
                }
                
                # Log health every hour
                if datetime.now().minute == 0:
                    logger.info(f"💓 Health Check: {health}")
                
            except Exception as e:
                logger.error(f"Health check error: {e}")
            
            await asyncio.sleep(300)  # Check every 5 minutes
    
    def get_dashboard_data(self) -> Dict:
        """Get data for admin dashboard"""
        return {
            "platform_stats": {
                "uptime_hours": (datetime.now() - self.start_time).total_seconds() / 3600 if self.start_time else 0,
                "is_running": self.is_running,
                "leads_scraped": self.stats.platform_leads_scraped,
                "calls_made": self.stats.platform_calls_made,
                "new_clients_today": self.stats.new_clients_today
            },
            "tenant_stats": self.tenant_manager.get_platform_stats(),
            "active_campaigns": self.stats.active_campaigns
        }


# Global orchestrator instance
orchestrator: Optional[PlatformOrchestrator] = None


async def start_platform():
    """Start the platform - call this once to run everything"""
    global orchestrator
    orchestrator = PlatformOrchestrator()
    await orchestrator.start()


async def stop_platform():
    """Stop the platform gracefully"""
    global orchestrator
    if orchestrator:
        await orchestrator.stop()
