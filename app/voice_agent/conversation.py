"""
Conversation Manager
Manages conversation state and flow for voice calls
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationState(Enum):
    """States in the conversation flow"""
    OPENING = "opening"
    INTRODUCTION = "introduction"
    QUALIFICATION = "qualification"
    OBJECTION_HANDLING = "objection_handling"
    APPOINTMENT_BOOKING = "appointment_booking"
    CALLBACK_SCHEDULING = "callback_scheduling"
    CLOSING = "closing"
    ENDED = "ended"


class QualificationStage(Enum):
    """Stages of lead qualification"""
    NOT_STARTED = "not_started"
    DECISION_MAKER = "decision_maker"
    CURRENT_SITUATION = "current_situation"
    PAIN_POINTS = "pain_points"
    BUDGET = "budget"
    TIMELINE = "timeline"
    COMPLETED = "completed"


@dataclass
class ConversationTurn:
    """Single turn in conversation"""
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: Optional[str] = None
    entities: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationContext:
    """Full conversation context"""
    call_id: str
    state: ConversationState = ConversationState.OPENING
    qualification_stage: QualificationStage = QualificationStage.NOT_STARTED
    turns: List[ConversationTurn] = field(default_factory=list)
    qualification_data: Dict[str, Any] = field(default_factory=dict)
    objections_encountered: List[str] = field(default_factory=list)
    appointment_details: Optional[Dict[str, Any]] = None
    callback_time: Optional[str] = None
    lead_score: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None


class ConversationManager:
    """
    Manages conversation state machine and flow
    """
    
    # State transitions
    STATE_TRANSITIONS = {
        ConversationState.OPENING: [
            ConversationState.INTRODUCTION,
            ConversationState.ENDED
        ],
        ConversationState.INTRODUCTION: [
            ConversationState.QUALIFICATION,
            ConversationState.OBJECTION_HANDLING,
            ConversationState.ENDED
        ],
        ConversationState.QUALIFICATION: [
            ConversationState.APPOINTMENT_BOOKING,
            ConversationState.OBJECTION_HANDLING,
            ConversationState.CALLBACK_SCHEDULING,
            ConversationState.CLOSING
        ],
        ConversationState.OBJECTION_HANDLING: [
            ConversationState.QUALIFICATION,
            ConversationState.APPOINTMENT_BOOKING,
            ConversationState.CALLBACK_SCHEDULING,
            ConversationState.CLOSING,
            ConversationState.ENDED
        ],
        ConversationState.APPOINTMENT_BOOKING: [
            ConversationState.CLOSING,
            ConversationState.QUALIFICATION
        ],
        ConversationState.CALLBACK_SCHEDULING: [
            ConversationState.CLOSING
        ],
        ConversationState.CLOSING: [
            ConversationState.ENDED
        ]
    }
    
    # Qualification flow
    QUALIFICATION_FLOW = [
        QualificationStage.DECISION_MAKER,
        QualificationStage.CURRENT_SITUATION,
        QualificationStage.PAIN_POINTS,
        QualificationStage.BUDGET,
        QualificationStage.TIMELINE,
        QualificationStage.COMPLETED
    ]
    
    def __init__(self):
        self.conversations: Dict[str, ConversationContext] = {}
        logger.info("💬 Conversation Manager initialized")
    
    def start_conversation(self, call_id: str) -> ConversationContext:
        """Start a new conversation"""
        context = ConversationContext(call_id=call_id)
        self.conversations[call_id] = context
        logger.info(f"Started conversation for call {call_id}")
        return context
    
    def get_conversation(self, call_id: str) -> Optional[ConversationContext]:
        """Get conversation by call ID"""
        return self.conversations.get(call_id)
    
    def add_turn(
        self,
        call_id: str,
        role: str,
        content: str,
        intent: Optional[str] = None,
        entities: Optional[Dict[str, Any]] = None
    ) -> ConversationContext:
        """Add a turn to the conversation"""
        context = self.conversations.get(call_id)
        if not context:
            raise ValueError(f"Conversation {call_id} not found")
        
        turn = ConversationTurn(
            role=role,
            content=content,
            intent=intent,
            entities=entities or {}
        )
        context.turns.append(turn)
        
        # Update state based on intent
        if intent:
            self._update_state(context, intent, entities or {})
        
        return context
    
    def _update_state(
        self,
        context: ConversationContext,
        intent: str,
        entities: Dict[str, Any]
    ):
        """Update conversation state based on detected intent"""
        current_state = context.state
        
        # State transition logic
        if intent == "interested" and current_state == ConversationState.INTRODUCTION:
            context.state = ConversationState.QUALIFICATION
            
        elif intent == "appointment_interest":
            context.state = ConversationState.APPOINTMENT_BOOKING
            
        elif intent == "callback_request":
            context.state = ConversationState.CALLBACK_SCHEDULING
            if "time_mention" in entities:
                context.callback_time = entities["time_mention"]
                
        elif intent in ["not_interested", "opt_out"]:
            context.state = ConversationState.CLOSING
            
        elif intent == "objection":
            context.objections_encountered.append(entities.get("objection_type", "unknown"))
            context.state = ConversationState.OBJECTION_HANDLING
        
        # Update qualification stage
        self._update_qualification(context, intent, entities)
    
    def _update_qualification(
        self,
        context: ConversationContext,
        intent: str,
        entities: Dict[str, Any]
    ):
        """Update qualification data based on conversation"""
        if context.state != ConversationState.QUALIFICATION:
            return
        
        # Extract qualification data from entities
        if "is_decision_maker" in entities:
            context.qualification_data["is_decision_maker"] = entities["is_decision_maker"]
            context.qualification_stage = QualificationStage.CURRENT_SITUATION
            
        if "current_provider" in entities:
            context.qualification_data["current_provider"] = entities["current_provider"]
            context.qualification_stage = QualificationStage.PAIN_POINTS
            
        if "pain_points" in entities:
            context.qualification_data["pain_points"] = entities["pain_points"]
            context.qualification_stage = QualificationStage.BUDGET
            
        if "budget" in entities:
            context.qualification_data["budget"] = entities["budget"]
            context.qualification_stage = QualificationStage.TIMELINE
            
        if "timeline" in entities:
            context.qualification_data["timeline"] = entities["timeline"]
            context.qualification_stage = QualificationStage.COMPLETED
        
        # Update lead score
        self._calculate_lead_score(context)
    
    def _calculate_lead_score(self, context: ConversationContext) -> int:
        """Calculate lead score based on qualification data"""
        score = 0
        data = context.qualification_data
        
        # Decision maker check
        if data.get("is_decision_maker") is True:
            score += 25
        elif data.get("is_decision_maker") is False:
            score += 10  # Still valuable, just need to reach DM
        
        # Has budget
        if data.get("budget"):
            score += 25
        
        # Has timeline
        if data.get("timeline"):
            score += 20
            if "urgent" in str(data.get("timeline", "")).lower():
                score += 10
        
        # Pain points identified
        if data.get("pain_points"):
            score += 15
        
        # Appointment scheduled
        if context.appointment_details:
            score += 30
        
        # Callback scheduled
        if context.callback_time:
            score += 15
        
        # Objection count penalty
        score -= len(context.objections_encountered) * 5
        
        context.lead_score = max(0, min(100, score))
        return context.lead_score
    
    def get_next_question(self, call_id: str) -> Optional[str]:
        """Get next qualification question based on stage"""
        context = self.conversations.get(call_id)
        if not context:
            return None
        
        questions = {
            QualificationStage.NOT_STARTED: "Are you the right person to discuss this with, or should I speak with someone else?",
            QualificationStage.DECISION_MAKER: "What solution are you currently using for this?",
            QualificationStage.CURRENT_SITUATION: "What challenges are you facing with your current approach?",
            QualificationStage.PAIN_POINTS: "Do you have a budget allocated for this kind of solution?",
            QualificationStage.BUDGET: "What's your timeline for making a decision?",
            QualificationStage.TIMELINE: None,  # Qualification complete
        }
        
        return questions.get(context.qualification_stage)
    
    def end_conversation(self, call_id: str) -> Optional[ConversationContext]:
        """End a conversation and return summary"""
        context = self.conversations.get(call_id)
        if not context:
            return None
        
        context.state = ConversationState.ENDED
        context.ended_at = datetime.now()
        
        # Calculate final score
        self._calculate_lead_score(context)
        
        logger.info(f"Ended conversation {call_id}. Score: {context.lead_score}")
        return context
    
    def get_conversation_summary(self, call_id: str) -> Dict[str, Any]:
        """Get conversation summary for CRM/reporting"""
        context = self.conversations.get(call_id)
        if not context:
            return {}
        
        duration = None
        if context.ended_at and context.started_at:
            duration = (context.ended_at - context.started_at).total_seconds()
        
        return {
            "call_id": call_id,
            "state": context.state.value,
            "lead_score": context.lead_score,
            "qualification_data": context.qualification_data,
            "qualification_stage": context.qualification_stage.value,
            "appointment_scheduled": context.appointment_details is not None,
            "appointment_details": context.appointment_details,
            "callback_scheduled": context.callback_time is not None,
            "callback_time": context.callback_time,
            "objections_count": len(context.objections_encountered),
            "objections": context.objections_encountered,
            "turn_count": len(context.turns),
            "duration_seconds": duration,
            "transcript": [
                {"role": t.role, "content": t.content, "intent": t.intent}
                for t in context.turns
            ]
        }
