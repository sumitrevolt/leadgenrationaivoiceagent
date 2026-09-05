"""
Swara Voice Learning Pipeline — voice_learning_event storage + learning loop.

Rule 4: Every useful owner-facing OpenClaw voice interaction generates a structured
        learning event: voice_learning_event.
Rule 5: English → Swara Hinglish learning loop with candidate generation + evaluation.
Rule 6: Owner corrections → high-priority learning events.
Rule 9:  Observe → Candidate → Test → Score → Approve → Version → Deploy → Monitor → Rollback

Storage: Redis (primary, fast) + JSONL persistence (durability). Events are
         versioned and tagged with quality metadata.

Event schema captures:
    - original_text, language, generated_audio_metadata
    - intended_meaning, context, domain
    - pronunciation_issues, hindi_english_ratio
    - successful_phrase, rejected_phrase, owner_corrections
    - speaking_style, confidence, emotional_tone
    - technical_vocabulary, timestamp, model/version, voice_id
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Literal

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# EVENT SCHEMA
# -----------------------------------------------------------------------------

LearningDomain = Literal[
    "greeting", "lead_qualification", "appointment_booking", "pricing",
    "objection_handling", "customer_confusion", "follow_up", "closing",
    "escalation", "payment", "rescheduling", "support", "goodbye",
    "sales_discovery", "owner_communication", "other"
]

EmotionalTone = Literal[
    "neutral", "warm", "confident", "empathetic", "energetic",
    "concerned", "professional", "friendly", "assertive"
]

SpeakingStyle = Literal[
    "formal", "casual", "persuasive", "educational", "consultative",
    "transactional", "relationship_building", "crisis_management"
]

CollectionSource = Literal[
    "real_call", "shadow_eval", "owner_interaction", "ab_test",
    "manual_entry", "language_adaptation"
]


@dataclass
class AudioMetadata:
    """Metadata about generated audio for a learning event."""
    provider: str
    voice_id: str
    model: str | None
    format: str  # "mp3" | "wav" | "pcm"
    duration_ms: int | None = None
    size_bytes: int | None = None


@dataclass
class VoiceLearningEvent:
    """Structured learning event captured from voice interactions.

    Per Rule 4, this captures everything needed to evaluate and improve
    Swara's voice behavior. Candidates must pass evaluation before
    becoming production (Rule 9).
    """
    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    version: str = "swara_voice_profile_v1"

    # Core text content
    original_text: str = ""
    language: str = "en"  # "en" | "hi" | "hinglish"
    intended_meaning: str = ""

    # Context
    domain: LearningDomain = "other"
    context: str = ""  # call context: niche, stage, customer type
    collection_source: CollectionSource = "real_call"

    # Hinglish adaptation pipeline (Rule 5)
    hindi_english_ratio: float = 0.0  # 0.0 = pure English, 1.0 = pure Hindi
    english_source: str | None = None  # if adapted from English
    swara_hinglish_candidate: str | None = None  # candidate Hinglish version
    pronunciation_normalized: str | None = None  # phoneme-adjusted form

    # Pronunciation tracking (Rule 7)
    pronunciation_issues: list[str] = field(default_factory=list)
    pronunciation_suggestions: list[dict[str, str]] = field(default_factory=list)

    # Evaluation metadata (Rule 10 quality gates)
    confidence: float = 0.0  # model confidence score 0-1
    meaning_preservation: float = 0.0  # 0-1, must be >= 0.98 to promote
    intent_preservation: float = 0.0  # 0-1, must be >= 0.98 to promote
    natural_hinglish: float = 0.0  # 0-1, must be >= 0.95 to promote
    pronunciation_quality: float = 0.0  # 0-1, must be >= 0.95 to promote
    persona_consistency: float = 0.0  # 0-1, must be >= 0.95 to promote
    hallucination_risk: str = "unknown"  # "acceptable" | "low" | "high"
    policy_safety: str = "unknown"  # "pass" | "fail"
    customer_data_leakage: str = "unknown"  # "zero" | "detected"
    critical_regression: bool = False  # must be False to promote

    # Owner corrections (Rule 6)
    owner_corrections: list[dict[str, str]] = field(default_factory=list)
    # Each correction: {incorrect, corrected, reason, affected_intent, timestamp}

    # Audio metadata
    audio_metadata: AudioMetadata | None = None

    # Speaking style
    speaking_style: SpeakingStyle = "casual"
    emotional_tone: EmotionalTone = "neutral"
    technical_vocabulary: list[str] = field(default_factory=list)

    # Lifecycle / status
    status: Literal["collected", "candidate", "approved", "rejected", "in_production"] = "collected"
    promotion_score: float = 0.0  # composite score for promotion ranking
    promoted_to: list[str] = field(default_factory=list)  # which golden utterance/version it became
    rejection_reason: str | None = None

    # Timestamps
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_evaluated: str | None = None

    # Model/version tracking (Rule 19)
    model_version: str = "swara_voice_profile_v1"
    llm_model: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# STORAGE BACKEND
# -----------------------------------------------------------------------------

class VoiceLearningStore:
    """
    Storage backend for voice_learning_event records.

    Primary: Redis (fast access for real-time eval/shadow mode)
    Secondary: JSONL file (durability + batch processing)

    Rule 9: Candidates must pass evaluation before production promotion.
    Rule 6: Owner corrections are flagged high-priority.
    """

    def __init__(self) -> None:
        self._redis = None
        self._redis_connected = False
        self._jsonl_path: str | None = None
        self._events: list[VoiceLearningEvent] = []  # in-process fallback

    def _init_redis(self) -> bool:
        """Initialize Redis connection (optional — falls back to in-process)."""
        if self._redis_connected:
            return self._redis is not None
        try:
            from app.platform.extensions import get_redis

            self._redis = get_redis()
            self._redis_connected = True
        except Exception as e:
            logger.debug(f"[voice_learning] Redis not available: {e}")
            self._redis = None
            self._redis_connected = True  # mark as "tried"
        return self._redis is not None

    def _init_jsonl(self) -> str | None:
        """Initialize JSONL persistence path."""
        if self._jsonl_path is not None:
            return self._jsonl_path
        base = os.getenv("VOICE_LEARNING_DATA_DIR", "data/voice_learning")
        try:
            os.makedirs(base, exist_ok=True)
            self._jsonl_path = os.path.join(base, f"learning_events.jsonl")
        except Exception as e:
            logger.warning(f"[voice_learning] Cannot init JSONL path: {e}")
            self._jsonl_path = None
        return self._jsonl_path

    def store(self, event: VoiceLearningEvent) -> None:
        """Store a voice learning event.

        Persists to:
        1. Redis (if available) — for real-time shadow eval
        2. JSONL file (if writable) — for durability + batch processing
        3. In-process list — always works as fallback
        """
        self._redis_connected == False and self._init_redis()
        self._init_jsonl()

        event_dict = event.to_dict()

        # 1. In-process (always works)
        self._events.append(event)

        # 2. Redis (fast access)
        if self._redis:
            try:
                key = f"voice_learning:{event.event_id}"
                self._redis.setex(key, 86400 * 30, json.dumps(event_dict))  # 30-day TTL
                # Index by status + priority
                if event.status == "candidate":
                    priority = 10 if event.owner_corrections else 5
                    self._redis.zadd(
                        "voice_learning_candidates",
                        {event.event_id: priority}
                    )
                    logger.debug(f"[voice_learning] Stored candidate {event.event_id} (priority={priority})")
            except Exception as e:
                logger.warning(f"[voice_learning] Redis store failed: {e}")

        # 3. JSONL persistence
        if self._jsonl_path:
            try:
                with open(self._jsonl_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(event_dict, ensure_ascii=False) + "\n")
            except Exception as e:
                logger.warning(f"[voice_learning] JSONL store failed: {e}")

        # Log high-priority events (Rule 6: owner corrections)
        if event.owner_corrections:
            logger.info(f"[voice_learning] HIGH-PRIORITY owner correction: {event.event_id}")

    def get_candidates(self, limit: int = 100, high_priority_only: bool = False) -> list[VoiceLearningEvent]:
        """Get candidate events for evaluation (pending promotion)."""
        if self._redis and not high_priority_only:
            try:
                ids = self._redis.zrange("voice_learning_candidates", 0, limit - 1)
                events: list[VoiceLearningEvent] = []
                for eid in ids:
                    key = f"voice_learning:{eid.decode()}"
                    raw = self._redis.get(key)
                    if raw:
                        events.append(VoiceLearningEvent(**json.loads(raw)))
                    # Remove from candidate index (consumed)
                    self._redis.zrem("voice_learning_candidates", eid)
                return events
            except Exception as e:
                logger.warning(f"[voice_learning] Redis candidate fetch failed: {e}")

        # Fallback: in-process
        candidates = [e for e in self._events if e.status == "candidate"]
        if high_priority_only:
            candidates = [e for e in candidates if e.owner_corrections]
        return candidates[:limit]

    def get_production_events(self, domain: str | None = None, limit: int = 50) -> list[VoiceLearningEvent]:
        """Get events that are in production (for observability + shadow comparison)."""
        events = [e for e in self._events if e.status == "in_production"]
        if domain:
            events = [e for e in events if e.domain == domain]
        return events[-limit:] if limit else events

    def update_status(self, event_id: str, status: str, rejection_reason: str | None = None) -> bool:
        """Update the status of a learning event."""
        for event in self._events:
            if event.event_id == event_id:
                event.status = status  # type: ignore[assignment]
                if status == "approved" and "approved" not in event.promoted_to:
                    event.promoted_to.append(f"approved@{datetime.now(timezone.utc).isoformat()}")
                if status == "rejected":
                    event.rejection_reason = rejection_reason
                event.last_evaluated = datetime.now(timezone.utc).isoformat()
                # Persist update to JSONL (append updated version)
                if self._jsonl_path:
                    try:
                        with open(self._jsonl_path, "a", encoding="utf-8") as f:
                            updated = asdict(event)
                            updated["status_update"] = True
                            f.write(json.dumps(updated, ensure_ascii=False) + "\n")
                    except Exception as e:
                        logger.warning(f"[voice_learning] JSONL update failed: {e}")
                return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get storage statistics for observability (Rule 18)."""
        statuses = {}
        for event in self._events:
            statuses[event.status] = statuses.get(event.status, 0) + 1
        high_priority = sum(1 for e in self._events if e.owner_corrections)
        return {
            "total_events": len(self._events),
            "by_status": statuses,
            "high_priority_corrections": high_priority,
            "redis_connected": self._redis is not None,
            "jsonl_path": self._jsonl_path,
        }


# -----------------------------------------------------------------------------
# SINGLETON
# -----------------------------------------------------------------------------

_store: VoiceLearningStore | None = None


def get_voice_learning_store() -> VoiceLearningStore:
    """Get the singleton VoiceLearningStore."""
    global _store
    if _store is None:
        _store = VoiceLearningStore()
    return _store


# -----------------------------------------------------------------------------
# EVENT FACTORY + HIGH-LEVEL API
# -----------------------------------------------------------------------------

def record_voice_event(
    original_text: str,
    language: str,
    intended_meaning: str,
    domain: LearningDomain,
    context: str = "",
    audio_metadata: AudioMetadata | None = None,
    speaking_style: SpeakingStyle = "casual",
    emotional_tone: EmotionalTone = "neutral",
    technical_vocabulary: list[str] | None = None,
    collection_source: CollectionSource = "real_call",
    confidence: float = 0.0,
) -> VoiceLearningEvent:
    """Create and store a voice learning event.

    Use this for every useful owner-facing OpenClaw voice interaction (Rule 4).
    """
    from app.voice_agent.swara_config import get_active_profile

    profile = get_active_profile()
    audio_meta = audio_metadata or AudioMetadata(
        provider=profile.provider,
        voice_id=profile.voice_id,
        model=profile.model or "default",
        format="mp3",
    )

    event = VoiceLearningEvent(
        original_text=original_text,
        language=language,
        intended_meaning=intended_meaning,
        domain=domain,
        context=context,
        audio_metadata=audio_meta,
        speaking_style=speaking_style,
        emotional_tone=emotional_tone,
        technical_vocabulary=technical_vocabulary or [],
        collection_source=collection_source,
        confidence=confidence,
        model_version="swara_voice_profile_v1",
        llm_model=profile.provider,
    )

    get_voice_learning_store().store(event)
    return event


def record_owner_correction(
    event_id: str,
    incorrect_phrase: str,
    corrected_phrase: str,
    reason: str,
    affected_intent: str,
) -> bool:
    """Record an owner correction on an existing event (Rule 6: high-priority)."""
    store = get_voice_learning_store()
    for event in store._events:
        if event.event_id == event_id:
            correction = {
                "incorrect": incorrect_phrase,
                "corrected": corrected_phrase,
                "reason": reason,
                "affected_intent": affected_intent,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            event.owner_corrections.append(correction)
            # Re-store to update indexes
            store.store(event)
            logger.info(f"[voice_learning] Owner correction recorded for {event_id}")
            return True
    logger.warning(f"[voice_learning] Event {event_id} not found for correction")
    return False


def promote_candidate_to_golden(event_id: str) -> bool:
    """Promote a verified candidate to golden utterances (Rule 9: approve step)."""
    store = get_voice_learning_store()
    for event in store._events:
        if event.event_id == event_id and event.status == "candidate":
            if event.critical_regression:
                logger.warning(f"[voice_learning] Candidate {event_id} has critical_regression=True, skipping promotion")
                store.update_status(event_id, "rejected", "critical_regression_detected")
                return False
            if event.customer_data_leakage != "zero":
                logger.warning(f"[voice_learning] Candidate {event_id} has customer_data_leakage={event.customer_data_leakage}, skipping")
                store.update_status(event_id, "rejected", "customer_data_leakage")
                return False
            if event.policy_safety != "pass":
                logger.warning(f"[voice_learning] Candidate {event_id} has policy_safety={event.policy_safety}, skipping")
                store.update_status(event_id, "rejected", "policy_safety_fail")
                return False

            # Apply quality gates (Rule 10)
            gates = {
                "meaning_preservation": event.meaning_preservation >= 0.98,
                "intent_preservation": event.intent_preservation >= 0.98,
                "natural_hinglish": event.natural_hinglish >= 0.95,
                "pronunciation_quality": event.pronunciation_quality >= 0.95,
                "persona_consistency": event.persona_consistency >= 0.95,
            }
            failed_gates = [k for k, v in gates.items() if not v]
            if failed_gates:
                logger.warning(f"[voice_learning] Candidate {event_id} failed quality gates: {failed_gates}")
                store.update_status(event_id, "rejected", f"failed_gates: {failed_gates}")
                return False

            # Promote to golden
            store.update_status(event_id, "approved")
            from app.voice_agent.swara_golden_utterances import add_golden_example_from_event
            add_golden_example_from_event(event)
            logger.info(f"[voice_learning] Candidate {event_id} promoted to golden utterances")
            return True
    return False


__all__ = [
    "VoiceLearningEvent",
    "AudioMetadata",
    "VoiceLearningStore",
    "get_voice_learning_store",
    "record_voice_event",
    "record_owner_correction",
    "promote_candidate_to_golden",
    "LearningDomain",
    "EmotionalTone",
    "SpeakingStyle",
    "CollectionSource",
]