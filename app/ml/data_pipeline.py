"""
Conversation Data Pipeline
Captures every conversation with embeddings for ML training

Features:
- Store all conversations in structured format
- Generate embeddings using sentence-transformers
- Track outcomes (appointment/rejection/callback)
- Extract features for ML models
- Export data for batch training
"""
import json
import hashlib
from datetime import datetime
from enum import Enum
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ConversationOutcome(Enum):
    """Possible outcomes of a conversation"""
    APPOINTMENT_BOOKED = "appointment_booked"
    CALLBACK_SCHEDULED = "callback_scheduled"
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    WRONG_NUMBER = "wrong_number"
    DND = "dnd"
    UNKNOWN = "unknown"


@dataclass
class ConversationTurn:
    """Single turn in a conversation"""
    role: str  # "agent" or "user"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: Optional[str] = None
    confidence: float = 0.0
    entities: Dict[str, Any] = field(default_factory=dict)
    response_time_ms: int = 0  # Time taken to generate response
    
    def to_dict(self) -> Dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "intent": self.intent,
            "confidence": self.confidence,
            "entities": self.entities,
            "response_time_ms": self.response_time_ms
        }


@dataclass
class ConversationFeatures:
    """
    Extracted features for ML training
    These features are used to train lead scoring and success prediction models
    """
    # Call metadata
    call_duration_seconds: int = 0
    total_turns: int = 0
    agent_turns: int = 0
    user_turns: int = 0
    
    # Engagement metrics
    avg_user_response_length: float = 0.0
    avg_agent_response_length: float = 0.0
    user_question_count: int = 0
    user_objection_count: int = 0
    
    # Intent distribution
    intent_counts: Dict[str, int] = field(default_factory=dict)
    
    # Sentiment indicators
    positive_signals: int = 0  # "interested", "tell me more", etc.
    negative_signals: int = 0  # "not interested", "busy", etc.
    
    # Qualification indicators
    is_decision_maker: bool = False
    has_budget: bool = False
    has_timeline: bool = False
    has_pain_point: bool = False
    
    # Script effectiveness
    script_used: str = ""
    script_variant: str = ""  # For A/B testing
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ConversationRecord:
    """
    Complete record of a conversation for ML training
    """
    # Identifiers
    conversation_id: str
    call_id: str
    tenant_id: str
    
    # Lead info
    lead_id: str
    lead_phone: str
    lead_company: str
    lead_industry: str
    lead_city: str
    
    # Conversation data
    turns: List[ConversationTurn] = field(default_factory=list)
    
    # Outcome
    outcome: ConversationOutcome = ConversationOutcome.UNKNOWN
    outcome_details: Dict[str, Any] = field(default_factory=dict)
    
    # Extracted features
    features: ConversationFeatures = field(default_factory=ConversationFeatures)
    
    # Embeddings (populated after processing)
    conversation_embedding: List[float] = field(default_factory=list)
    turn_embeddings: List[List[float]] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=datetime.now)
    language: str = "hinglish"
    model_used: str = "gemini-1.5-flash"
    
    # Quality scores (for training)
    human_rating: Optional[int] = None  # 1-5 if reviewed
    predicted_quality: float = 0.0
    conversion_probability: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "conversation_id": self.conversation_id,
            "call_id": self.call_id,
            "tenant_id": self.tenant_id,
            "lead_id": self.lead_id,
            "lead_phone": self.lead_phone,
            "lead_company": self.lead_company,
            "lead_industry": self.lead_industry,
            "lead_city": self.lead_city,
            "turns": [t.to_dict() for t in self.turns],
            "outcome": self.outcome.value,
            "outcome_details": self.outcome_details,
            "features": self.features.to_dict(),
            "conversation_embedding": self.conversation_embedding,
            "created_at": self.created_at.isoformat(),
            "language": self.language,
            "model_used": self.model_used,
            "human_rating": self.human_rating,
            "predicted_quality": self.predicted_quality,
            "conversion_probability": self.conversion_probability
        }


class ConversationDataPipeline:
    """
    Manages conversation data for ML training
    
    Responsibilities:
    1. Capture conversations in real-time
    2. Extract features from conversations
    3. Generate embeddings for semantic search
    4. Store data for batch training
    5. Export training datasets
    """
    
    def __init__(self, data_dir: str = "data/conversations"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory buffer for recent conversations
        self.buffer: List[ConversationRecord] = []
        self.buffer_size = 100
        
        # Embedding model (lazy loaded)
        self._embedder = None
        
        logger.info(f"📊 Data pipeline initialized: {self.data_dir}")
    
    @property
    def embedder(self):
        """Lazy load embedding model"""
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                # Use multilingual model for Hindi/English support
                self._embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
                logger.info("🧠 Embedding model loaded")
            except ImportError:
                logger.warning("sentence-transformers not installed, embeddings disabled")
        return self._embedder
    
    def generate_conversation_id(self, call_id: str, timestamp: datetime) -> str:
        """Generate unique conversation ID"""
        raw = f"{call_id}_{timestamp.isoformat()}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
    
    async def capture_conversation(
        self,
        call_id: str,
        tenant_id: str,
        lead_info: Dict,
        turns: List[Dict],
        outcome: str,
        outcome_details: Dict = None
    ) -> ConversationRecord:
        """
        Capture a completed conversation for ML training
        
        Args:
            call_id: Unique call identifier
            tenant_id: Tenant who made the call
            lead_info: Lead details (phone, company, industry, city)
            turns: List of conversation turns
            outcome: Call outcome (appointment_booked, not_interested, etc.)
            outcome_details: Additional outcome info (appointment time, callback time)
        
        Returns:
            ConversationRecord ready for training
        """
        
        # Create conversation record
        record = ConversationRecord(
            conversation_id=self.generate_conversation_id(call_id, datetime.now()),
            call_id=call_id,
            tenant_id=tenant_id,
            lead_id=lead_info.get("lead_id", ""),
            lead_phone=lead_info.get("phone", ""),
            lead_company=lead_info.get("company", ""),
            lead_industry=lead_info.get("industry", ""),
            lead_city=lead_info.get("city", ""),
            outcome=ConversationOutcome(outcome) if outcome else ConversationOutcome.UNKNOWN,
            outcome_details=outcome_details or {}
        )
        
        # Parse turns
        for turn_data in turns:
            turn = ConversationTurn(
                role=turn_data.get("role", "agent"),
                content=turn_data.get("content", ""),
                intent=turn_data.get("intent"),
                confidence=turn_data.get("confidence", 0.0),
                entities=turn_data.get("entities", {}),
                response_time_ms=turn_data.get("response_time_ms", 0)
            )
            record.turns.append(turn)
        
        # Extract features
        record.features = self._extract_features(record)
        
        # Generate embeddings
        await self._generate_embeddings(record)
        
        # Store record
        self._store_record(record)
        
        # Add to buffer
        self.buffer.append(record)
        if len(self.buffer) > self.buffer_size:
            self.buffer.pop(0)
        
        logger.info(
            f"📝 Conversation captured: {record.conversation_id} "
            f"| Outcome: {record.outcome.value} "
            f"| Turns: {len(record.turns)}"
        )
        
        return record
    
    def _extract_features(self, record: ConversationRecord) -> ConversationFeatures:
        """Extract ML features from conversation"""
        
        features = ConversationFeatures()
        
        # Basic counts
        features.total_turns = len(record.turns)
        features.agent_turns = sum(1 for t in record.turns if t.role == "agent")
        features.user_turns = sum(1 for t in record.turns if t.role == "user")
        
        # Response lengths
        user_contents = [t.content for t in record.turns if t.role == "user"]
        agent_contents = [t.content for t in record.turns if t.role == "agent"]
        
        if user_contents:
            features.avg_user_response_length = sum(len(c) for c in user_contents) / len(user_contents)
        if agent_contents:
            features.avg_agent_response_length = sum(len(c) for c in agent_contents) / len(agent_contents)
        
        # Intent distribution
        for turn in record.turns:
            if turn.intent:
                features.intent_counts[turn.intent] = features.intent_counts.get(turn.intent, 0) + 1
        
        # Count questions and objections
        question_keywords = ["?", "kya", "kaise", "kab", "kitna", "kyun", "what", "how", "when"]
        objection_keywords = ["nahi", "busy", "baad mein", "not interested", "no need"]
        
        for turn in record.turns:
            if turn.role == "user":
                content_lower = turn.content.lower()
                if any(kw in content_lower for kw in question_keywords):
                    features.user_question_count += 1
                if any(kw in content_lower for kw in objection_keywords):
                    features.user_objection_count += 1
        
        # Positive/negative signals
        positive_keywords = ["interested", "batao", "tell me", "sounds good", "theek hai", "haan"]
        negative_keywords = ["not interested", "nahi chahiye", "busy", "mat karo call"]
        
        for turn in record.turns:
            if turn.role == "user":
                content_lower = turn.content.lower()
                if any(kw in content_lower for kw in positive_keywords):
                    features.positive_signals += 1
                if any(kw in content_lower for kw in negative_keywords):
                    features.negative_signals += 1
        
        # Qualification indicators from entities
        for turn in record.turns:
            entities = turn.entities or {}
            if entities.get("is_decision_maker"):
                features.is_decision_maker = True
            if entities.get("has_budget"):
                features.has_budget = True
            if entities.get("timeline"):
                features.has_timeline = True
            if entities.get("pain_point"):
                features.has_pain_point = True
        
        return features
    
    async def _generate_embeddings(self, record: ConversationRecord):
        """Generate embeddings for semantic search"""
        
        if not self.embedder:
            return
        
        try:
            # Full conversation embedding
            full_text = " ".join([t.content for t in record.turns])
            record.conversation_embedding = self.embedder.encode(full_text).tolist()
            
            # Individual turn embeddings
            for turn in record.turns:
                embedding = self.embedder.encode(turn.content).tolist()
                record.turn_embeddings.append(embedding)
                
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
    
    def _store_record(self, record: ConversationRecord):
        """Store conversation record to disk"""
        
        # Organize by date and tenant
        date_str = record.created_at.strftime("%Y-%m-%d")
        tenant_dir = self.data_dir / record.tenant_id / date_str
        tenant_dir.mkdir(parents=True, exist_ok=True)
        
        # Save as JSON
        file_path = tenant_dir / f"{record.conversation_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, ensure_ascii=False, indent=2)
    
    def get_training_data(
        self,
        tenant_id: Optional[str] = None,
        outcome: Optional[ConversationOutcome] = None,
        min_turns: int = 3,
        limit: int = 1000
    ) -> List[ConversationRecord]:
        """
        Get conversation records for training
        
        Args:
            tenant_id: Filter by tenant (None for all)
            outcome: Filter by outcome (None for all)
            min_turns: Minimum conversation turns
            limit: Maximum records to return
        
        Returns:
            List of ConversationRecords
        """
        
        records = []
        
        # Walk through data directory
        search_path = self.data_dir / tenant_id if tenant_id else self.data_dir
        
        if not search_path.exists():
            return records
        
        for json_file in search_path.rglob("*.json"):
            if len(records) >= limit:
                break
            
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Filter by outcome
                if outcome and data.get("outcome") != outcome.value:
                    continue
                
                # Filter by min turns
                if len(data.get("turns", [])) < min_turns:
                    continue
                
                # Reconstruct record (simplified)
                record = ConversationRecord(
                    conversation_id=data["conversation_id"],
                    call_id=data["call_id"],
                    tenant_id=data["tenant_id"],
                    lead_id=data["lead_id"],
                    lead_phone=data["lead_phone"],
                    lead_company=data["lead_company"],
                    lead_industry=data["lead_industry"],
                    lead_city=data["lead_city"],
                    outcome=ConversationOutcome(data["outcome"]),
                    conversation_embedding=data.get("conversation_embedding", [])
                )
                
                records.append(record)
                
            except Exception as e:
                logger.warning(f"Failed to load {json_file}: {e}")
        
        return records
    
    def export_for_finetuning(
        self,
        output_file: str,
        format: str = "jsonl",  # jsonl, csv, parquet
        include_successful_only: bool = True
    ) -> int:
        """
        Export conversations for LLM fine-tuning
        
        Returns:
            Number of records exported
        """
        
        successful_outcomes = {
            ConversationOutcome.APPOINTMENT_BOOKED,
            ConversationOutcome.CALLBACK_SCHEDULED,
            ConversationOutcome.INTERESTED
        }
        
        records = self.get_training_data(limit=10000)
        
        if include_successful_only:
            records = [r for r in records if r.outcome in successful_outcomes]
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == "jsonl":
            with open(output_path, "w", encoding="utf-8") as f:
                for record in records:
                    # Format for fine-tuning (OpenAI style)
                    for i in range(0, len(record.turns) - 1, 2):
                        if i + 1 < len(record.turns):
                            entry = {
                                "messages": [
                                    {"role": "user", "content": record.turns[i].content},
                                    {"role": "assistant", "content": record.turns[i + 1].content}
                                ]
                            }
                            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        
        logger.info(f"📤 Exported {len(records)} conversations to {output_file}")
        return len(records)
    
    def get_stats(self) -> Dict:
        """Get pipeline statistics"""
        
        total_files = sum(1 for _ in self.data_dir.rglob("*.json"))
        
        # Count outcomes
        outcome_counts = {}
        for record in self.buffer:
            outcome = record.outcome.value
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
        
        return {
            "total_conversations": total_files,
            "buffer_size": len(self.buffer),
            "recent_outcomes": outcome_counts,
            "data_directory": str(self.data_dir)
        }


# Singleton instance
data_pipeline = ConversationDataPipeline()
