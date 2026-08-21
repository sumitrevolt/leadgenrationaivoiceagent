"""
LLM Brain Module
The AI brain that powers conversations using GPT-4/Claude/Gemini
With ML-powered auto-learning and continuous optimization
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.config import settings
from app.utils.logger import setup_logger

# ML Module Imports for Auto-Learning
try:
    from app.ml.brain_optimizer import BrainOptimizer, ConversationContext
    from app.ml.data_pipeline import ConversationDataPipeline, ConversationOutcome
    from app.ml.feedback_loop import CallOutcome, FeedbackLoop
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
    entities: dict[str, Any]


class LLMBrain:
    """
    LLM-powered conversation brain
    Handles intelligent responses, qualification, and objection handling
    """

    # System prompts for different roles
    SYSTEM_PROMPTS = {
        "sales_agent": """Tum {client_name} ke liye phone par baat kar rahe ek warm, natural insaan ho. Tum ek AI ho, par baat ekdam insaan jaisi honi chahiye — robotic ya scripted bilkul nahi.

TUM PHONE PAR HO — sabse zaroori rules:
1. Reply CHHOTA rakho: 1-2 line, ~15-25 shabd. Phone par lambi speech koi nahi sunta.
2. PEHLE customer ne jo kaha use acknowledge karo ("Haan bilkul", "Samajh gaya", "Achha"), PHIR jawab do.
3. Customer agar kuch POOCHHE, to pehle uske sawaal ka seedha jawab do — apni baat baad me.
4. Ek baar me SIRF EK cheez poochho. Kabhi questions ki list mat girao — survey jaisa mat lago.
5. Customer ki HI bhasha aur tone match karo: Hindi me Hindi, Hinglish me Hinglish, English me English.
6. Agar baat clear na sune (awaaz tooti/adhuri), to naturally bolo "samajh nahi aaya" aur dobara poochho — guess mat karo, aage mat badho.
7. Jo cheez woh pehle bata/poochh chuke, dobara mat poochho/repeat mat karo.
8. "Not interested" pe ek baar wajah samjho, phir "naa" ka respect karo aur politely baat khatam karo — pushy bilkul nahi.
9. Agar customer poochhe ki tum AI/bot ho, to SAAF-SAAF "haan, main ek AI assistant hoon" bolo — KABHI inkaar ya jhooth mat bolo (AI-disclosure = compliance, fail-CLOSED; 2026-07-05). Customer ke time ki value do.
10. Hamesha customer ko izzat se 'aap' aur 'sir/madam' bolkar address karo. KABHI 'tum', 'tu', 'yaar', 'bhai' ya informal slang/tone ka use mat karo. Agent ki tone hamesha respectful, polite, aur highly professional honi chahiye.

CLIENT / BUSINESS:
- Company: {client_name}
- Service: {client_service}
- Industry: {niche}

TUMHARA GOAL (natural baat-cheet me, dheere-dheere — sab ek saath nahi): lead ko samajhna (decision-maker hain? abhi kya use karte hain? kya zaroorat/dikkat hai? budget/timeline?) aur ek chhota demo ya callback book karna. Yeh sab tumhare DIMAAG me rahe — customer ke saamne checklist mat banao, ek-ek baat natural flow me aaye.

Sirf agent ka bola jaane wala AGLA sentence likho — koi naam-prefix, stage-direction ya explanation nahi, bas spoken reply.""",
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
""",
    }

    def __init__(self, model: str | None = None, tenant_id: str | None = None):
        self.model = model or settings.default_llm
        self.provider = "unknown"
        self.tenant_id = tenant_id or "default"

        # Initialize ML components for auto-learning.
        # These classes take data/persist directories (not tenant_id) — scope
        # each tenant to its own subdirectory for isolation.
        self.ml_enabled = ML_ENABLED
        if self.ml_enabled:
            try:
                t = self.tenant_id
                self.feedback_loop = FeedbackLoop(data_dir=f"data/feedback/{t}")
                self.brain_optimizer = BrainOptimizer(
                    data_dir=f"data/optimizer/{t}",
                    feedback_loop=self.feedback_loop,
                )
                self.data_pipeline = ConversationDataPipeline(data_dir=f"data/conversations/{t}")
                self.vector_store = VectorStore(persist_directory=f"data/vectorstore/{t}")
                logger.info("🤖 ML Auto-Learning enabled")
            except Exception as e:
                logger.warning(f"ML initialization failed: {e}. Running without ML.")
                self.ml_enabled = False

        # Current conversation tracking for ML
        self.current_conversation_id: str | None = None
        self.current_responses: list[dict[str, Any]] = []

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
        elif any(
            name in self.model.lower()
            for name in ("mistral", "groq", "cerebras", "sambanova", "nvidia", "openrouter")
        ):
            # LeadGen's active stack is the free_ai provider chain. The legacy
            # brain still powers supervisor smoke/voice flows, so accept the
            # configured free model and route generation through the same
            # guarded fallback chain instead of rejecting it as unknown.
            self.client = None
            self.provider = "free_ai"
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
            from google import genai

            self.client = genai.Client(api_key=settings.gemini_api_key)
            self.provider = "gemini"
        except ImportError:
            raise ImportError("google-genai package not installed")

    def _init_vertexai(self):
        """Initialize Google Vertex AI client (GCP VM / ADC)"""
        try:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(
                project=settings.google_cloud_project_id, location=settings.google_cloud_location
            )
            self.client = GenerativeModel
            self.provider = "vertex"
            logger.info(f"🚀 Vertex AI initialized (Project: {settings.google_cloud_project_id})")
        except ImportError:
            raise ImportError(
                "google-cloud-aiplatform package not installed. Run 'pip install google-cloud-aiplatform'"
            )
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
            import os

            from llama_cpp import Llama

            model_path = os.path.abspath(settings.local_llm_path)

            if not os.path.exists(model_path):
                logger.warning(f"Local model not found at {model_path}. Please download it.")
                self.client = None
                return

            self.client = Llama(
                model_path=model_path,
                n_ctx=2048,
                n_gpu_layers=35,  # Push as much as possible to T4
                verbose=False,
            )
            self.provider = "local"
            logger.info(f"💎 Local LLM initialized using GPU (Model: {settings.local_llm_path})")
        except ImportError:
            raise ImportError("llama-cpp-python not installed. Run 'pip install llama-cpp-python'")
        except Exception as e:
            logger.error(f"Local LLM initialization failed: {e}")
            self.client = None

    async def generate_opening(
        self, niche: str, client_name: str, client_service: str, lead_name: str = "Sir/Madam"
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
        conversation_history: list[dict[str, str]],
        niche: str,
        client_name: str,
        client_service: str,
        detected_intent: Intent | None = None,
        lead_data: dict[str, Any] | None = None,
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
                    call_id=self.current_conversation_id or "web-call",
                    tenant_id=self.tenant_id,
                    lead_industry=niche,
                    lead_company=(lead_data or {}).get("company", client_name),
                    lead_city=(lead_data or {}).get("city", ""),
                    current_intent=(detected_intent.intent_type if detected_intent else "general"),
                    conversation_history=conversation_history,
                )

                # Optimized prompt from learned patterns; the (already formatted)
                # default prompt is the base/fallback.
                default_prompt = self._get_default_prompt(client_name, client_service, niche)
                agent_type = (
                    "sales_agent" if client_service != "AI Lead Gen SAAS" else "saas_sales_agent"
                )
                optimized_prompt = await self.brain_optimizer.get_optimized_system_prompt(
                    agent_type=agent_type,
                    industry=niche,
                    base_prompt=default_prompt,
                )
                system_prompt = optimized_prompt or default_prompt

                # RAG context from similar successful conversations.
                rag_items = await self.brain_optimizer.get_rag_context(
                    context=context,
                    current_query=last_user_message,
                    top_k=3,
                )
                if rag_items:
                    rag_text = "\n".join(str(item) for item in rag_items[:3])
                    system_prompt += f"\n\n📚 SIMILAR SUCCESSFUL RESPONSES:\n{rag_text}"

                # Proven best response template for this situation (sync, str).
                best_response = self.feedback_loop.get_best_response(
                    response_type=(detected_intent.intent_type if detected_intent else "general"),
                    industry=niche,
                )
                if best_response:
                    system_prompt += (
                        "\n\n✅ PROVEN RESPONSE STYLE (adapt but follow this pattern):\n"
                        f"{best_response}"
                    )

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
            self.current_responses.append(
                {
                    "user_input": last_user_message,
                    "agent_response": response,
                    "intent": detected_intent.intent_type if detected_intent else None,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return response

    def _get_default_prompt(self, client_name: str, client_service: str, niche: str) -> str:
        """Get default static system prompt.

        ADR-184 (2026-08-21): Enterprise persona registry se agent-specific
        system prompt use karo. Fallback = original static prompts.
        """
        # Try enterprise persona — agent_name se staff_id resolve karo
        try:
            from app.platform.team import get_staff_persona_prompt

            # llm_brain ke andar agent_name attribute nahi hai —
            # default "Swara" use karo (primary telecaller)
            persona = get_staff_persona_prompt(
                "swara",
                client_name=client_name,
                niche=niche,
                client=client_name,
            )
            if persona:
                return persona
        except Exception:
            pass

        # Original fallback prompts
        if client_service == "AI Lead Gen SAAS":
            return self.SYSTEM_PROMPTS["saas_sales_agent"].format(
                client_name=client_name, niche=niche
            )
        else:
            return self.SYSTEM_PROMPTS["sales_agent"].format(
                client_name=client_name, client_service=client_service, niche=niche
            )

    async def handle_objection(
        self, objection: str, client_name: str, client_service: str, niche: str
    ) -> str:
        """Generate response to handle specific objection - ML enhanced"""

        # Check ML for proven objection responses
        if self.ml_enabled:
            try:
                best_objection_response = await self.feedback_loop.get_best_objection_response(
                    objection=objection, industry=niche
                )

                if best_objection_response and best_objection_response.get("success_rate", 0) > 0.6:
                    logger.info(f"📚 Using ML-proven objection response for: {objection[:50]}")
                    return best_objection_response.get(
                        "response",
                        await self._generate_objection_response(
                            objection, client_name, client_service, niche
                        ),
                    )

                # Get similar objection examples from vector store.
                # BUGFIX (2026-07-05): kwarg was `limit=2` but signature is
                # `top_k` → TypeError har call pe (broad except me swallow ho jaata,
                # objection-RAG context KABHI prompt tak nahi pahunchta tha).
                # Result-dicts me keys `user_message`/`agent_response` hain (vector_store
                # metadata), `objection`/`response` nahi.
                similar = await self.vector_store.find_objection_responses(
                    objection=objection, industry=niche, top_k=2
                )

                if similar:
                    extra_context = "\n\nSIMILAR SUCCESSFUL OBJECTION HANDLES:\n"
                    for s in similar:
                        extra_context += f"- Objection: {s.get('user_message', '')[:100]}\n  Response: {s.get('agent_response', '')[:150]}\n"

                    return await self._generate_objection_response(
                        objection, client_name, client_service, niche, extra_context
                    )
            except Exception as e:
                logger.warning(f"ML objection handling failed: {e}")

        return await self._generate_objection_response(
            objection, client_name, client_service, niche
        )

    async def _generate_objection_response(
        self,
        objection: str,
        client_name: str,
        client_service: str,
        niche: str,
        extra_context: str = "",
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
        conversation_history: list[dict[str, str]],
        lead_data: dict[str, Any],
        niche: str,
        appointment_booked: bool = False,
        callback_scheduled: bool = False,
        notes: str | None = None,
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
                    metadata={"call_duration": call_duration},
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
                    "notes": notes,
                },
            )

            # Store in vector database for RAG
            if conv_outcome in [
                ConversationOutcome.APPOINTMENT_BOOKED,
                ConversationOutcome.CALLBACK_SCHEDULED,
                ConversationOutcome.INTERESTED,
            ]:
                await self.vector_store.add_conversation(
                    conversation_id=self.current_conversation_id,
                    turns=conversation_history,
                    outcome=conv_outcome.value,
                    industry=niche,
                    success_score=1.0 if appointment_booked else 0.7,
                )

            logger.info(f"📊 Recorded call outcome: {outcome} for learning")

            # Reset conversation tracking
            self.current_conversation_id = None
            self.current_responses = []

        except Exception as e:
            logger.error(f"Failed to record call outcome: {e}")

    async def extract_qualification_data(
        self, conversation_history: list[dict[str, str]]
    ) -> dict[str, Any]:
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

        if self.provider == "free_ai":
            from app.voice_agent import free_ai

            text, _provider = await free_ai.chat(
                system="",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=500,
                temperature=0.7,
                profile="realtime",
            )
            return (text or "").strip()

        if self.provider == "openai":
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500,
            )
            return response.choices[0].message.content.strip()

        elif self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model, max_tokens=500, messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        elif self.provider == "gemini":
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            return response.text.strip()

        elif self.provider == "vertex":
            # Vertex AI uses the GenerativeModel class directly
            model = self.client(self.model.replace("vertex-", ""))
            response = await model.generate_content_async(prompt)
            return response.text.strip()

        elif self.provider == "local" and self.client:
            # Synchronous call for local llama, wrap in thread
            import asyncio
            import functools

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                functools.partial(
                    self.client,
                    prompt=f"Q: {prompt}\nA:",
                    max_tokens=256,
                    stop=["Q:", "\n"],
                    echo=False,
                ),
            )
            return response["choices"][0]["text"].strip()

    async def _generate_chat(
        self, system_prompt: str, conversation_history: list[dict[str, str]]
    ) -> str:
        """Generate response in chat context"""

        if self.provider == "free_ai":
            from app.voice_agent import free_ai

            text, _provider = await free_ai.chat(
                system=system_prompt,
                messages=conversation_history,
                max_tokens=300,
                temperature=0.7,
                profile="realtime",
            )
            return (text or "").strip()

        if self.provider == "openai":
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(conversation_history)

            response = await self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=0.7, max_tokens=300
            )
            return response.choices[0].message.content.strip()

        elif self.provider == "anthropic":
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system=system_prompt,
                messages=conversation_history,
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

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=full_prompt,
            )
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
            import asyncio
            import functools

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
                    echo=False,
                ),
            )
            return response["choices"][0]["text"].strip()
