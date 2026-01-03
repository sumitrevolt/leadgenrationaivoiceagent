"""
Hot Lead Call Transfer System
Transfers high-intent leads to human sales reps in real-time

When AI detects a hot lead (high intent to buy), it can:
1. Transfer call to available sales rep
2. Add sales rep to the call (conference)
3. Schedule immediate callback from sales rep
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import random

from app.config import settings
from app.utils.logger import setup_logger
from app.integrations.whatsapp import WhatsAppIntegration

logger = setup_logger(__name__)


class TransferType(Enum):
    """Type of call transfer"""
    WARM_TRANSFER = "warm_transfer"  # AI briefs rep, then transfers
    BLIND_TRANSFER = "blind_transfer"  # Direct transfer without brief
    CONFERENCE = "conference"  # Add rep to call, AI stays
    CALLBACK = "callback"  # Schedule immediate callback


class TransferReason(Enum):
    """Why the transfer was triggered"""
    HIGH_INTENT = "high_intent"
    REQUESTED_HUMAN = "requested_human"
    COMPLEX_QUERY = "complex_query"
    READY_TO_BUY = "ready_to_buy"
    APPOINTMENT_CONFIRMED = "appointment_confirmed"
    VIP_LEAD = "vip_lead"


@dataclass
class SalesRep:
    """Sales representative"""
    id: str
    name: str
    phone: str
    email: str
    extension: str  # For call transfer
    specializations: List[str]  # Industries they handle
    is_available: bool = True
    current_calls: int = 0
    max_concurrent_calls: int = 2
    daily_transfers_received: int = 0
    
    # Performance metrics
    total_transfers: int = 0
    successful_closes: int = 0
    avg_response_time_seconds: float = 0
    
    def availability_score(self) -> float:
        """Calculate availability score for routing"""
        if not self.is_available:
            return 0
        
        # Lower current calls = higher score
        call_score = (self.max_concurrent_calls - self.current_calls) / self.max_concurrent_calls
        
        # Success rate factor
        success_rate = self.successful_closes / max(self.total_transfers, 1)
        
        return (call_score * 0.6) + (success_rate * 0.4)


@dataclass
class TransferRequest:
    """Request to transfer a call"""
    call_id: str
    lead_id: str
    phone_number: str
    lead_name: str
    company_name: Optional[str]
    industry: str
    transfer_type: TransferType
    reason: TransferReason
    lead_score: int
    qualification_data: Dict[str, Any]
    conversation_summary: str
    urgency_level: str  # low, medium, high, critical
    
    # Transfer status
    status: str = "pending"  # pending, in_progress, completed, failed
    assigned_rep: Optional[SalesRep] = None
    created_at: datetime = field(default_factory=datetime.now)
    transferred_at: Optional[datetime] = None


class HotLeadDetector:
    """
    Detects hot leads based on conversation signals
    """
    
    # Signals that indicate high intent
    HIGH_INTENT_SIGNALS = [
        "ready to buy",
        "want to purchase",
        "send the invoice",
        "when can we start",
        "what's the price",
        "final cost",
        "sign the deal",
        "proceed with",
        "let's do it",
        "book it",
        "confirm the order",
        "payment terms",
        "contract",
        "when can you deliver",
    ]
    
    # Signals for requesting human
    HUMAN_REQUEST_SIGNALS = [
        "talk to a human",
        "speak to someone",
        "real person",
        "manager",
        "sales person",
        "representative",
        "transfer me",
        "not a robot",
    ]
    
    # Budget mentions that indicate serious intent
    BUDGET_SIGNALS = [
        "budget is",
        "can spend",
        "allocated",
        "approved budget",
        "we have funds",
    ]
    
    def detect_hot_lead(
        self,
        conversation_history: List[Dict[str, str]],
        qualification_data: Dict[str, Any],
        lead_score: int
    ) -> Dict[str, Any]:
        """
        Analyze conversation to detect if this is a hot lead
        
        Returns:
            {
                "is_hot": bool,
                "confidence": float,
                "reason": TransferReason,
                "urgency": str,
                "signals_detected": List[str]
            }
        """
        signals_found = []
        reason = None
        
        # Combine all user messages
        user_text = " ".join([
            turn["content"].lower() 
            for turn in conversation_history 
            if turn["role"] == "user"
        ])
        
        # Check for high intent signals
        for signal in self.HIGH_INTENT_SIGNALS:
            if signal in user_text:
                signals_found.append(f"high_intent: {signal}")
                reason = TransferReason.READY_TO_BUY
        
        # Check for human request
        for signal in self.HUMAN_REQUEST_SIGNALS:
            if signal in user_text:
                signals_found.append(f"human_request: {signal}")
                reason = TransferReason.REQUESTED_HUMAN
        
        # Check for budget mention
        for signal in self.BUDGET_SIGNALS:
            if signal in user_text:
                signals_found.append(f"budget_mention: {signal}")
        
        # Check qualification data
        if qualification_data.get("is_decision_maker") is True:
            signals_found.append("is_decision_maker")
        
        if qualification_data.get("budget"):
            signals_found.append("has_budget")
        
        if qualification_data.get("timeline"):
            if any(word in str(qualification_data["timeline"]).lower() 
                   for word in ["urgent", "asap", "immediately", "this week", "today"]):
                signals_found.append("urgent_timeline")
                reason = reason or TransferReason.HIGH_INTENT
        
        # Calculate confidence
        confidence = len(signals_found) / 10  # Max 10 signals = 100% confidence
        confidence = min(confidence, 1.0)
        
        # Add lead score to confidence
        if lead_score >= 80:
            confidence = min(confidence + 0.3, 1.0)
            signals_found.append("high_lead_score")
        elif lead_score >= 60:
            confidence = min(confidence + 0.1, 1.0)
        
        # Determine if hot lead
        is_hot = confidence >= 0.5 or reason == TransferReason.REQUESTED_HUMAN
        
        # Determine urgency
        if reason == TransferReason.REQUESTED_HUMAN:
            urgency = "critical"
        elif reason == TransferReason.READY_TO_BUY:
            urgency = "high"
        elif confidence >= 0.7:
            urgency = "high"
        elif confidence >= 0.5:
            urgency = "medium"
        else:
            urgency = "low"
        
        return {
            "is_hot": is_hot,
            "confidence": confidence,
            "reason": reason or TransferReason.HIGH_INTENT,
            "urgency": urgency,
            "signals_detected": signals_found
        }


class CallTransferManager:
    """
    Manages call transfers to sales reps
    """
    
    def __init__(self):
        self.sales_reps: Dict[str, SalesRep] = {}
        self.pending_transfers: Dict[str, TransferRequest] = {}
        self.hot_lead_detector = HotLeadDetector()
        self.whatsapp = WhatsAppIntegration()
        
        # Load sales reps (in production, load from database)
        self._load_default_reps()
        
        logger.info("📞 Call Transfer Manager initialized")
    
    def _load_default_reps(self):
        """Load default sales reps (demo data)"""
        default_reps = [
            SalesRep(
                id="rep_001",
                name="Rahul Sharma",
                phone="+919876543210",
                email="rahul@company.com",
                extension="101",
                specializations=["real_estate", "solar", "insurance"],
                is_available=True
            ),
            SalesRep(
                id="rep_002",
                name="Priya Patel",
                phone="+919876543211",
                email="priya@company.com",
                extension="102",
                specializations=["coaching", "healthcare", "edtech"],
                is_available=True
            ),
            SalesRep(
                id="rep_003",
                name="Amit Kumar",
                phone="+919876543212",
                email="amit@company.com",
                extension="103",
                specializations=["real_estate", "solar", "digital_marketing"],
                is_available=True
            ),
        ]
        
        for rep in default_reps:
            self.sales_reps[rep.id] = rep
    
    def add_sales_rep(self, rep: SalesRep):
        """Add a sales rep to the pool"""
        self.sales_reps[rep.id] = rep
    
    def set_rep_availability(self, rep_id: str, is_available: bool):
        """Set availability of a sales rep"""
        if rep_id in self.sales_reps:
            self.sales_reps[rep_id].is_available = is_available
    
    def find_best_rep(self, industry: str) -> Optional[SalesRep]:
        """
        Find best available sales rep for the industry
        Uses availability score and specialization matching
        """
        eligible_reps = []
        
        for rep in self.sales_reps.values():
            if not rep.is_available:
                continue
            if rep.current_calls >= rep.max_concurrent_calls:
                continue
            
            # Check specialization match
            specialization_match = industry in rep.specializations
            score = rep.availability_score()
            
            if specialization_match:
                score += 0.3  # Boost for specialization
            
            eligible_reps.append((rep, score))
        
        if not eligible_reps:
            return None
        
        # Sort by score descending
        eligible_reps.sort(key=lambda x: x[1], reverse=True)
        return eligible_reps[0][0]
    
    async def check_for_transfer(
        self,
        call_id: str,
        lead_id: str,
        phone_number: str,
        lead_name: str,
        company_name: Optional[str],
        industry: str,
        conversation_history: List[Dict[str, str]],
        qualification_data: Dict[str, Any],
        lead_score: int
    ) -> Optional[TransferRequest]:
        """
        Check if call should be transferred based on conversation
        Returns TransferRequest if transfer is needed
        """
        # Detect if this is a hot lead
        detection = self.hot_lead_detector.detect_hot_lead(
            conversation_history,
            qualification_data,
            lead_score
        )
        
        if not detection["is_hot"]:
            return None
        
        logger.info(f"🔥 Hot lead detected! Call {call_id}, Confidence: {detection['confidence']}")
        logger.info(f"   Signals: {detection['signals_detected']}")
        
        # Create transfer request
        transfer = TransferRequest(
            call_id=call_id,
            lead_id=lead_id,
            phone_number=phone_number,
            lead_name=lead_name,
            company_name=company_name,
            industry=industry,
            transfer_type=TransferType.WARM_TRANSFER,
            reason=detection["reason"],
            lead_score=lead_score,
            qualification_data=qualification_data,
            conversation_summary=self._create_summary(conversation_history),
            urgency_level=detection["urgency"]
        )
        
        # Find best rep
        rep = self.find_best_rep(industry)
        if rep:
            transfer.assigned_rep = rep
            self.pending_transfers[call_id] = transfer
            
            # Notify rep
            await self._notify_rep(rep, transfer)
        
        return transfer
    
    def _create_summary(self, conversation_history: List[Dict[str, str]]) -> str:
        """Create brief summary of conversation for sales rep"""
        # Get last 6 turns
        recent = conversation_history[-6:]
        
        summary_parts = []
        for turn in recent:
            role = "Lead" if turn["role"] == "user" else "AI"
            content = turn["content"][:100]  # Truncate
            summary_parts.append(f"{role}: {content}")
        
        return "\n".join(summary_parts)
    
    async def _notify_rep(self, rep: SalesRep, transfer: TransferRequest):
        """Notify sales rep about incoming transfer"""
        message = f"""🔥 *HOT LEAD ALERT*

*Lead:* {transfer.lead_name}
*Company:* {transfer.company_name or 'N/A'}
*Industry:* {transfer.industry}
*Lead Score:* {transfer.lead_score}/100
*Urgency:* {transfer.urgency_level.upper()}

*Qualification:*
{self._format_qualification(transfer.qualification_data)}

*Conversation Summary:*
{transfer.conversation_summary[:500]}

*Transfer Reason:* {transfer.reason.value}

📞 *Call will be transferred to you shortly*
Reply 'READY' to confirm availability."""
        
        try:
            await self.whatsapp.send_text_message(rep.phone, message)
            logger.info(f"📱 Notified {rep.name} about transfer")
        except Exception as e:
            logger.error(f"Failed to notify rep: {e}")
    
    def _format_qualification(self, data: Dict[str, Any]) -> str:
        """Format qualification data for message"""
        lines = []
        if data.get("is_decision_maker"):
            lines.append("✅ Decision Maker: Yes")
        if data.get("budget"):
            lines.append(f"💰 Budget: {data['budget']}")
        if data.get("timeline"):
            lines.append(f"⏰ Timeline: {data['timeline']}")
        if data.get("pain_points"):
            lines.append(f"❗ Pain Points: {data['pain_points']}")
        
        return "\n".join(lines) if lines else "Basic qualification done"
    
    async def execute_transfer(
        self,
        call_id: str,
        transfer_type: TransferType = TransferType.WARM_TRANSFER
    ) -> Dict[str, Any]:
        """
        Execute the call transfer
        Returns transfer status and details
        """
        transfer = self.pending_transfers.get(call_id)
        if not transfer:
            return {"success": False, "error": "No pending transfer"}
        
        if not transfer.assigned_rep:
            return {"success": False, "error": "No rep assigned"}
        
        rep = transfer.assigned_rep
        transfer.status = "in_progress"
        
        # In production, this would use telephony API to transfer
        # For now, return the transfer details
        
        result = {
            "success": True,
            "transfer_type": transfer_type.value,
            "rep": {
                "name": rep.name,
                "phone": rep.phone,
                "extension": rep.extension
            },
            "lead": {
                "name": transfer.lead_name,
                "phone": transfer.phone_number,
                "score": transfer.lead_score
            }
        }
        
        # Update rep status
        rep.current_calls += 1
        rep.total_transfers += 1
        transfer.status = "completed"
        transfer.transferred_at = datetime.now()
        
        logger.info(f"✅ Transfer completed: {call_id} -> {rep.name}")
        
        return result
    
    def get_transfer_message(self, transfer: TransferRequest) -> str:
        """
        Get message to speak before transfer
        This is what AI says to the lead before transferring
        """
        rep_name = transfer.assigned_rep.name if transfer.assigned_rep else "our specialist"
        
        messages = {
            TransferReason.READY_TO_BUY: f"""Sir, aap ready hain proceed karne ke liye - bahut achhi baat hai! 
Main aapko {rep_name} se connect kar raha hoon jo aapki process complete karenge. 
Ek second hold karein.""",
            
            TransferReason.REQUESTED_HUMAN: f"""Bilkul sir, main aapko humare specialist {rep_name} se connect kar raha hoon. 
Wo aapki saari queries personally handle karenge. 
Ek second please.""",
            
            TransferReason.HIGH_INTENT: f"""Sir, aapki requirements sun ke lagta hai aap serious hain. 
Main aapko {rep_name} se connect kar raha hoon jo aapke liye best solution discuss karenge.
Hold please.""",
            
            TransferReason.COMPLEX_QUERY: f"""Yeh ek detailed question hai sir. Main aapko humare expert {rep_name} se connect kar raha hoon.
Wo properly explain kar denge. One moment please.""",
            
            TransferReason.VIP_LEAD: f"""Sir, main aapko humare senior specialist {rep_name} se connect kar raha hoon.
Wo personally aapki requirement handle karenge. Please hold.""",
            
            TransferReason.APPOINTMENT_CONFIRMED: f"""Appointment confirm ho gayi hai sir! Main aapko {rep_name} se connect kar raha hoon 
jo final details confirm karenge. One moment."""
        }
        
        return messages.get(transfer.reason, messages[TransferReason.HIGH_INTENT])
    
    def get_handoff_brief(self, transfer: TransferRequest) -> str:
        """
        Get brief for sales rep when call connects
        This is spoken to the rep before connecting to lead
        """
        return f"""Connecting you with {transfer.lead_name}. 
They're interested in {transfer.industry}. 
Lead score {transfer.lead_score}. 
They mentioned: {transfer.qualification_data.get('pain_points', 'general interest')}.
Transferring now."""


class TransferAnalytics:
    """
    Track and analyze transfer performance
    """
    
    def __init__(self):
        self.transfers: List[TransferRequest] = []
    
    def record_transfer(self, transfer: TransferRequest):
        """Record a transfer for analytics"""
        self.transfers.append(transfer)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get transfer metrics"""
        total = len(self.transfers)
        if total == 0:
            return {"total_transfers": 0}
        
        completed = sum(1 for t in self.transfers if t.status == "completed")
        
        return {
            "total_transfers": total,
            "completed": completed,
            "success_rate": completed / total,
            "by_reason": self._count_by_reason(),
            "by_industry": self._count_by_industry(),
            "avg_lead_score": sum(t.lead_score for t in self.transfers) / total
        }
    
    def _count_by_reason(self) -> Dict[str, int]:
        """Count transfers by reason"""
        counts = {}
        for t in self.transfers:
            reason = t.reason.value
            counts[reason] = counts.get(reason, 0) + 1
        return counts
    
    def _count_by_industry(self) -> Dict[str, int]:
        """Count transfers by industry"""
        counts = {}
        for t in self.transfers:
            counts[t.industry] = counts.get(t.industry, 0) + 1
        return counts


# Global instances
call_transfer_manager = CallTransferManager()
transfer_analytics = TransferAnalytics()
