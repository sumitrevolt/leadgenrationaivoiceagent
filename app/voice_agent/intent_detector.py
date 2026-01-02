"""
Intent Detection Module
Detects user intent from speech for smart response handling
"""
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum
import re

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class IntentType(Enum):
    """Possible user intents"""
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CALLBACK_REQUEST = "callback_request"
    APPOINTMENT_INTEREST = "appointment_interest"
    OBJECTION = "objection"
    QUESTION = "question"
    GREETING = "greeting"
    GOODBYE = "goodbye"
    OPT_OUT = "opt_out"
    CONFUSED = "confused"
    DECISION_MAKER_NO = "decision_maker_no"
    SEND_EMAIL = "send_email"
    BUSY = "busy"
    PRICE_QUERY = "price_query"
    NEUTRAL = "neutral"


@dataclass
class DetectedIntent:
    """Result of intent detection"""
    intent_type: str
    confidence: float
    entities: Dict[str, Any]
    raw_text: str
    language: str  # "en", "hi", "hinglish"


class IntentDetector:
    """
    Detects user intent from transcribed speech
    Uses pattern matching + LLM for accuracy
    """
    
    # Intent patterns (supports Hindi, English, Hinglish)
    INTENT_PATTERNS = {
        IntentType.OPT_OUT: [
            r"stop (calling|calls)",
            r"remove (my|this) number",
            r"don'?t call (me|again)",
            r"unsubscribe",
            r"mat karo call",
            r"band karo",
            r"number hatao",
            r"press(ed)? 9",
        ],
        IntentType.NOT_INTERESTED: [
            r"not interested",
            r"no thanks",
            r"nahi chahiye",
            r"interest nahi",
            r"don'?t (want|need)",
            r"zaroorat nahi",
            r"no need",
        ],
        IntentType.CALLBACK_REQUEST: [
            r"call (me )?(back|later)",
            r"baad me(in)? call",
            r"busy (right now|abhi)",
            r"can you call (later|tomorrow|next week)",
            r"kal call karna",
            r"shaam ko call",
        ],
        IntentType.APPOINTMENT_INTEREST: [
            r"(book|schedule|set up) (a )?(meeting|appointment|call)",
            r"let'?s (meet|talk|discuss)",
            r"milte hain",
            r"meeting (rakh|fix|schedule)",
            r"yes.*(meeting|appointment)",
            r"interested.*(meeting|discuss)",
        ],
        IntentType.SEND_EMAIL: [
            r"send (me )?(an )?email",
            r"email (kar|bhej|send)",
            r"mail (kar|bhej)",
            r"details email",
        ],
        IntentType.BUSY: [
            r"(i'?m )?busy",
            r"in (a )?meeting",
            r"not (a )?good time",
            r"meeting me(in)? hun",
            r"abhi busy",
            r"can'?t talk",
        ],
        IntentType.DECISION_MAKER_NO: [
            r"i'?m not the (right|decision)",
            r"talk to (my )?boss",
            r"owner se baat",
            r"main decide nahi",
            r"senior se (baat|contact)",
        ],
        IntentType.PRICE_QUERY: [
            r"(how much|what'?s the|kitna) (cost|price|charge)",
            r"price kya hai",
            r"kitne (paise|rupees|rs)",
            r"cost batao",
            r"rate kya hai",
        ],
        IntentType.INTERESTED: [
            r"(yes|yeah|haan|ji).*(interested|tell me more)",
            r"sounds (good|interesting)",
            r"tell me more",
            r"acha batao",
            r"interested (hun|hain|hu)",
            r"let me (know|hear)",
        ],
        IntentType.GREETING: [
            r"^(hello|hi|hey|namaste|namaskar)$",
            r"good (morning|afternoon|evening)",
        ],
        IntentType.GOODBYE: [
            r"(bye|goodbye|thanks|thank you)$",
            r"(ok|okay) (bye|thanks)",
            r"dhanyawad",
            r"shukriya",
        ],
    }
    
    def __init__(self, use_llm_fallback: bool = True):
        self.use_llm_fallback = use_llm_fallback
        logger.info("🎯 Intent Detector initialized")
    
    async def detect(
        self,
        text: str,
        context: Optional[Any] = None
    ) -> DetectedIntent:
        """
        Detect intent from user speech
        
        Args:
            text: Transcribed user speech
            context: Call context for better detection
            
        Returns:
            DetectedIntent with type, confidence, and entities
        """
        text_lower = text.lower().strip()
        
        # Detect language
        language = self._detect_language(text)
        
        # Pattern-based detection first (fast)
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    logger.debug(f"Pattern matched: {intent_type.value} for '{text}'")
                    return DetectedIntent(
                        intent_type=intent_type.value,
                        confidence=0.85,
                        entities=self._extract_entities(text, intent_type),
                        raw_text=text,
                        language=language
                    )
        
        # LLM-based detection for complex cases
        if self.use_llm_fallback:
            return await self._detect_with_llm(text, language, context)
        
        # Default to neutral
        return DetectedIntent(
            intent_type=IntentType.NEUTRAL.value,
            confidence=0.5,
            entities={},
            raw_text=text,
            language=language
        )
    
    def _detect_language(self, text: str) -> str:
        """Detect if text is Hindi, English, or Hinglish"""
        # Simple detection based on character ranges
        hindi_chars = len(re.findall(r'[\u0900-\u097F]', text))
        english_chars = len(re.findall(r'[a-zA-Z]', text))
        
        total = hindi_chars + english_chars
        if total == 0:
            return "unknown"
        
        hindi_ratio = hindi_chars / total
        
        if hindi_ratio > 0.7:
            return "hi"
        elif hindi_ratio > 0.2:
            return "hinglish"
        else:
            return "en"
    
    def _extract_entities(
        self,
        text: str,
        intent_type: IntentType
    ) -> Dict[str, Any]:
        """Extract relevant entities based on intent"""
        entities = {}
        text_lower = text.lower()
        
        # Extract time mentions
        time_patterns = [
            r'(\d{1,2})\s*(am|pm|बजे)',
            r'(morning|afternoon|evening|subah|dopahar|shaam)',
            r'(today|tomorrow|kal|aaj|parso)',
            r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)',
            r'(somvar|mangalvar|budhvar|guruvar|shukravar|shanivar|ravivar)'
        ]
        
        for pattern in time_patterns:
            match = re.search(pattern, text_lower)
            if match:
                entities["time_mention"] = match.group()
                break
        
        # Extract phone/email if mentioned
        phone_match = re.search(r'(\+91)?[\s-]?\d{10}', text)
        if phone_match:
            entities["phone"] = phone_match.group()
        
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if email_match:
            entities["email"] = email_match.group()
        
        return entities
    
    async def _detect_with_llm(
        self,
        text: str,
        language: str,
        context: Optional[Any] = None
    ) -> DetectedIntent:
        """Use LLM for complex intent detection"""
        try:
            from app.voice_agent.llm_brain import LLMBrain
            
            llm = LLMBrain()
            
            prompt = f"""Classify the intent of this customer response in a sales call:

Text: "{text}"
Language: {language}

Possible intents:
- interested: Customer shows interest in learning more
- not_interested: Customer clearly not interested
- callback_request: Wants to be called back later
- appointment_interest: Wants to schedule a meeting
- objection: Has a concern or objection
- question: Asking a question about the product/service
- busy: Currently busy, can't talk
- opt_out: Wants to stop receiving calls
- send_email: Wants information via email
- price_query: Asking about pricing
- neutral: No clear intent

Respond with ONLY the intent name and confidence (0-1), like:
interested 0.85"""
            
            response = await llm._generate(prompt)
            parts = response.strip().split()
            
            if len(parts) >= 2:
                intent = parts[0].lower()
                confidence = float(parts[1])
            else:
                intent = parts[0].lower() if parts else "neutral"
                confidence = 0.7
            
            return DetectedIntent(
                intent_type=intent,
                confidence=confidence,
                entities=self._extract_entities(text, IntentType.NEUTRAL),
                raw_text=text,
                language=language
            )
            
        except Exception as e:
            logger.error(f"LLM intent detection failed: {e}")
            return DetectedIntent(
                intent_type=IntentType.NEUTRAL.value,
                confidence=0.5,
                entities={},
                raw_text=text,
                language=language
            )
