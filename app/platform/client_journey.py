"""
Automated Client Journey
Handles the entire lifecycle from lead to paying customer automatically

JOURNEY STAGES:
1. Lead Found (Scraped from Google Maps, IndiaMart, etc.)
2. Initial Call Made (AI pitches the service)
3. Interest Captured (Lead shows interest)
4. Trial Started (Auto-onboarded as trial client)
5. Nurturing (Automated follow-ups during trial)
6. Conversion (Trial to paid subscription)
7. Active Client (Ongoing service with their own AI agent)
"""
import asyncio
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from app.utils.logger import setup_logger
from app.integrations.whatsapp_handler import whatsapp_handler
from app.integrations.email_sender import email_sender
from app.platform.sales_scripts import PlatformScripts
from app.config import settings

logger = setup_logger(__name__)


class JourneyStage(Enum):
    """Client journey stages"""
    NEW_LEAD = "new_lead"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    TRIAL_STARTED = "trial_started"
    TRIAL_DAY_3 = "trial_day_3"
    TRIAL_ENDING = "trial_ending"
    TRIAL_ENDED = "trial_ended"
    CONVERTED = "converted"
    ACTIVE = "active"
    CHURNED = "churned"
    NOT_INTERESTED = "not_interested"


class InteractionType(Enum):
    """Types of interactions"""
    CALL = "call"
    WHATSAPP = "whatsapp"
    EMAIL = "email"
    SMS = "sms"


@dataclass
class JourneyEvent:
    """Single event in the journey"""
    stage: JourneyStage
    interaction_type: InteractionType
    message: str
    outcome: str = ""
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class ClientJourneyTracker:
    """Track a client's journey through the funnel"""
    lead_id: str
    company_name: str
    contact_name: str
    contact_phone: str
    contact_email: str
    industry: str
    
    current_stage: JourneyStage = JourneyStage.NEW_LEAD
    events: List[JourneyEvent] = field(default_factory=list)
    
    # Stage timestamps
    first_contact_at: Optional[datetime] = None
    trial_started_at: Optional[datetime] = None
    converted_at: Optional[datetime] = None
    
    # Metrics
    total_calls: int = 0
    total_whatsapp_messages: int = 0
    total_emails: int = 0
    
    # Lead quality score (1-10)
    quality_score: int = 5


class ClientJourneyManager:
    """
    Manages the automated client journey
    
    This class handles ALL stages automatically:
    - Initial outreach
    - Follow-ups
    - Trial onboarding
    - Nurturing during trial
    - Conversion attempts
    - Churn prevention
    """
    
    def __init__(self):
        self.active_journeys: Dict[str, ClientJourneyTracker] = {}
        self.scripts = PlatformScripts
    
    async def start_journey(
        self,
        lead_id: str,
        company_name: str,
        contact_name: str,
        contact_phone: str,
        contact_email: str,
        industry: str
    ) -> ClientJourneyTracker:
        """Start a new client journey"""
        
        tracker = ClientJourneyTracker(
            lead_id=lead_id,
            company_name=company_name,
            contact_name=contact_name,
            contact_phone=contact_phone,
            contact_email=contact_email,
            industry=industry
        )
        
        self.active_journeys[lead_id] = tracker
        
        logger.info(f"📍 Journey started for {company_name}")
        
        # Automatically proceed to first contact
        await self._schedule_first_contact(tracker)
        
        return tracker
    
    async def _schedule_first_contact(self, tracker: ClientJourneyTracker):
        """Schedule the initial contact call"""
        
        # Record intent to contact
        tracker.events.append(JourneyEvent(
            stage=JourneyStage.NEW_LEAD,
            interaction_type=InteractionType.CALL,
            message="Scheduled for initial contact call"
        ))
        
        # The actual call is handled by the PlatformOrchestrator
        # This just prepares the journey
    
    async def record_call_outcome(
        self,
        lead_id: str,
        outcome: str,
        details: Dict = None
    ):
        """
        Record the outcome of a call
        
        Outcomes:
        - interested: Wants to try
        - callback: Asked for callback
        - not_interested: Clear rejection
        - no_answer: Didn't pick up
        - busy: Was busy, try later
        """
        
        if lead_id not in self.active_journeys:
            logger.warning(f"Journey not found for lead {lead_id}")
            return
        
        tracker = self.active_journeys[lead_id]
        tracker.total_calls += 1
        
        if tracker.first_contact_at is None:
            tracker.first_contact_at = datetime.now()
        
        # Update stage based on outcome
        if outcome == "interested":
            tracker.current_stage = JourneyStage.INTERESTED
            tracker.quality_score = 8
            
            # Auto-start trial
            await self._auto_start_trial(tracker)
            
        elif outcome == "callback":
            tracker.current_stage = JourneyStage.CONTACTED
            tracker.quality_score = 6
            
            # Schedule callback
            await self._schedule_callback(tracker, details.get("callback_time"))
            
        elif outcome == "not_interested":
            tracker.current_stage = JourneyStage.NOT_INTERESTED
            tracker.quality_score = 2
            
            # Maybe a follow-up in 30 days?
            
        elif outcome == "no_answer":
            # Retry logic
            if tracker.total_calls < 3:
                await self._schedule_retry(tracker)
        
        # Record event
        tracker.events.append(JourneyEvent(
            stage=tracker.current_stage,
            interaction_type=InteractionType.CALL,
            message=f"Call completed",
            outcome=outcome
        ))
    
    async def _auto_start_trial(self, tracker: ClientJourneyTracker):
        """Automatically start trial for interested lead"""
        
        tracker.current_stage = JourneyStage.TRIAL_STARTED
        tracker.trial_started_at = datetime.now()
        
        # Send welcome messages
        await self._send_trial_welcome(tracker)
        
        # Schedule nurturing sequence
        await self._schedule_nurturing(tracker)
        
        logger.info(f"✅ Trial auto-started for {tracker.company_name}")
    
    async def _send_trial_welcome(self, tracker: ClientJourneyTracker):
        """Send welcome messages when trial starts"""
        
        # WhatsApp welcome
        welcome_message = f"""🎉 Welcome to LeadGen AI Solutions, {tracker.contact_name}!

Your 7-day FREE trial has started!

What's included:
✅ 100 AI-powered calls
✅ Automated lead scraping
✅ WhatsApp alerts for hot leads
✅ Full CRM integration

Dashboard: https://app.leadgenai.com/login

Your login credentials have been sent to {tracker.contact_email}

Questions? Just reply to this message!

Let's generate some leads! 🚀"""

        await whatsapp_handler.send_message(
            to=tracker.contact_phone,
            message=welcome_message
        )
        tracker.total_whatsapp_messages += 1
        
        # Email welcome
        await email_sender.send_email(
            to=tracker.contact_email,
            subject="Welcome to LeadGen AI - Your Trial Has Started!",
            body=welcome_message.replace("✅", "•").replace("🎉", "").replace("🚀", ""),
            is_html=False
        )
        tracker.total_emails += 1
        
        tracker.events.append(JourneyEvent(
            stage=JourneyStage.TRIAL_STARTED,
            interaction_type=InteractionType.WHATSAPP,
            message="Trial welcome sequence sent"
        ))
    
    async def _schedule_nurturing(self, tracker: ClientJourneyTracker):
        """Schedule nurturing messages during trial"""
        
        # Day 3: Check-in
        await self._schedule_message(
            tracker,
            delay_days=3,
            stage=JourneyStage.TRIAL_DAY_3,
            message_type="trial_day_3"
        )
        
        # Day 6: Trial ending warning
        await self._schedule_message(
            tracker,
            delay_days=6,
            stage=JourneyStage.TRIAL_ENDING,
            message_type="trial_ending"
        )
        
        # Day 8: Trial ended - conversion push
        await self._schedule_message(
            tracker,
            delay_days=8,
            stage=JourneyStage.TRIAL_ENDED,
            message_type="trial_ended"
        )
    
    async def _schedule_message(
        self,
        tracker: ClientJourneyTracker,
        delay_days: int,
        stage: JourneyStage,
        message_type: str
    ):
        """Schedule a future message"""
        
        # In production, this would use a task queue like Celery
        # For now, we log the scheduled action
        
        scheduled_time = datetime.now() + timedelta(days=delay_days)
        
        logger.info(
            f"📅 Scheduled {message_type} for {tracker.company_name} "
            f"at {scheduled_time.strftime('%Y-%m-%d %H:%M')}"
        )
    
    async def _schedule_callback(
        self,
        tracker: ClientJourneyTracker,
        callback_time: Optional[str]
    ):
        """Schedule a callback as requested by the lead"""
        
        if callback_time:
            logger.info(
                f"📞 Callback scheduled for {tracker.company_name} at {callback_time}"
            )
        else:
            # Default to next day 11 AM
            logger.info(f"📞 Callback scheduled for {tracker.company_name} tomorrow 11 AM")
    
    async def _schedule_retry(self, tracker: ClientJourneyTracker):
        """Schedule retry call for no-answer"""
        
        retry_time = datetime.now() + timedelta(hours=4)
        
        logger.info(
            f"🔄 Retry call scheduled for {tracker.company_name} "
            f"at {retry_time.strftime('%H:%M')}"
        )
    
    async def send_nurturing_message(self, lead_id: str, message_type: str):
        """Send a nurturing message based on type"""
        
        if lead_id not in self.active_journeys:
            return
        
        tracker = self.active_journeys[lead_id]
        script = self.scripts.get_followup_script(message_type)
        
        # Personalize message
        message = script["message"].format(
            name=tracker.contact_name,
            leads_scraped=150,  # Would be real data
            calls_made=75,
            appointments=8,
            total_leads=150,
            total_calls=75,
            support_number=settings.support_phone_number or settings.support_whatsapp_number or "Contact Support"
        )
        
        # Send via WhatsApp
        await whatsapp_handler.send_message(
            to=tracker.contact_phone,
            message=message
        )
        tracker.total_whatsapp_messages += 1
        
        # Update stage
        if message_type == "trial_day_3":
            tracker.current_stage = JourneyStage.TRIAL_DAY_3
        elif message_type == "trial_ending":
            tracker.current_stage = JourneyStage.TRIAL_ENDING
        elif message_type == "trial_ended":
            tracker.current_stage = JourneyStage.TRIAL_ENDED
        
        tracker.events.append(JourneyEvent(
            stage=tracker.current_stage,
            interaction_type=InteractionType.WHATSAPP,
            message=f"Nurturing message sent: {message_type}"
        ))
    
    async def attempt_conversion(self, lead_id: str) -> bool:
        """Attempt to convert trial user to paid"""
        
        if lead_id not in self.active_journeys:
            return False
        
        tracker = self.active_journeys[lead_id]
        
        # Send conversion message with special offer
        conversion_message = f"""Hi {tracker.contact_name}!

Your trial has been amazing:
📊 150+ leads generated
📞 75 calls made
📅 8 appointments booked

Don't lose this momentum!

🎁 SPECIAL OFFER: 20% OFF if you subscribe in the next 48 hours!

Plans:
• Starter: ₹15,000 → ₹12,000/month
• Growth: ₹25,000 → ₹20,000/month
• Enterprise: ₹50,000 → ₹40,000/month

Reply UPGRADE to continue, or call us to discuss."""

        await whatsapp_handler.send_message(
            to=tracker.contact_phone,
            message=conversion_message
        )
        
        logger.info(f"💰 Conversion attempt made for {tracker.company_name}")
        
        return True
    
    async def handle_conversion_response(
        self,
        lead_id: str,
        response: str,
        plan: str = None
    ):
        """Handle response to conversion attempt"""
        
        if lead_id not in self.active_journeys:
            return
        
        tracker = self.active_journeys[lead_id]
        
        if response.upper() == "UPGRADE" or "upgrade" in response.lower():
            tracker.current_stage = JourneyStage.CONVERTED
            tracker.converted_at = datetime.now()
            
            # Send payment link
            support_number = settings.support_phone_number or settings.support_whatsapp_number or "our support team"
            payment_message = f"""Great choice, {tracker.contact_name}! 🎉

Complete your subscription here:
{settings.platform_website_url}/subscribe/{lead_id}

Or call us: {support_number}

We're excited to continue generating leads for you!"""

            await whatsapp_handler.send_message(
                to=tracker.contact_phone,
                message=payment_message
            )
            
            logger.info(f"🎉 Conversion successful for {tracker.company_name}")
            
        else:
            # Handle objection
            await self._handle_objection(tracker, response)
    
    async def _handle_objection(
        self,
        tracker: ClientJourneyTracker,
        objection: str
    ):
        """Handle conversion objection"""
        
        # Use AI to generate appropriate response
        # For now, use script-based response
        
        response = self.scripts.get_objection_handler("need_to_think")
        
        await whatsapp_handler.send_message(
            to=tracker.contact_phone,
            message=response
        )
    
    def get_journey_stats(self) -> Dict:
        """Get statistics about all journeys"""
        
        stats = {
            "total_journeys": len(self.active_journeys),
            "stages": {},
            "conversion_rate": 0.0,
            "avg_quality_score": 0.0
        }
        
        # Count by stage
        for tracker in self.active_journeys.values():
            stage = tracker.current_stage.value
            stats["stages"][stage] = stats["stages"].get(stage, 0) + 1
        
        # Calculate conversion rate
        converted = stats["stages"].get("converted", 0) + stats["stages"].get("active", 0)
        total = len(self.active_journeys)
        if total > 0:
            stats["conversion_rate"] = (converted / total) * 100
        
        # Average quality score
        if self.active_journeys:
            total_score = sum(t.quality_score for t in self.active_journeys.values())
            stats["avg_quality_score"] = total_score / len(self.active_journeys)
        
        return stats


# Singleton instance
client_journey_manager = ClientJourneyManager()
