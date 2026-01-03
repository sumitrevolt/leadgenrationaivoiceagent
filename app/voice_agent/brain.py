"""
Voice Agent Brain - Vertex AI Powered Conversation Intelligence
Production-grade conversation handling with real-time AI responses
"""
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import re

from app.llm.vertex_client import get_vertex_client, VertexAIClient
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationIntent(Enum):
    """Detected intents from conversation"""
    GREETING = "greeting"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK = "callback"
    QUESTION = "question"
    OBJECTION = "objection"
    APPOINTMENT = "appointment"
    DND = "dnd"
    WRONG_NUMBER = "wrong_number"
    TRANSFER = "transfer"
    END_CALL = "end_call"
    UNKNOWN = "unknown"


class LeadTemperature(Enum):
    """Lead qualification temperature"""
    HOT = "hot"  # Ready to buy/demo
    WARM = "warm"  # Interested, needs follow-up
    COLD = "cold"  # Not interested now
    DEAD = "dead"  # Not interested at all


@dataclass
class ConversationContext:
    """Context for ongoing conversation"""
    call_id: str
    lead_name: str
    lead_phone: str
    company_name: Optional[str] = None
    industry: Optional[str] = None
    client_name: str = "AuraLeads AI"
    client_product: str = "AI Voice Agent for Lead Generation"
    
    # Conversation state
    turn_count: int = 0
    intents_detected: List[ConversationIntent] = field(default_factory=list)
    lead_temperature: LeadTemperature = LeadTemperature.COLD
    
    # Collected information
    collected_info: Dict[str, Any] = field(default_factory=dict)
    objections: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    
    # Appointment
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    appointment_confirmed: bool = False
    
    # Conversation history
    history: List[Dict[str, str]] = field(default_factory=list)
    
    # Call outcome
    call_outcome: Optional[str] = None
    follow_up_required: bool = False
    follow_up_date: Optional[str] = None


class VoiceAgentBrain:
    """
    AI-powered brain for voice agents using Vertex AI
    Handles real-time conversation processing and response generation
    """
    
    # Response timing targets (for voice)
    TARGET_RESPONSE_MS = 500  # Target response time
    MAX_RESPONSE_MS = 2000  # Maximum acceptable
    
    # Conversation prompts
    SYSTEM_PROMPT = """You are Maya, a friendly and professional AI sales agent for {client_name}.
You're calling Indian businesses to offer {client_product}.

YOUR PERSONALITY:
- Speak naturally in Hinglish (mix of Hindi and English) when appropriate
- Be warm, professional, and consultative
- Listen actively and respond to what they say
- Keep responses concise (2-3 sentences max) - this is a phone call
- Use the person's name occasionally
- Handle objections gracefully without being pushy

YOUR GOAL:
1. Build rapport and understand their business needs
2. Identify if they're a good fit for our solution
3. If interested, schedule a demo/callback
4. Collect their email for follow-up

IMPORTANT RULES:
- Never be pushy or aggressive
- If they say DND or not interested, thank them and end politely
- If wrong number, apologize and end
- If they ask questions, answer briefly then redirect to value
- Always confirm appointments with date/time

CURRENT CONTEXT:
- Speaking with: {lead_name}
- Company: {company_name}
- Industry: {industry}
- Turn: {turn_count}
- Lead temperature: {lead_temperature}
"""

    INTENT_PROMPT = """Analyze this customer response and identify the primary intent.
Customer said: "{text}"

Previous context: {context}

Respond with a JSON object:
{{
  "intent": "one of: greeting, interested, not_interested, callback, question, objection, appointment, dnd, wrong_number, transfer, end_call, unknown",
  "confidence": 0.0-1.0,
  "extracted_info": {{
    "email": "if mentioned",
    "time_preference": "if mentioned",
    "objection": "if raising objection",
    "question": "if asking question"
  }},
  "lead_temperature": "hot, warm, cold, or dead based on tone/content",
  "sentiment": "positive, neutral, negative"
}}"""

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.client: VertexAIClient = get_vertex_client(model_name)
        self.active_contexts: Dict[str, ConversationContext] = {}
        
    async def start_conversation(
        self,
        call_id: str,
        lead_name: str,
        lead_phone: str,
        company_name: Optional[str] = None,
        industry: Optional[str] = None,
        client_name: str = "AuraLeads AI",
        client_product: str = "AI Voice Agent for Lead Generation",
    ) -> Tuple[str, ConversationContext]:
        """
        Start a new conversation and generate opening script
        
        Returns:
            Tuple of (opening_script, context)
        """
        # Create context
        context = ConversationContext(
            call_id=call_id,
            lead_name=lead_name,
            lead_phone=lead_phone,
            company_name=company_name or "your company",
            industry=industry or "your industry",
            client_name=client_name,
            client_product=client_product,
        )
        
        # Store context
        self.active_contexts[call_id] = context
        
        # Generate opening
        opening = await self._generate_opening(context)
        
        # Add to history
        context.history.append({
            "role": "assistant",
            "content": opening
        })
        context.turn_count = 1
        
        logger.info(f"Started conversation for call {call_id}")
        return opening, context
    
    async def _generate_opening(self, context: ConversationContext) -> str:
        """Generate personalized opening script"""
        prompt = f"""Generate a natural, friendly opening for a cold call in Hinglish.

Details:
- Caller: Maya from {context.client_name}
- Calling: {context.lead_name} at {context.company_name}
- Industry: {context.industry}
- Product: {context.client_product}

Requirements:
- Start with a warm greeting using their name
- Brief introduction (who you are)
- Quick value proposition (1 sentence)
- Engaging question to start dialogue
- Keep it under 30 words total
- Natural Hinglish if appropriate

Generate ONLY the spoken text, no instructions or formatting."""

        response, _ = await self.client.generate(prompt, max_tokens=100)
        return response.strip()
    
    async def process_response(
        self,
        call_id: str,
        user_text: str,
    ) -> Tuple[str, ConversationIntent, Dict[str, Any]]:
        """
        Process user response and generate AI reply
        
        Args:
            call_id: Active call ID
            user_text: What the user said (from STT)
            
        Returns:
            Tuple of (ai_response, detected_intent, extracted_info)
        """
        context = self.active_contexts.get(call_id)
        if not context:
            logger.warning(f"No context found for call {call_id}")
            return "I'm sorry, there seems to be a connection issue. Could you please repeat that?", ConversationIntent.UNKNOWN, {}
        
        # Add user message to history
        context.history.append({
            "role": "user",
            "content": user_text
        })
        context.turn_count += 1
        
        # Analyze intent (parallel with response generation for speed)
        intent_task = asyncio.create_task(self._analyze_intent(user_text, context))
        
        # Generate response
        response = await self._generate_response(user_text, context)
        
        # Wait for intent analysis
        intent, extracted_info = await intent_task
        
        # Update context
        context.intents_detected.append(intent)
        if extracted_info:
            context.collected_info.update(extracted_info)
            
            if extracted_info.get("objection"):
                context.objections.append(extracted_info["objection"])
            if extracted_info.get("question"):
                context.questions.append(extracted_info["question"])
        
        # Update lead temperature
        self._update_temperature(context, intent)
        
        # Add response to history
        context.history.append({
            "role": "assistant",
            "content": response
        })
        
        # Check for conversation end
        if intent in [ConversationIntent.DND, ConversationIntent.WRONG_NUMBER, ConversationIntent.END_CALL]:
            context.call_outcome = intent.value
            
        if intent == ConversationIntent.APPOINTMENT and extracted_info.get("time_preference"):
            context.appointment_time = extracted_info["time_preference"]
            context.appointment_confirmed = True
        
        logger.debug(f"Call {call_id}: Intent={intent.value}, Temp={context.lead_temperature.value}")
        return response, intent, extracted_info
    
    async def _analyze_intent(
        self,
        text: str,
        context: ConversationContext
    ) -> Tuple[ConversationIntent, Dict[str, Any]]:
        """Analyze intent from user response"""
        # Quick keyword detection for common intents
        text_lower = text.lower()
        
        # Fast path for common phrases
        if any(word in text_lower for word in ["dnd", "do not disturb", "mat karo call"]):
            return ConversationIntent.DND, {}
        if any(word in text_lower for word in ["wrong number", "galat number"]):
            return ConversationIntent.WRONG_NUMBER, {}
        if any(word in text_lower for word in ["not interested", "interest nahi", "nahi chahiye"]):
            return ConversationIntent.NOT_INTERESTED, {}
        
        # Use LLM for complex intent detection
        prompt = self.INTENT_PROMPT.format(
            text=text,
            context=f"Turn {context.turn_count}, previous intents: {[i.value for i in context.intents_detected[-3:]]}"
        )
        
        try:
            response, _ = await self.client.generate(prompt, temperature=0.3, max_tokens=200)
            
            # Parse JSON response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                intent = ConversationIntent(result.get("intent", "unknown"))
                extracted_info = result.get("extracted_info", {})
                
                # Update temperature based on analysis
                if result.get("lead_temperature"):
                    context.lead_temperature = LeadTemperature(result["lead_temperature"])
                
                return intent, extracted_info
        except Exception as e:
            logger.warning(f"Intent analysis failed: {e}")
        
        return ConversationIntent.UNKNOWN, {}
    
    async def _generate_response(
        self,
        user_text: str,
        context: ConversationContext
    ) -> str:
        """Generate AI response to user input"""
        # Build system prompt with context
        system_prompt = self.SYSTEM_PROMPT.format(
            client_name=context.client_name,
            client_product=context.client_product,
            lead_name=context.lead_name,
            company_name=context.company_name,
            industry=context.industry,
            turn_count=context.turn_count,
            lead_temperature=context.lead_temperature.value,
        )
        
        # Build conversation for context
        conversation = "\n".join([
            f"{'Maya' if msg['role'] == 'assistant' else context.lead_name}: {msg['content']}"
            for msg in context.history[-6:]  # Last 6 turns for context
        ])
        
        prompt = f"""Previous conversation:
{conversation}

{context.lead_name} just said: "{user_text}"

Generate Maya's response. Remember:
- Keep it brief (2-3 sentences max)
- Be natural and conversational
- Address what they said
- Move toward the goal appropriately

Maya:"""

        response, _ = await self.client.generate(
            prompt,
            system_instruction=system_prompt,
            temperature=0.8,
            max_tokens=150
        )
        
        # Clean response
        response = response.strip()
        if response.startswith("Maya:"):
            response = response[5:].strip()
        
        return response
    
    def _update_temperature(self, context: ConversationContext, intent: ConversationIntent):
        """Update lead temperature based on intent"""
        temperature_map = {
            ConversationIntent.INTERESTED: LeadTemperature.WARM,
            ConversationIntent.APPOINTMENT: LeadTemperature.HOT,
            ConversationIntent.NOT_INTERESTED: LeadTemperature.COLD,
            ConversationIntent.DND: LeadTemperature.DEAD,
            ConversationIntent.WRONG_NUMBER: LeadTemperature.DEAD,
        }
        
        if intent in temperature_map:
            new_temp = temperature_map[intent]
            # Only upgrade temperature, don't downgrade from interested
            if new_temp == LeadTemperature.DEAD or context.lead_temperature != LeadTemperature.HOT:
                context.lead_temperature = new_temp
    
    async def end_conversation(
        self,
        call_id: str,
        outcome: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        End conversation and return summary
        
        Returns:
            Conversation summary with collected data
        """
        context = self.active_contexts.get(call_id)
        if not context:
            return {"error": "No active conversation"}
        
        # Generate summary
        summary = {
            "call_id": call_id,
            "lead_name": context.lead_name,
            "lead_phone": context.lead_phone,
            "company_name": context.company_name,
            "industry": context.industry,
            "turn_count": context.turn_count,
            "lead_temperature": context.lead_temperature.value,
            "intents_detected": [i.value for i in context.intents_detected],
            "collected_info": context.collected_info,
            "objections": context.objections,
            "questions": context.questions,
            "appointment": {
                "confirmed": context.appointment_confirmed,
                "date": context.appointment_date,
                "time": context.appointment_time,
            },
            "call_outcome": outcome or context.call_outcome or "completed",
            "follow_up_required": context.lead_temperature in [LeadTemperature.WARM, LeadTemperature.HOT],
            "conversation_history": context.history,
        }
        
        # Clean up
        del self.active_contexts[call_id]
        
        logger.info(f"Ended call {call_id}: outcome={summary['call_outcome']}, temp={summary['lead_temperature']}")
        return summary
    
    def get_context(self, call_id: str) -> Optional[ConversationContext]:
        """Get active conversation context"""
        return self.active_contexts.get(call_id)
    
    def get_active_calls(self) -> List[str]:
        """Get list of active call IDs"""
        return list(self.active_contexts.keys())


# Singleton instance
_brain_instance: Optional[VoiceAgentBrain] = None


def get_voice_agent_brain() -> VoiceAgentBrain:
    """Get singleton voice agent brain instance"""
    global _brain_instance
    if _brain_instance is None:
        _brain_instance = VoiceAgentBrain()
    return _brain_instance


# Convenience functions
async def start_call(
    call_id: str,
    lead_name: str,
    lead_phone: str,
    **kwargs
) -> Tuple[str, ConversationContext]:
    """Start a new call"""
    brain = get_voice_agent_brain()
    return await brain.start_conversation(call_id, lead_name, lead_phone, **kwargs)


async def handle_response(call_id: str, user_text: str) -> Tuple[str, ConversationIntent, Dict]:
    """Handle user response in active call"""
    brain = get_voice_agent_brain()
    return await brain.process_response(call_id, user_text)


async def end_call(call_id: str, outcome: str = None) -> Dict[str, Any]:
    """End call and get summary"""
    brain = get_voice_agent_brain()
    return await brain.end_conversation(call_id, outcome)
