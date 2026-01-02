"""
Campaign Manager
Orchestrates entire lead generation campaigns
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import uuid

from app.config import settings
from app.lead_scraper.scraper_manager import LeadScraperManager, UnifiedLead
from app.telephony.call_manager import CallManager, CallRequest, CallResult
from app.integrations.google_sheets import GoogleSheetsIntegration
from app.integrations.hubspot import HubSpotIntegration
from app.integrations.whatsapp import WhatsAppIntegration
from app.integrations.email_sender import EmailSender
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CampaignStatus(Enum):
    """Campaign status"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignType(Enum):
    """Type of campaign"""
    COLD_OUTREACH = "cold_outreach"  # Scrape and call new leads
    FOLLOW_UP = "follow_up"  # Follow up on existing leads
    CALLBACK = "callback"  # Handle callback requests
    RE_ENGAGEMENT = "re_engagement"  # Re-engage old leads


@dataclass
class Campaign:
    """Campaign configuration"""
    id: str
    name: str
    type: CampaignType
    status: CampaignStatus
    
    # Target configuration
    niche: str
    target_cities: List[str]
    target_lead_count: int
    
    # Client details
    client_name: str
    client_service: str
    script_name: str
    
    # Schedule
    start_date: datetime
    end_date: Optional[datetime]
    daily_call_limit: int
    working_hours_start: str
    working_hours_end: str
    
    # Notifications
    notify_whatsapp: List[str] = field(default_factory=list)
    notify_email: List[str] = field(default_factory=list)
    hot_lead_threshold: int = 70
    
    # CRM sync
    sync_to_sheets: bool = True
    sync_to_hubspot: bool = False
    spreadsheet_id: Optional[str] = None
    
    # Stats
    leads_scraped: int = 0
    leads_called: int = 0
    leads_qualified: int = 0
    appointments_booked: int = 0
    callbacks_scheduled: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


class CampaignManager:
    """
    Manages end-to-end lead generation campaigns
    
    Flow:
    1. Create campaign with configuration
    2. Scrape leads (automated)
    3. Queue calls (automated, scheduled)
    4. Process results (automated)
    5. Notify on hot leads (automated)
    6. Sync to CRM (automated)
    7. Generate reports (automated)
    """
    
    def __init__(self):
        self.scraper = LeadScraperManager()
        self.call_manager = CallManager()
        self.sheets = GoogleSheetsIntegration()
        self.hubspot = HubSpotIntegration()
        self.whatsapp = WhatsAppIntegration()
        self.email = EmailSender()
        
        self.campaigns: Dict[str, Campaign] = {}
        self.campaign_leads: Dict[str, List[UnifiedLead]] = {}
        
        logger.info("🎯 Campaign Manager initialized")
    
    async def create_campaign(
        self,
        name: str,
        niche: str,
        client_name: str,
        client_service: str,
        target_cities: Optional[List[str]] = None,
        target_lead_count: int = 500,
        daily_call_limit: int = 100,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        notify_whatsapp: Optional[List[str]] = None,
        notify_email: Optional[List[str]] = None,
        sync_to_sheets: bool = True,
        sync_to_hubspot: bool = False
    ) -> Campaign:
        """
        Create a new campaign
        """
        campaign_id = str(uuid.uuid4())
        
        campaign = Campaign(
            id=campaign_id,
            name=name,
            type=CampaignType.COLD_OUTREACH,
            status=CampaignStatus.DRAFT,
            niche=niche,
            target_cities=target_cities or LeadScraperManager.INDIAN_CITIES[:5],
            target_lead_count=target_lead_count,
            client_name=client_name,
            client_service=client_service,
            script_name=f"{niche}_script",
            start_date=start_date or datetime.now(),
            end_date=end_date,
            daily_call_limit=daily_call_limit,
            working_hours_start=settings.working_hours_start,
            working_hours_end=settings.working_hours_end,
            notify_whatsapp=notify_whatsapp or [],
            notify_email=notify_email or [],
            sync_to_sheets=sync_to_sheets,
            sync_to_hubspot=sync_to_hubspot
        )
        
        self.campaigns[campaign_id] = campaign
        logger.info(f"Campaign created: {name} ({campaign_id})")
        
        return campaign
    
    async def start_campaign(self, campaign_id: str) -> bool:
        """
        Start a campaign (full automation)
        
        This will:
        1. Scrape leads
        2. Create spreadsheet
        3. Start calling
        """
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        if campaign.status == CampaignStatus.RUNNING:
            logger.warning(f"Campaign {campaign_id} is already running")
            return False
        
        campaign.status = CampaignStatus.RUNNING
        campaign.updated_at = datetime.now()
        
        logger.info(f"🚀 Starting campaign: {campaign.name}")
        
        # Run campaign pipeline
        asyncio.create_task(self._run_campaign_pipeline(campaign))
        
        return True
    
    async def _run_campaign_pipeline(self, campaign: Campaign):
        """Run the full campaign pipeline"""
        try:
            # Step 1: Scrape leads
            logger.info(f"Step 1: Scraping leads for {campaign.name}")
            leads = await self.scraper.scrape_leads(
                niche=campaign.niche,
                cities=campaign.target_cities,
                max_leads=campaign.target_lead_count
            )
            
            campaign.leads_scraped = len(leads)
            self.campaign_leads[campaign.id] = leads
            logger.info(f"Scraped {len(leads)} leads")
            
            # Step 2: Setup spreadsheet
            if campaign.sync_to_sheets:
                logger.info("Step 2: Setting up Google Sheets")
                
                if not campaign.spreadsheet_id:
                    # Create new spreadsheet for this campaign
                    campaign.spreadsheet_id = await self.sheets.create_spreadsheet(
                        title=f"{campaign.name} - Leads",
                        share_with=campaign.notify_email
                    )
                
                await self.sheets.add_leads_sheet(campaign.spreadsheet_id)
                await self.sheets.add_call_log_sheet(campaign.spreadsheet_id)
                
                # Add leads to sheet
                lead_dicts = [lead.to_dict() for lead in leads]
                await self.sheets.append_leads_batch(lead_dicts, campaign.spreadsheet_id)
                logger.info("Leads added to Google Sheets")
            
            # Step 3: Queue calls
            logger.info("Step 3: Queueing calls")
            await self._queue_campaign_calls(campaign, leads)
            
            # Step 4: Start call processor (if not already running)
            asyncio.create_task(self._monitor_campaign(campaign))
            
            logger.info(f"✅ Campaign {campaign.name} pipeline started")
            
        except Exception as e:
            logger.error(f"Campaign pipeline error: {e}")
            campaign.status = CampaignStatus.PAUSED
    
    async def _queue_campaign_calls(
        self,
        campaign: Campaign,
        leads: List[UnifiedLead]
    ):
        """Queue calls for all leads"""
        for i, lead in enumerate(leads):
            if not lead.phone:
                continue
            
            # Calculate scheduled time based on working hours
            scheduled_time = self._calculate_call_time(
                campaign,
                i,
                campaign.daily_call_limit
            )
            
            request = CallRequest(
                lead_id=lead.id,
                phone_number=lead.phone,
                campaign_id=campaign.id,
                niche=campaign.niche,
                client_name=campaign.client_name,
                client_service=campaign.client_service,
                script_name=campaign.script_name,
                lead_data={
                    "company_name": lead.company_name,
                    "contact_name": lead.contact_name,
                    "city": lead.city,
                    "category": lead.category
                },
                priority=5 if lead.verified else 7,
                scheduled_time=scheduled_time
            )
            
            await self.call_manager.queue_call(request)
        
        logger.info(f"Queued {len(leads)} calls for campaign {campaign.id}")
    
    def _calculate_call_time(
        self,
        campaign: Campaign,
        call_index: int,
        daily_limit: int
    ) -> datetime:
        """Calculate when a call should be made based on working hours"""
        # Parse working hours
        start_hour = int(campaign.working_hours_start.split(':')[0])
        end_hour = int(campaign.working_hours_end.split(':')[0])
        working_hours = end_hour - start_hour
        
        # Calculate day offset
        day_offset = call_index // daily_limit
        calls_today = call_index % daily_limit
        
        # Spread calls throughout the day
        calls_per_hour = daily_limit / working_hours
        hour_offset = int(calls_today / calls_per_hour)
        minute_offset = int((calls_today % calls_per_hour) * (60 / calls_per_hour))
        
        call_time = campaign.start_date + timedelta(
            days=day_offset,
            hours=start_hour + hour_offset,
            minutes=minute_offset
        )
        
        return call_time
    
    async def _monitor_campaign(self, campaign: Campaign):
        """Monitor campaign progress and handle events"""
        while campaign.status == CampaignStatus.RUNNING:
            try:
                # Update stats
                stats = self.call_manager.get_stats()
                
                # Get completed calls for this campaign
                completed = [
                    c for c in self.call_manager.completed_calls
                    if hasattr(c, 'campaign_id') and c.campaign_id == campaign.id
                ]
                
                campaign.leads_called = len(completed)
                campaign.leads_qualified = sum(1 for c in completed if c.lead_score >= 50)
                campaign.appointments_booked = sum(1 for c in completed if c.outcome == "appointment")
                campaign.callbacks_scheduled = sum(1 for c in completed if c.outcome == "callback")
                campaign.updated_at = datetime.now()
                
                # Process hot leads
                for call in completed:
                    if call.lead_score >= campaign.hot_lead_threshold:
                        await self._handle_hot_lead(campaign, call)
                
                # Check if campaign is complete
                if campaign.leads_called >= campaign.leads_scraped:
                    campaign.status = CampaignStatus.COMPLETED
                    await self._send_campaign_summary(campaign)
                    break
                
                # Wait before next check
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Campaign monitoring error: {e}")
                await asyncio.sleep(60)
        
        logger.info(f"Campaign {campaign.name} monitoring stopped")
    
    async def _handle_hot_lead(self, campaign: Campaign, call: CallResult):
        """Handle hot lead notification and CRM sync"""
        lead_data = {
            "company_name": call.qualification_data.get("company_name", ""),
            "contact_name": call.qualification_data.get("contact_name", ""),
            "phone": call.phone_number,
            "city": call.qualification_data.get("city", ""),
            "lead_score": call.lead_score,
            "detected_intent": call.outcome,
            "notes": str(call.qualification_data),
            "call_time": call.completed_at.isoformat()
        }
        
        # Send WhatsApp notifications
        for number in campaign.notify_whatsapp:
            try:
                await self.whatsapp.send_lead_alert(number, lead_data)
            except Exception as e:
                logger.error(f"WhatsApp notification failed: {e}")
        
        # Send email notifications
        if campaign.notify_email:
            try:
                await self.email.send_lead_alert(campaign.notify_email, lead_data)
            except Exception as e:
                logger.error(f"Email notification failed: {e}")
        
        # Sync to HubSpot
        if campaign.sync_to_hubspot:
            try:
                contact_id = await self.hubspot.create_contact(lead_data)
                if contact_id:
                    await self.hubspot.log_call_activity(contact_id, {
                        "phone": call.phone_number,
                        "duration_seconds": call.duration_seconds,
                        "outcome": call.outcome,
                        "lead_score": call.lead_score,
                        "completed_at": call.completed_at
                    })
            except Exception as e:
                logger.error(f"HubSpot sync failed: {e}")
        
        # Update sheet
        if campaign.sync_to_sheets and campaign.spreadsheet_id:
            try:
                await self.sheets.update_lead_status(
                    lead_id=call.lead_id,
                    status="called",
                    outcome=call.outcome,
                    lead_score=call.lead_score,
                    notes=str(call.qualification_data),
                    spreadsheet_id=campaign.spreadsheet_id
                )
                
                await self.sheets.log_call({
                    "call_id": call.call_id,
                    "lead_id": call.lead_id,
                    "phone": call.phone_number,
                    "campaign_id": campaign.id,
                    "duration_seconds": call.duration_seconds,
                    "outcome": call.outcome,
                    "lead_score": call.lead_score,
                    "recording_url": call.recording_url
                }, campaign.spreadsheet_id)
            except Exception as e:
                logger.error(f"Sheets sync failed: {e}")
    
    async def _send_campaign_summary(self, campaign: Campaign):
        """Send campaign completion summary"""
        summary = {
            "campaign_name": campaign.name,
            "leads_scraped": campaign.leads_scraped,
            "leads_called": campaign.leads_called,
            "leads_qualified": campaign.leads_qualified,
            "appointments_booked": campaign.appointments_booked,
            "callbacks_scheduled": campaign.callbacks_scheduled,
            "connection_rate": campaign.leads_called / campaign.leads_scraped if campaign.leads_scraped > 0 else 0,
            "qualification_rate": campaign.leads_qualified / campaign.leads_called if campaign.leads_called > 0 else 0
        }
        
        logger.info(f"Campaign {campaign.name} completed: {summary}")
        
        # Send notifications
        for number in campaign.notify_whatsapp:
            await self.whatsapp.send_daily_report(number, summary)
        
        if campaign.notify_email:
            await self.email.send_daily_report(campaign.notify_email, summary)
    
    async def pause_campaign(self, campaign_id: str) -> bool:
        """Pause a running campaign"""
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return False
        
        campaign.status = CampaignStatus.PAUSED
        campaign.updated_at = datetime.now()
        logger.info(f"Campaign {campaign.name} paused")
        return True
    
    async def resume_campaign(self, campaign_id: str) -> bool:
        """Resume a paused campaign"""
        campaign = self.campaigns.get(campaign_id)
        if not campaign or campaign.status != CampaignStatus.PAUSED:
            return False
        
        campaign.status = CampaignStatus.RUNNING
        campaign.updated_at = datetime.now()
        
        asyncio.create_task(self._monitor_campaign(campaign))
        logger.info(f"Campaign {campaign.name} resumed")
        return True
    
    async def get_campaign_stats(self, campaign_id: str) -> Dict[str, Any]:
        """Get current campaign statistics"""
        campaign = self.campaigns.get(campaign_id)
        if not campaign:
            return {}
        
        return {
            "id": campaign.id,
            "name": campaign.name,
            "status": campaign.status.value,
            "niche": campaign.niche,
            "leads_scraped": campaign.leads_scraped,
            "leads_called": campaign.leads_called,
            "leads_qualified": campaign.leads_qualified,
            "appointments_booked": campaign.appointments_booked,
            "callbacks_scheduled": campaign.callbacks_scheduled,
            "progress": campaign.leads_called / campaign.leads_scraped if campaign.leads_scraped > 0 else 0,
            "created_at": campaign.created_at.isoformat(),
            "updated_at": campaign.updated_at.isoformat()
        }
    
    def list_campaigns(self) -> List[Dict[str, Any]]:
        """List all campaigns"""
        return [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status.value,
                "niche": c.niche,
                "progress": c.leads_called / c.leads_scraped if c.leads_scraped > 0 else 0
            }
            for c in self.campaigns.values()
        ]
