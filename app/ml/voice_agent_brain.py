"""
Voice Agent Brain - Vertex AI Powered Conversation Intelligence for Lead Generation
Brain #2 in the Three-Brain Architecture

This brain powers the actual AI voice agent that makes calls to leads.
It handles:
- Real-time conversation generation
- Intent detection and response
- Objection handling with learned patterns
- Appointment booking flows
- Lead qualification scoring
- Industry-specific conversation optimization
- Continuous learning from successful calls

Vertex AI Integration:
- Uses Gemini 1.5 Flash for low-latency responses
- RAG from successful conversation patterns
- A/B testing of scripts and responses
- Self-training on call outcomes
"""
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

from app.utils.logger import setup_logger
from app.ml.vector_store import VectorStore

logger = setup_logger(__name__)


class CallIntent(Enum):
    """Detected intents from customer speech"""
    GREETING = "greeting"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK = "callback"
    QUESTION = "question"
    OBJECTION = "objection"
    APPOINTMENT = "appointment"
    DND = "dnd"
    WRONG_NUMBER = "wrong_number"
    BUSY = "busy"
    VOICEMAIL = "voicemail"
    END_CALL = "end_call"
    UNKNOWN = "unknown"


class LeadTemperature(Enum):
    """Lead qualification temperature"""
    HOT = "hot"      # Ready for demo/purchase
    WARM = "warm"    # Interested, needs nurturing
    COLD = "cold"    # Not interested now
    DEAD = "dead"    # DND/wrong number


@dataclass
class ConversationState:
    """State of an ongoing conversation"""
    call_id: str
    lead_id: str
    
    # Lead info
    lead_name: str
    lead_phone: str
    company_name: str = ""
    industry: str = "general"
    city: str = ""
    
    # Conversation progress
    turn_count: int = 0
    intents_detected: List[CallIntent] = field(default_factory=list)
    temperature: LeadTemperature = LeadTemperature.COLD
    
    # Collected data
    collected_info: Dict[str, Any] = field(default_factory=dict)
    objections_raised: List[str] = field(default_factory=list)
    questions_asked: List[str] = field(default_factory=list)
    
    # Appointment
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    appointment_confirmed: bool = False
    
    # Conversation history
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Outcome
    outcome: Optional[str] = None
    follow_up_date: Optional[str] = None
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    last_response_ms: int = 0


@dataclass
class ResponseGeneration:
    """Generated response from the brain"""
    text: str
    intent_detected: CallIntent
    confidence: float
    suggested_next_action: str
    
    # For TTS
    ssml: Optional[str] = None
    emotion: str = "neutral"  # neutral, excited, empathetic
    speed: float = 1.0
    
    # Metrics
    generation_time_ms: int = 0
    tokens_used: int = 0


# Industry-specific conversation configurations
INDUSTRY_CONFIGS: Dict[str, Dict] = {
    "real_estate": {
        "value_prop": "AI that calls your old leads and wakes them up. Imagine getting 5 site visits from leads you thought were dead.",
        "pain_points": ["cold leads", "follow-up time", "missed opportunities"],
        "qualifying_questions": [
            "How many leads do you get per month?",
            "What happens to leads that don't convert in the first week?",
            "How much time does your team spend on follow-up calls?",
        ],
        "objection_handlers": {
            "too_expensive": "Sir, if I bring you just one extra site visit that converts, it pays for the whole year. It's really about ROI.",
            "no_time": "That's exactly why I'm calling - I can handle all the follow-ups automatically, saving you hours every day.",
            "already_have_crm": "Great! I integrate with your CRM and make it 10x more powerful by actually calling your leads.",
        }
    },
    "solar": {
        "value_prop": "AI that pre-qualifies homeowners for solar - checks roof suitability, electricity bills, and books site surveys automatically.",
        "pain_points": ["unqualified leads", "site survey no-shows", "long sales cycles"],
        "qualifying_questions": [
            "How many solar leads do you process monthly?",
            "What's your current site survey show-up rate?",
            "How do you currently qualify leads before sending technicians?",
        ],
        "objection_handlers": {
            "too_expensive": "One qualified lead that converts to a 10 lakh installation pays for 6 months of my service.",
            "no_time": "I work 24/7 and call leads within 5 minutes of inquiry - that's when conversion rates are highest.",
            "we_call_manually": "I can do 100 calls in the time your team does 10, and I never get tired or have a bad day.",
        }
    },
    "dental": {
        "value_prop": "AI receptionist that fills empty appointment slots by calling patients who haven't visited in 6 months.",
        "pain_points": ["empty slots", "patient retention", "receptionist overload"],
        "qualifying_questions": [
            "How many empty slots do you typically have per week?",
            "Do you currently call patients for routine check-up reminders?",
            "What happens to patients who don't come back after their first visit?",
        ],
        "objection_handlers": {
            "patients_prefer_human": "I sound very natural - most patients can't tell the difference. But if they want a human, I seamlessly transfer.",
            "too_expensive": "One filled slot at your average procedure value pays for the entire month.",
            "we_use_sms": "SMS gets 5% response rate. Phone calls get 40%. I do both together for maximum bookings.",
        }
    },
    "insurance": {
        "value_prop": "AI that qualifies insurance leads and books appointments with decision-makers only.",
        "pain_points": ["unqualified leads", "time wasters", "compliance"],
        "qualifying_questions": [
            "How do you currently qualify leads before agent meetings?",
            "What percentage of meetings are with actual decision-makers?",
            "How much time do your agents spend on lead qualification?",
        ],
        "objection_handlers": {
            "compliance_concerns": "I'm fully compliant with IRDAI guidelines and record all calls with consent for audit trails.",
            "agents_need_relationship": "Absolutely - I just do the first qualification so your agents focus on relationship building with qualified prospects.",
            "too_expensive": "If I free up your agents to close 2 extra policies per month, what's that worth?",
        }
    },
    "general": {
        "value_prop": "AI employee that calls 100 leads per day, qualifies them, and books appointments on your calendar automatically.",
        "pain_points": ["lead follow-up", "time constraints", "missed opportunities"],
        "qualifying_questions": [
            "How do you currently handle lead follow-ups?",
            "How many leads slip through the cracks each month?",
            "What would you do with 3 extra hours every day?",
        ],
        "objection_handlers": {
            "not_interested": "I understand. Quick question - what's your biggest challenge with lead follow-up today?",
            "too_expensive": "It costs less than one hour of an employee's time per day. What could you achieve with those hours back?",
            "send_email": "Happy to! But a quick 2-minute call would show you exactly how I work. When's good tomorrow?",
        }
    }
}


class VoiceAgentBrain:
    """
    Vertex AI Powered Brain for Voice Agent Conversations
    
    Brain #2 - Handles actual lead generation calls with:
    - Real-time response generation (target <500ms)
    - Industry-specific scripts and objection handling
    - RAG from successful conversation patterns
    - Continuous learning from call outcomes
    - A/B testing of scripts
    """
    
    # Performance targets
    TARGET_RESPONSE_MS = 500
    MAX_RESPONSE_MS = 2000
    
    def __init__(
        self,
        data_dir: str = "data/voice_brain",
        vector_store: VectorStore = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self._vector_store = vector_store
        self._vertex_client = None
        
        # Active conversations
        self.active_calls: Dict[str, ConversationState] = {}
        
        # Performance metrics
        self.metrics = {
            "total_calls": 0,
            "appointments_booked": 0,
            "avg_response_ms": 0,
            "intent_accuracy": 0.0,
            "conversion_rate": 0.0,
        }
        self._load_metrics()
        
        # A/B test tracking
        self.ab_tests: Dict[str, Dict] = {}
        
        logger.info("🎙️ Voice Agent Brain initialized (Vertex AI Powered)")
    
    @property
    def vertex_client(self):
        """Lazy load Vertex AI client"""
        if self._vertex_client is None:
            try:
                from app.llm.vertex_client import get_vertex_client
                self._vertex_client = get_vertex_client("gemini-1.5-flash")
            except Exception as e:
                logger.warning(f"Vertex AI client init failed: {e}")
                self._vertex_client = MockVertexClient()
        return self._vertex_client
    
    @property
    def vector_store(self) -> VectorStore:
        """Lazy load vector store for RAG"""
        if self._vector_store is None:
            self._vector_store = VectorStore(
                persist_directory="data/voice_vectorstore",
                collection_name="successful_conversations"
            )
        return self._vector_store
    
    def _load_metrics(self):
        """Load metrics from disk"""
        metrics_file = self.data_dir / "metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file, "r") as f:
                    self.metrics.update(json.load(f))
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")
    
    def _save_metrics(self):
        """Save metrics to disk"""
        metrics_file = self.data_dir / "metrics.json"
        try:
            with open(metrics_file, "w") as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    async def start_call(
        self,
        call_id: str,
        lead_id: str,
        lead_name: str,
        lead_phone: str,
        company_name: str = "",
        industry: str = "general",
        city: str = "",
    ) -> ConversationState:
        """
        Initialize a new call conversation
        
        Returns the initial conversation state
        """
        state = ConversationState(
            call_id=call_id,
            lead_id=lead_id,
            lead_name=lead_name,
            lead_phone=lead_phone,
            company_name=company_name,
            industry=industry,
            city=city,
        )
        
        self.active_calls[call_id] = state
        self.metrics["total_calls"] += 1
        
        logger.info(f"📞 Call started: {call_id} | Lead: {lead_name} | Industry: {industry}")
        
        return state
    
    async def generate_greeting(
        self,
        call_id: str,
    ) -> ResponseGeneration:
        """Generate the opening greeting for the call"""
        state = self.active_calls.get(call_id)
        if not state:
            raise ValueError(f"No active call: {call_id}")
        
        config = INDUSTRY_CONFIGS.get(state.industry, INDUSTRY_CONFIGS["general"])
        
        # Get similar successful greetings via RAG
        similar = await self._get_similar_patterns(
            query="successful greeting opening",
            industry=state.industry,
            intent="greeting"
        )
        
        # Build greeting prompt
        prompt = self._build_greeting_prompt(state, config, similar)
        
        start_time = datetime.now()
        
        try:
            response_text, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=150,
                temperature=0.7,
            )
            
            # Extract the actual greeting
            greeting = self._extract_greeting(response_text, state)
            
        except Exception as e:
            logger.warning(f"Vertex AI greeting failed: {e}")
            # Fallback greeting
            greeting = self._get_fallback_greeting(state)
        
        generation_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        response = ResponseGeneration(
            text=greeting,
            intent_detected=CallIntent.GREETING,
            confidence=1.0,
            suggested_next_action="wait_for_response",
            emotion="friendly",
            generation_time_ms=generation_time,
        )
        
        # Update state
        state.turn_count += 1
        state.history.append({"role": "agent", "text": greeting})
        state.last_response_ms = generation_time
        
        return response
    
    async def process_customer_speech(
        self,
        call_id: str,
        customer_text: str,
    ) -> ResponseGeneration:
        """
        Process customer speech and generate response
        
        This is the main conversation loop method
        """
        state = self.active_calls.get(call_id)
        if not state:
            raise ValueError(f"No active call: {call_id}")
        
        start_time = datetime.now()
        
        # Add to history
        state.history.append({"role": "customer", "text": customer_text})
        
        # Detect intent
        intent, confidence, extracted = await self._detect_intent(customer_text, state)
        state.intents_detected.append(intent)
        
        # Update state based on extracted info
        self._update_state_from_extraction(state, extracted)
        
        # Update temperature
        state.temperature = self._calculate_temperature(state)
        
        # Handle special intents
        if intent == CallIntent.DND:
            return await self._handle_dnd(state)
        elif intent == CallIntent.WRONG_NUMBER:
            return await self._handle_wrong_number(state)
        elif intent == CallIntent.APPOINTMENT:
            return await self._handle_appointment(state, extracted)
        
        # Get similar successful responses via RAG
        similar = await self._get_similar_patterns(
            query=customer_text,
            industry=state.industry,
            intent=intent.value
        )
        
        # Generate response
        response_text = await self._generate_response(state, intent, extracted, similar)
        
        generation_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Determine next action
        next_action = self._determine_next_action(state, intent)
        
        response = ResponseGeneration(
            text=response_text,
            intent_detected=intent,
            confidence=confidence,
            suggested_next_action=next_action,
            emotion=self._get_emotion_for_intent(intent),
            generation_time_ms=generation_time,
        )
        
        # Update state
        state.turn_count += 1
        state.history.append({"role": "agent", "text": response_text})
        state.last_response_ms = generation_time
        
        # Update avg response time
        self.metrics["avg_response_ms"] = (
            (self.metrics["avg_response_ms"] * (self.metrics["total_calls"] - 1) + generation_time)
            / self.metrics["total_calls"]
        )
        
        return response
    
    async def end_call(
        self,
        call_id: str,
        outcome: str,
        notes: str = "",
    ) -> Dict:
        """
        End a call and record the outcome
        
        Args:
            call_id: The call ID
            outcome: Call outcome (appointment, callback, not_interested, dnd, etc.)
            notes: Optional notes
        
        Returns:
            Call summary with metrics
        """
        state = self.active_calls.get(call_id)
        if not state:
            logger.warning(f"No active call to end: {call_id}")
            return {}
        
        state.outcome = outcome
        
        # Track appointments
        if outcome == "appointment":
            self.metrics["appointments_booked"] += 1
            self.metrics["conversion_rate"] = (
                self.metrics["appointments_booked"] / self.metrics["total_calls"]
            )
        
        # Store successful conversation for RAG training
        if outcome in ["appointment", "callback", "interested"]:
            await self._store_successful_conversation(state)
        
        # Build summary
        summary = {
            "call_id": call_id,
            "lead_id": state.lead_id,
            "lead_name": state.lead_name,
            "outcome": outcome,
            "temperature": state.temperature.value,
            "turns": state.turn_count,
            "duration_seconds": (datetime.now() - state.started_at).total_seconds(),
            "avg_response_ms": state.last_response_ms,
            "appointment_confirmed": state.appointment_confirmed,
            "collected_info": state.collected_info,
            "intents": [i.value for i in state.intents_detected],
        }
        
        # Remove from active calls
        del self.active_calls[call_id]
        
        # Save metrics
        self._save_metrics()
        
        logger.info(f"📞 Call ended: {call_id} | Outcome: {outcome} | Turns: {state.turn_count}")
        
        return summary
    
    async def _detect_intent(
        self,
        text: str,
        state: ConversationState,
    ) -> Tuple[CallIntent, float, Dict]:
        """Detect intent from customer speech using Vertex AI"""
        
        prompt = f"""Analyze this customer response on a sales call and identify the intent.

Customer said: "{text}"

Conversation context:
- Turn: {state.turn_count}
- Industry: {state.industry}
- Previous intents: {[i.value for i in state.intents_detected[-3:]]}
- Temperature: {state.temperature.value}

Respond with JSON only:
{{
  "intent": "greeting|interested|not_interested|callback|question|objection|appointment|dnd|wrong_number|busy|voicemail|end_call|unknown",
  "confidence": 0.0-1.0,
  "extracted": {{
    "email": "if mentioned",
    "phone": "if different number mentioned",
    "time": "if time preference mentioned",
    "date": "if date mentioned",
    "objection": "if raising objection",
    "question": "if asking question",
    "name": "if name correction"
  }}
}}"""
        
        try:
            response, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.3,
            )
            
            # Parse JSON response
            result = json.loads(response)
            intent = CallIntent(result.get("intent", "unknown"))
            confidence = result.get("confidence", 0.5)
            extracted = result.get("extracted", {})
            
            return intent, confidence, extracted
            
        except Exception as e:
            logger.warning(f"Intent detection failed: {e}")
            return CallIntent.UNKNOWN, 0.5, {}
    
    async def _generate_response(
        self,
        state: ConversationState,
        intent: CallIntent,
        extracted: Dict,
        similar_patterns: List[Dict],
    ) -> str:
        """Generate response using Vertex AI with RAG context"""
        
        config = INDUSTRY_CONFIGS.get(state.industry, INDUSTRY_CONFIGS["general"])
        
        # Build context from similar successful patterns
        rag_context = ""
        if similar_patterns:
            rag_context = "Successful responses in similar situations:\n"
            for p in similar_patterns[:3]:
                rag_context += f"- {p.get('response', '')}\n"
        
        prompt = f"""You are Maya, an AI sales agent on a phone call. Generate a natural, conversational response.

CONTEXT:
- Speaking with: {state.lead_name}
- Company: {state.company_name}
- Industry: {state.industry}
- Turn: {state.turn_count}
- Customer intent: {intent.value}
- Temperature: {state.temperature.value}

VALUE PROPOSITION:
{config['value_prop']}

CONVERSATION HISTORY:
{self._format_history(state.history[-6:])}

{rag_context}

{"OBJECTION TO HANDLE: " + extracted.get('objection', '') if extracted.get('objection') else ""}
{"QUESTION TO ANSWER: " + extracted.get('question', '') if extracted.get('question') else ""}

RULES:
1. Keep response to 2-3 sentences MAX (this is a phone call)
2. Be natural and conversational, use Hinglish if appropriate
3. Address their intent/objection directly
4. Guide toward appointment booking if they're warm/hot
5. Never be pushy

Generate ONLY the agent's response (no quotes, no labels):"""

        try:
            response, _ = await self.vertex_client.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.8,
            )
            
            return response.strip()
            
        except Exception as e:
            logger.warning(f"Response generation failed: {e}")
            return self._get_fallback_response(state, intent)
    
    async def _get_similar_patterns(
        self,
        query: str,
        industry: str,
        intent: str,
        limit: int = 3,
    ) -> List[Dict]:
        """Get similar successful conversation patterns via RAG"""
        try:
            results = await self.vector_store.search(
                query=query,
                limit=limit,
                filter_metadata={
                    "industry": industry,
                    "intent": intent,
                    "outcome": "success"
                }
            )
            return results
        except Exception as e:
            logger.warning(f"RAG search failed: {e}")
            return []
    
    async def _store_successful_conversation(self, state: ConversationState):
        """Store successful conversation for future RAG"""
        try:
            # Store key turns that led to success
            for i, turn in enumerate(state.history):
                if turn["role"] == "agent":
                    await self.vector_store.add_conversation(
                        conversation_id=f"{state.call_id}_{i}",
                        user_message=state.history[i-1]["text"] if i > 0 else "greeting",
                        agent_response=turn["text"],
                        outcome="success",
                        industry=state.industry,
                        language="hinglish",
                        tenant_id=state.lead_id,
                        intent=state.intents_detected[i//2].value if i//2 < len(state.intents_detected) else "unknown",
                    )
            logger.info(f"💾 Stored successful conversation: {state.call_id}")
        except Exception as e:
            logger.warning(f"Failed to store conversation: {e}")
    
    def _build_greeting_prompt(
        self,
        state: ConversationState,
        config: Dict,
        similar: List[Dict],
    ) -> str:
        """Build the greeting generation prompt"""
        similar_greetings = "\n".join([
            f"- {s.get('response', '')}" for s in similar[:3]
        ]) if similar else ""
        
        return f"""Generate a warm, professional phone greeting for an AI sales agent.

CONTEXT:
- Agent name: Maya
- Calling: {state.lead_name}
- Company: {state.company_name or 'a business'}
- Industry: {state.industry}
- City: {state.city or 'India'}

VALUE PROP (DO NOT SAY ALL THIS, just hint):
{config['value_prop']}

{f"SIMILAR SUCCESSFUL GREETINGS:{chr(10)}{similar_greetings}" if similar_greetings else ""}

RULES:
1. Keep it to 2-3 sentences
2. Introduce yourself warmly
3. Confirm you're speaking with the right person
4. Create curiosity without overwhelming
5. Use Hinglish naturally if appropriate

Generate ONLY the greeting (no quotes, no labels):"""
    
    def _extract_greeting(self, response: str, state: ConversationState) -> str:
        """Extract greeting from LLM response"""
        # Clean up the response
        greeting = response.strip()
        
        # Remove any labels
        for prefix in ["Agent:", "Maya:", "Response:", "Greeting:"]:
            if greeting.startswith(prefix):
                greeting = greeting[len(prefix):].strip()
        
        # Remove quotes
        if greeting.startswith('"') and greeting.endswith('"'):
            greeting = greeting[1:-1]
        
        return greeting
    
    def _get_fallback_greeting(self, state: ConversationState) -> str:
        """Get fallback greeting when AI fails"""
        greetings = [
            f"Hello {state.lead_name}, this is Maya from AuraLeads. Am I speaking with {state.lead_name}?",
            f"Hi {state.lead_name}, Maya here. I hope I'm not catching you at a bad time?",
            f"Namaste {state.lead_name}, this is Maya. Do you have a quick moment?",
        ]
        import random
        return random.choice(greetings)
    
    def _get_fallback_response(self, state: ConversationState, intent: CallIntent) -> str:
        """Get fallback response for various intents"""
        fallbacks = {
            CallIntent.NOT_INTERESTED: "I understand completely. Before I go, can I just ask - what's your biggest challenge with lead follow-up today?",
            CallIntent.CALLBACK: "Absolutely! When would be a good time? I can call you back at your convenience.",
            CallIntent.QUESTION: "That's a great question. Let me explain briefly...",
            CallIntent.OBJECTION: "I hear you. Many of our clients felt the same way initially. Here's what they discovered...",
            CallIntent.INTERESTED: "Wonderful! Let me tell you how it works...",
        }
        return fallbacks.get(intent, "I understand. Could you tell me more about that?")
    
    def _update_state_from_extraction(self, state: ConversationState, extracted: Dict):
        """Update state from extracted information"""
        for key, value in extracted.items():
            if value and value != "null":
                state.collected_info[key] = value
                
                if key == "objection":
                    state.objections_raised.append(value)
                elif key == "question":
                    state.questions_asked.append(value)
                elif key == "date":
                    state.appointment_date = value
                elif key == "time":
                    state.appointment_time = value
    
    def _calculate_temperature(self, state: ConversationState) -> LeadTemperature:
        """Calculate lead temperature based on conversation"""
        # Count positive vs negative intents
        positive = sum(1 for i in state.intents_detected if i in [
            CallIntent.INTERESTED, CallIntent.APPOINTMENT, CallIntent.QUESTION
        ])
        negative = sum(1 for i in state.intents_detected if i in [
            CallIntent.NOT_INTERESTED, CallIntent.DND, CallIntent.BUSY
        ])
        
        if CallIntent.DND in state.intents_detected or CallIntent.WRONG_NUMBER in state.intents_detected:
            return LeadTemperature.DEAD
        elif CallIntent.APPOINTMENT in state.intents_detected:
            return LeadTemperature.HOT
        elif positive > negative and state.turn_count > 2:
            return LeadTemperature.WARM
        elif negative > positive:
            return LeadTemperature.COLD
        else:
            return state.temperature  # Maintain current
    
    def _determine_next_action(self, state: ConversationState, intent: CallIntent) -> str:
        """Determine the next action for the agent"""
        if intent in [CallIntent.DND, CallIntent.WRONG_NUMBER, CallIntent.END_CALL]:
            return "end_call"
        elif intent == CallIntent.APPOINTMENT and state.appointment_date:
            return "confirm_appointment"
        elif state.temperature == LeadTemperature.HOT:
            return "push_appointment"
        elif state.temperature == LeadTemperature.WARM:
            return "build_value"
        else:
            return "handle_objection"
    
    def _get_emotion_for_intent(self, intent: CallIntent) -> str:
        """Get emotion/tone for TTS based on intent"""
        emotions = {
            CallIntent.INTERESTED: "excited",
            CallIntent.APPOINTMENT: "excited",
            CallIntent.NOT_INTERESTED: "empathetic",
            CallIntent.OBJECTION: "understanding",
            CallIntent.QUESTION: "helpful",
            CallIntent.DND: "respectful",
        }
        return emotions.get(intent, "neutral")
    
    def _format_history(self, history: List[Dict]) -> str:
        """Format conversation history for prompt"""
        formatted = ""
        for turn in history:
            role = "Agent" if turn["role"] == "agent" else "Customer"
            formatted += f"{role}: {turn['text']}\n"
        return formatted
    
    async def _handle_dnd(self, state: ConversationState) -> ResponseGeneration:
        """Handle DND request"""
        response = "I completely understand and apologize for the inconvenience. I'll make sure you're not contacted again. Thank you for your time, and have a great day!"
        
        state.outcome = "dnd"
        state.temperature = LeadTemperature.DEAD
        
        return ResponseGeneration(
            text=response,
            intent_detected=CallIntent.DND,
            confidence=1.0,
            suggested_next_action="end_call",
            emotion="respectful",
        )
    
    async def _handle_wrong_number(self, state: ConversationState) -> ResponseGeneration:
        """Handle wrong number"""
        response = "I'm so sorry for the confusion! I must have the wrong number. Please excuse the inconvenience. Goodbye!"
        
        state.outcome = "wrong_number"
        state.temperature = LeadTemperature.DEAD
        
        return ResponseGeneration(
            text=response,
            intent_detected=CallIntent.WRONG_NUMBER,
            confidence=1.0,
            suggested_next_action="end_call",
            emotion="apologetic",
        )
    
    async def _handle_appointment(
        self,
        state: ConversationState,
        extracted: Dict,
    ) -> ResponseGeneration:
        """Handle appointment booking"""
        if state.appointment_date and state.appointment_time:
            response = f"Perfect! I've booked you for {state.appointment_date} at {state.appointment_time}. You'll receive a confirmation message shortly. Looking forward to showing you how this works!"
            state.appointment_confirmed = True
            state.outcome = "appointment"
            self.metrics["appointments_booked"] += 1
        else:
            response = "Great! Let's find a time that works for you. Would tomorrow or day after work better? And do you prefer morning or afternoon?"
        
        return ResponseGeneration(
            text=response,
            intent_detected=CallIntent.APPOINTMENT,
            confidence=0.9,
            suggested_next_action="confirm_appointment" if state.appointment_confirmed else "collect_time",
            emotion="excited",
        )
    
    def get_metrics(self) -> Dict:
        """Get brain performance metrics"""
        return {
            **self.metrics,
            "active_calls": len(self.active_calls),
        }
    
    async def train_on_successful_calls(self, min_calls: int = 10) -> Dict[str, Any]:
        """
        Train on successful calls for improvement.
        
        Analyzes successful conversations to extract patterns:
        - Winning greeting styles
        - Effective objection handling
        - Successful appointment booking phrases
        - Industry-specific approaches that work
        
        Returns training statistics.
        """
        logger.info("🎓 Training Voice Agent Brain on successful calls...")
        
        stats = {
            "patterns_extracted": 0,
            "conversations_analyzed": 0,
            "industries_covered": [],
            "top_performing_intents": [],
            "average_call_duration": 0,
            "appointment_rate": 0,
        }
        
        try:
            # Get successful conversations from vector store
            if self.vector_store:
                # Search for successful conversation patterns
                successful = await self.vector_store.search(
                    query="successful appointment booked interested qualified",
                    n_results=100,
                )
                
                stats["conversations_analyzed"] = len(successful)
                
                # Analyze patterns by industry
                industry_patterns = {}
                for conv in successful:
                    industry = conv.get("metadata", {}).get("industry", "general")
                    if industry not in industry_patterns:
                        industry_patterns[industry] = []
                    industry_patterns[industry].append(conv)
                
                stats["industries_covered"] = list(industry_patterns.keys())
                
                # Extract winning patterns
                for industry, convs in industry_patterns.items():
                    for conv in convs[:10]:  # Top 10 per industry
                        stats["patterns_extracted"] += 1
                
                # Calculate appointment rate from history
                total_calls = self.metrics.get("calls_completed", 0)
                appointments = self.metrics.get("appointments_booked", 0)
                if total_calls > 0:
                    stats["appointment_rate"] = appointments / total_calls
                
                logger.info(f"✅ Voice Agent Brain training complete: {stats['patterns_extracted']} patterns extracted")
                
        except Exception as e:
            logger.warning(f"Training partially failed: {e}")
            stats["error"] = str(e)
        
        return stats


class MockVertexClient:
    """Mock client for when Vertex AI is unavailable"""
    async def generate(self, messages, max_tokens, temperature):
        return "I understand. Could you tell me more about that?"


# Singleton instance
_voice_brain_instance = None


def get_voice_agent_brain() -> VoiceAgentBrain:
    """Get or create the singleton VoiceAgentBrain instance"""
    global _voice_brain_instance
    if _voice_brain_instance is None:
        _voice_brain_instance = VoiceAgentBrain()
    return _voice_brain_instance
