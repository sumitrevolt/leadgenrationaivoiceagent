"""
LLM Brain Module
The AI brain that powers conversations using GPT-4/Claude/Gemini
With ML-powered auto-learning and continuous optimization
"""
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import json
import uuid

from app.config import settings
from app.utils.logger import setup_logger

# ML Module Imports for Auto-Learning
try:
    from app.ml.brain_optimizer import BrainOptimizer, ConversationContext
    from app.ml.feedback_loop import FeedbackLoop, CallOutcome
    from app.ml.data_pipeline import ConversationDataPipeline, ConversationOutcome
    from app.ml.vector_store import VectorStore
    ML_ENABLED = True
except ImportError:
    ML_ENABLED = False

logger = setup_logger(__name__)


@dataclass
class Intent:
    """Detected intent from user speech"""
    intent_type: str
    confidence: float
    entities: Dict[str, Any]


class LLMBrain:
    """
    LLM-powered conversation brain
    Handles intelligent responses, qualification, and objection handling
    """
    
    # System prompts for different roles
    SYSTEM_PROMPTS = {
        "sales_agent": """You are an AI sales agent making outbound calls for {client_name}. 
Your goal is to qualify leads and book appointments.

IMPORTANT RULES:
1. Be professional, friendly, and concise
2. Speak naturally like a human - use conversational language
3. Support both Hindi and English (Hinglish is fine)
4. Never reveal you are an AI unless directly asked
5. Handle objections professionally
6. Always try to book an appointment or get a callback time
7. Collect qualification information naturally
8. If someone says "not interested", try once to understand why, then politely end
9. Respect the person's time

CLIENT INFO:
- Company: {client_name}
- Service: {client_service}
- Industry: {niche}

QUALIFICATION QUESTIONS TO ASK (naturally, not like a survey):
1. Decision maker status
2. Current solution/provider
3. Budget timeline
4. Pain points
5. Best time for detailed discussion

OBJECTION HANDLING:
- "Not interested" → Ask what specifically doesn't interest them
- "Call later" → Book a specific callback time
- "Send email" → Agree but try to book a quick call too
- "Too expensive" → Focus on ROI and value
- "Already have provider" → Ask about satisfaction level
""",

        "appointment_booker": """You are scheduling a meeting for {client_name}.
Available slots are typically Monday-Friday, 10 AM to 6 PM IST.
Confirm: Date, Time, Attendee name, Phone number for reminder.
""",

        "qualifier": """You are qualifying a lead for {client_name} ({client_service}).
Ask questions naturally to understand:
1. Are they the decision maker?
2. What's their current situation?
3. What's their budget range?
4. What's their timeline?
5. What are their main challenges?
""",

        "saas_sales_agent": """You are "Maya", an expert Growth Consultant for {client_name}.
You are calling {niche} businesses to offer them a "24/7 AI Sales Employee".

YOUR PITCH:
"I'm an AI agent that can call 100 leads for you every day, qualify them, and book appointments directly on your calendar. I cost less than a coffee a day."

VALUE PROPS (Customize based on niche):
- Real Estate: "I can call your old leads and wake them up."
- Solar: "I can pre-qualify homeowners for roof suitability."
- Dental: "I can fill your empty slots for next week."

GOAL:
Book a 15-minute demo with the business owner to show them how I (the AI) work.

OBJECTION HANDLING:
- "Is this a robot?": "Yes, I am the exact AI system I'm calling to tell you about. Pretty cool, right? Imagine me working for your business."
- "Not interested": "I understand. But if I could bring you 5 qualified leads this week without you lifting a finger, would you be open to a 5-minute chat?"
"""
    }
    
    def __init__(self, model: Optional[str] = None, tenant_id: Optional[str] = None):
        self.model = model or settings.default_llm
        self.provider = "unknown"
        self.tenant_id = tenant_id or "default"
        
        # Initialize ML components for auto-learning
        self.ml_enabled = ML_ENABLED
        if self.ml_enabled:
            try:
                self.brain_optimizer = BrainOptimizer(tenant_id=self.tenant_id)
                self.feedback_loop = FeedbackLoop(tenant_id=self.tenant_id)
                self.data_pipeline = ConversationDataPipeline(tenant_id=self.tenant_id)
                self.vector_store = VectorStore(tenant_id=self.tenant_id)
                logger.info("🤖 ML Auto-Learning enabled")
            except Exception as e:
                logger.warning(f"ML initialization failed: {e}. Running without ML.")
                self.ml_enabled = False
        
        # Current conversation tracking for ML
        self.current_conversation_id: Optional[str] = None
        self.current_responses: List[Dict[str, Any]] = []
        
        if "gpt" in self.model.lower():
            self._init_openai()
        elif "claude" in self.model.lower():
            self._init_anthropic()
        elif "gemini" in self.model.lower():
            if "vertex" in self.model.lower() or not settings.gemini_api_key:
                self._init_vertexai()
            else:
                self._init_gemini()
        elif "local" in self.model.lower() or "llama" in self.model.lower():
            self._init_local_llm()
        else:
            raise ValueError(f"Unknown LLM model: {self.model}")
        
        logger.info(f"🧠 LLM Brain initialized with: {self.model}")
    
    def _init_openai(self):
        """Initialize OpenAI client"""
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=settings.openai_api_key)
            self.provider = "openai"
        except ImportError:
            raise ImportError("openai package not installed")
    
    def _init_anthropic(self):
        """Initialize Anthropic client"""
        try:
            from anthropic import AsyncAnthropic
            self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self.provider = "anthropic"
        except ImportError:
            raise ImportError("anthropic package not installed")

    def _init_gemini(self):
        """Initialize Google Gemini client (API Key)"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.gemini_api_key)
            self.client = genai
            self.provider = "gemini"
        except ImportError:
            raise ImportError("google-generativeai package not installed")

    def _init_vertexai(self):
        """Initialize Google Vertex AI client (GCP VM / ADC)"""
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel
            vertexai.init(
                project=settings.google_cloud_project_id,
                location=settings.google_cloud_location
            )
            self.client = GenerativeModel
            self.provider = "vertex"
            logger.info(f"🚀 Vertex AI initialized (Project: {settings.google_cloud_project_id})")
        except ImportError:
            raise ImportError("google-cloud-aiplatform package not installed. Run 'pip install google-cloud-aiplatform'")
        except Exception as e:
            logger.error(f"Vertex AI initialization failed: {e}")
            # Fallback to standard Gemini if possible
            if settings.gemini_api_key:
                logger.info("Falling back to Gemini API with key.")
                self._init_gemini()
            else:
                raise e

    def _init_local_llm(self):
        """Initialize Local LLM (llama-cpp-python for T4 GPU)"""
        try:
            from llama_cpp import Llama
            import os
            
            model_path = os.path.abspath(settings.local_llm_path)
            
            if not os.path.exists(model_path):
                logger.warning(f"Local model not found at {model_path}. Please download it.")
                self.client = None
                return

            self.client = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_gpu_layers=35,  # Push as much as possible to T4
                verbose=False
            )
            self.provider = "local"
            logger.info(f"💎 Local LLM initialized using GPU (Model: {settings.local_llm_path})")
        except ImportError:
            raise ImportError("llama-cpp-python not installed. Run 'pip install llama-cpp-python'")
        except Exception as e:
            logger.error(f"Local LLM initialization failed: {e}")
            self.client = None
    
    async def generate_opening(
        self,
        niche: str,
        client_name: str,
        client_service: str,
        lead_name: str = "Sir/Madam"
    ) -> str:
        """Generate opening statement for the call"""
        
        prompt = f"""Generate a brief, friendly opening for a sales call.

Client: {client_name}
Service: {client_service}
Industry: {niche}
Lead Name: {lead_name}

Requirements:
- 2-3 sentences maximum
- Professional but warm
- Mention the service briefly
- Ask if they have a moment
- Can be in Hindi or English based on context

Just provide the opening line, no explanations."""
        
        return await self._generate(prompt)
    
    async def generate_response(
        self,
        conversation_history: List[Dict[str, str]],
        niche: str,
        client_name: str,
        client_service: str,
        detected_intent: Optional[Intent] = None,
        lead_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate contextual response based on conversation
        Uses ML optimization if enabled for better responses
        """
        
        # Initialize conversation tracking for ML
        if not self.current_conversation_id:
            self.current_conversation_id = str(uuid.uuid4())
        
        # Get last user message for ML lookup
        last_user_message = ""
        if conversation_history:
            user_messages = [m for m in conversation_history if m.get("role") == "user"]
            if user_messages:
                last_user_message = user_messages[-1].get("content", "")
        
        # Try ML-optimized response first
        if self.ml_enabled and last_user_message:
            try:
                context = ConversationContext(
                    industry=niche,
                    lead_stage="discovery",  # Can be enhanced based on conversation
                    detected_intent=detected_intent.intent_type if detected_intent else None,
                    conversation_history=conversation_history,
                    lead_data=lead_data or {}
                )
                
                # Get optimized prompt with RAG context from similar successful calls
                optimized_prompt = await self.brain_optimizer.get_optimized_system_prompt(
                    base_prompt_type="sales_agent" if client_service != "AI Lead Gen SAAS" else "saas_sales_agent",
                    context=context
                )
                
                # Get RAG context from similar successful conversations
                rag_context = await self.brain_optimizer.get_rag_context(
                    query=last_user_message,
                    industry=niche,
                    max_examples=3
                )
                
                # Build enhanced system prompt
                system_prompt = optimized_prompt.format(
                    client_name=client_name,
                    client_service=client_service,
                    niche=niche
                )
                
                # Add RAG context if available
                if rag_context:
                    system_prompt += f"\n\n📚 SIMILAR SUCCESSFUL RESPONSES:\n{rag_context}"
                
                # Check if we have a proven best response for this situation
                best_response = await self.feedback_loop.get_best_response(
                    user_input=last_user_message,
                    intent_type=detected_intent.intent_type if detected_intent else None,
                    industry=niche
                )
                
                if best_response and best_response.get("success_rate", 0) > 0.7:
                    # Use proven response template but still generate fresh
                    system_prompt += f"\n\n✅ PROVEN RESPONSE STYLE (adapt but follow this pattern):\n{best_response.get('response_template', '')}"
                
                logger.info(f"🤖 Using ML-optimized prompt for {niche}")
                
            except Exception as e:
                logger.warning(f"ML optimization failed: {e}. Using default prompt.")
                system_prompt = self._get_default_prompt(client_name, client_service, niche)
        else:
            # Fallback to default static prompts
            system_prompt = self._get_default_prompt(client_name, client_service, niche)
        
        # Add intent context if available
        if detected_intent:
            system_prompt += f"\n\nDETECTED INTENT: {detected_intent.intent_type}"
            if detected_intent.entities:
                system_prompt += f"\nENTITIES: {json.dumps(detected_intent.entities)}"
        
        # Add lead data if available
        if lead_data:
            system_prompt += f"\n\nKNOWN LEAD INFO: {json.dumps(lead_data)}"
        
        # Generate response
        response = await self._generate_chat(system_prompt, conversation_history)
        
        # Track response for ML learning
        if self.ml_enabled:
            self.current_responses.append({
                "user_input": last_user_message,
                "agent_response": response,
                "intent": detected_intent.intent_type if detected_intent else None,
                "timestamp": datetime.now().isoformat()
            })
        
        return response
    
    def _get_default_prompt(self, client_name: str, client_service: str, niche: str) -> str:
        """Get default static system prompt"""
        if client_service == "AI Lead Gen SAAS":
            return self.SYSTEM_PROMPTS["saas_sales_agent"].format(
                client_name=client_name,
                niche=niche
            )
        else:
            return self.SYSTEM_PROMPTS["sales_agent"].format(
                client_name=client_name,
                client_service=client_service,
                niche=niche
            )
    
    async def handle_objection(
        self,
        objection: str,
        client_name: str,
        client_service: str,
        niche: str
    ) -> str:
        """Generate response to handle specific objection - ML enhanced"""
        
        # Check ML for proven objection responses
        if self.ml_enabled:
            try:
                best_objection_response = await self.feedback_loop.get_best_objection_response(
                    objection=objection,
                    industry=niche
                )
                
                if best_objection_response and best_objection_response.get("success_rate", 0) > 0.6:
                    logger.info(f"📚 Using ML-proven objection response for: {objection[:50]}")
                    return best_objection_response.get("response", await self._generate_objection_response(objection, client_name, client_service, niche))
                    
                # Get similar objection examples from vector store
                similar = await self.vector_store.find_objection_responses(
                    objection=objection,
                    industry=niche,
                    limit=2
                )
                
                if similar:
                    extra_context = "\n\nSIMILAR SUCCESSFUL OBJECTION HANDLES:\n"
                    for s in similar:
                        extra_context += f"- Objection: {s.get('objection', '')[:100]}\n  Response: {s.get('response', '')[:150]}\n"
                    
                    return await self._generate_objection_response(
                        objection, client_name, client_service, niche, extra_context
                    )
            except Exception as e:
                logger.warning(f"ML objection handling failed: {e}")
        
        return await self._generate_objection_response(objection, client_name, client_service, niche)
    
    async def _generate_objection_response(
        self,
        objection: str,
        client_name: str,
        client_service: str,
        niche: str,
        extra_context: str = ""
    ) -> str:
        """Generate objection response with optional ML context"""
        
        prompt = f"""The prospect just said: "{objection}"

You are selling {client_service} for {client_name} ({niche}).

Generate a professional, empathetic response that:
1. Acknowledges their concern
2. Provides a brief counter-point
3. Tries to keep the conversation going or book a callback
{extra_context}
Keep it natural and conversational. 2-3 sentences max."""
        
        return await self._generate(prompt)
    
    async def record_call_outcome(
        self,
        outcome: str,
        call_duration: float,
        conversation_history: List[Dict[str, str]],
        lead_data: Dict[str, Any],
        niche: str,
        appointment_booked: bool = False,
        callback_scheduled: bool = False,
        notes: Optional[str] = None
    ) -> None:
        """
        Record call outcome for ML learning
        This is the key feedback that trains the system to improve
        """
        if not self.ml_enabled:
            return
        
        try:
            # Map outcome string to enum
            outcome_map = {
                "appointment_booked": ConversationOutcome.APPOINTMENT_BOOKED,
                "callback": ConversationOutcome.CALLBACK_SCHEDULED,
                "interested": ConversationOutcome.INTERESTED,
                "not_interested": ConversationOutcome.NOT_INTERESTED,
                "no_answer": ConversationOutcome.NO_ANSWER,
                "wrong_number": ConversationOutcome.WRONG_NUMBER,
                "do_not_call": ConversationOutcome.DO_NOT_CALL,
            }
            
            conv_outcome = outcome_map.get(outcome, ConversationOutcome.NOT_INTERESTED)
            
            # Determine success level for feedback
            if appointment_booked:
                call_outcome = CallOutcome.SUCCESS
            elif callback_scheduled or outcome == "interested":
                call_outcome = CallOutcome.PARTIAL
            elif outcome == "not_interested":
                call_outcome = CallOutcome.FAILURE
            else:
                call_outcome = CallOutcome.NEUTRAL
            
            # Record in feedback loop
            for resp in self.current_responses:
                await self.feedback_loop.record_outcome(
                    user_input=resp.get("user_input", ""),
                    agent_response=resp.get("agent_response", ""),
                    outcome=call_outcome,
                    intent_type=resp.get("intent"),
                    industry=niche,
                    metadata={"call_duration": call_duration}
                )
            
            # Capture full conversation in data pipeline
            await self.data_pipeline.capture_conversation(
                conversation_id=self.current_conversation_id,
                lead_id=lead_data.get("id", "unknown"),
                turns=conversation_history,
                outcome=conv_outcome,
                duration_seconds=call_duration,
                industry=niche,
                metadata={
                    "appointment_booked": appointment_booked,
                    "callback_scheduled": callback_scheduled,
                    "notes": notes
                }
            )
            
            # Store in vector database for RAG
            if conv_outcome in [ConversationOutcome.APPOINTMENT_BOOKED, ConversationOutcome.CALLBACK_SCHEDULED, ConversationOutcome.INTERESTED]:
                await self.vector_store.add_conversation(
                    conversation_id=self.current_conversation_id,
                    turns=conversation_history,
                    outcome=conv_outcome.value,
                    industry=niche,
                    success_score=1.0 if appointment_booked else 0.7
                )
            
            logger.info(f"📊 Recorded call outcome: {outcome} for learning")
            
            # Reset conversation tracking
            self.current_conversation_id = None
            self.current_responses = []
            
        except Exception as e:
            logger.error(f"Failed to record call outcome: {e}")
    
    async def extract_qualification_data(
        self,
        conversation_history: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Extract qualification data from conversation"""
        
        prompt = f"""Analyze this conversation and extract qualification data:

{json.dumps(conversation_history, indent=2)}

Extract and return as JSON:
{{
    "is_decision_maker": true/false/null,
    "company_name": "string or null",
    "current_provider": "string or null",
    "budget_range": "string or null",
    "timeline": "string or null",
    "pain_points": ["list", "of", "pain points"],
    "interest_level": "high/medium/low/none",
    "callback_time": "string or null",
    "email": "string or null",
    "notes": "any additional notes"
}}

Return ONLY valid JSON, no explanations."""
        
        response = await self._generate(prompt)
        
        try:
            # Clean possible markdown code blocks if the LLM includes them
            response = response.replace("```json", "").replace("```", "").strip()
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Failed to parse qualification data as JSON")
            return {"raw_response": response}
    
    async def _generate(self, prompt: str) -> str:
        """Generate text using configured LLM"""
        
        if self.provider == "openai":
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        
        elif self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        elif self.provider == "gemini":
            model = self.client.GenerativeModel(self.model)
            response = await model.generate_content_async(prompt)
            return response.text.strip()
        
        elif self.provider == "vertex":
            # Vertex AI uses the GenerativeModel class directly
            model = self.client(self.model.replace("vertex-", ""))
            response = await model.generate_content_async(prompt)
            return response.text.strip()
            
        elif self.provider == "local" and self.client:
            # Synchronous call for local llama, wrap in thread
            import functools
            import asyncio
            
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                functools.partial(
                    self.client,
                    prompt=f"Q: {prompt}\nA:",
                    max_tokens=256,
                    stop=["Q:", "\n"],
                    echo=False
                )
            )
            return response["choices"][0]["text"].strip()
    
    async def _generate_chat(
        self,
        system_prompt: str,
        conversation_history: List[Dict[str, str]]
    ) -> str:
        """Generate response in chat context"""
        
        if self.provider == "openai":
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(conversation_history)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=300
            )
            return response.choices[0].message.content.strip()
        
        elif self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=system_prompt,
                messages=conversation_history
            )
            return response.content[0].text.strip()

        elif self.provider == "gemini":
            # Gemini manages history differently, but for simplicity 
            # we will construct a prompt with history
            
            full_prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nCONVERSATION HISTORY:\n"
            for msg in conversation_history:
                role_label = "User" if msg["role"] == "user" else "Agent"
                full_prompt += f"{role_label}: {msg['content']}\n"
            
            full_prompt += "\nAgent: (Respond naturally)"
            
            model = self.client.GenerativeModel(self.model)
            response = await model.generate_content_async(full_prompt)
            return response.text.strip()

        elif self.provider == "vertex":
            full_prompt = f"SYSTEM INSTRUCTIONS:\n{system_prompt}\n\nCONVERSATION HISTORY:\n"
            for msg in conversation_history:
                role_label = "User" if msg["role"] == "user" else "Agent"
                full_prompt += f"{role_label}: {msg['content']}\n"
            
            full_prompt += "\nAgent: (Respond naturally)"
            
            model = self.client(self.model.replace("vertex-", ""))
            response = await model.generate_content_async(full_prompt)
            return response.text.strip()

        elif self.provider == "local" and self.client:
            import functools
            import asyncio
            
            # Construct a chat-like prompt for local models
            prompt = f"<|system|>\n{system_prompt}\n"
            for msg in conversation_history:
                role = "user" if msg["role"] == "user" else "assistant"
                prompt += f"<|{role}|>\n{msg['content']}\n"
            prompt += "<|assistant|>\n"

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                functools.partial(
                    self.client,
                    prompt=prompt,
                    max_tokens=256,
                    stop=["<|user|>", "<|system|>"],
                    echo=False
                )
            )
            return response["choices"][0]["text"].strip()
