"""
Swara Pronunciation Dictionary — project-specific pronunciation memory.

Rule 7: Maintain a curated pronunciation dictionary with:
    written_form, preferred_spoken_form, language, phonetic_hint, confidence, source, last_verified

Customer names must receive special care. Never confidently invent pronunciation when uncertain.

Version: swara_pronunciation_dict_v1
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# SCHEMA
# -----------------------------------------------------------------------------

@dataclass
class PronunciationEntry:
    """Single pronunciation dictionary entry."""
    written_form: str
    preferred_spoken_form: str
    language: str = "hinglish"  # "hinglish" | "hindi" | "english" | "marathi" | "other"
    phonetic_hint: str = ""  # IPA-ish or descriptive hint
    confidence: float = 0.9  # 0-1, how confident we are
    source: str = "manual"  # "manual" | "owner_correction" | "verified_call" | "external_dict"
    last_verified: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    version: str = "swara_pronunciation_dict_v1"
    tags: list[str] = field(default_factory=list)  # e.g., ["customer_name", "location", "product", "brand"]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# DEFAULT ENTRIES — PROJECT-SPECIFIC
# -----------------------------------------------------------------------------
# These are the canonical pronunciations for LeadGen AI domain terms.
# Add new entries here — they become the single source of truth.

DEFAULT_PRONUNCIATIONS: dict[str, PronunciationEntry] = {
    # Brand / product
    "LeadGen": PronunciationEntry(
        written_form="LeadGen",
        preferred_spoken_form="LeadGen",
        language="english",
        phonetic_hint="LEED-jen",
        confidence=1.0,
        source="brand_guideline",
        tags=["brand", "product"],
    ),
    "Swara": PronunciationEntry(
        written_form="Swara",
        preferred_spoken_form="Swara",
        language="hinglish",
        phonetic_hint="SWAH-rah (rhymes with 'sara')",
        confidence=1.0,
        source="brand_guideline",
        tags=["brand", "voice_agent"],
    ),
    "LeadGen AI": PronunciationEntry(
        written_form="LeadGen AI",
        preferred_spoken_form="LeadGen AI",
        language="english",
        phonetic_hint="LEED-jen AY-EYE",
        confidence=1.0,
        source="brand_guideline",
        tags=["brand"],
    ),

    # Locations (Indian)
    "Nagpur": PronunciationEntry(
        written_form="Nagpur",
        preferred_spoken_form="Nagpur",
        language="hinglish",
        phonetic_hint="NAHG-poor",
        confidence=0.95,
        source="verified_call",
        tags=["location", "maharashtra"],
    ),
    "Maharashtra": PronunciationEntry(
        written_form="Maharashtra",
        preferred_spoken_form="Maharashtra",
        language="hinglish",
        phonetic_hint="ma-ha-RASH-tra",
        confidence=0.95,
        source="verified_call",
        tags=["location", "state"],
    ),
    "Mumbai": PronunciationEntry(
        written_form="Mumbai",
        preferred_spoken_form="Mumbai",
        language="hinglish",
        phonetic_hint="moom-BYE",
        confidence=1.0,
        source="verified_call",
        tags=["location"],
    ),
    "Delhi": PronunciationEntry(
        written_form="Delhi",
        preferred_spoken_form="Dilli",
        language="hinglish",
        phonetic_hint="DIL-lee",
        confidence=0.9,
        source="verified_call",
        tags=["location"],
    ),
    "Bangalore": PronunciationEntry(
        written_form="Bangalore",
        preferred_spoken_form="Bengaluru",
        language="hinglish",
        phonetic_hint="BEN-guh-LOO-roo",
        confidence=0.9,
        source="verified_call",
        tags=["location"],
    ),
    "Pune": PronunciationEntry(
        written_form="Pune",
        preferred_spoken_form="Poona",
        language="hinglish",
        phonetic_hint="POO-nah",
        confidence=0.9,
        source="verified_call",
        tags=["location", "maharashtra"],
    ),

    # Tech / Business terms
    "WhatsApp": PronunciationEntry(
        written_form="WhatsApp",
        preferred_spoken_form="WhatsApp",
        language="english",
        phonetic_hint="WAHTS-app",
        confidence=1.0,
        source="common_usage",
        tags=["product", "tech"],
    ),
    "SaaS": PronunciationEntry(
        written_form="SaaS",
        preferred_spoken_form="Saas",
        language="english",
        phonetic_hint="SASS (rhymes with 'pass')",
        confidence=0.95,
        source="common_usage",
        tags=["tech", "business"],
    ),
    "CRM": PronunciationEntry(
        written_form="CRM",
        preferred_spoken_form="C-R-M",
        language="english",
        phonetic_hint="SEE-AR-EM",
        confidence=1.0,
        source="common_usage",
        tags=["tech", "business"],
    ),
    "API": PronunciationEntry(
        written_form="API",
        preferred_spoken_form="A-P-I",
        language="english",
        phonetic_hint="AY-PEE-EYE",
        confidence=1.0,
        source="common_usage",
        tags=["tech"],
    ),
    "AI": PronunciationEntry(
        written_form="AI",
        preferred_spoken_form="A-I",
        language="english",
        phonetic_hint="AY-EYE",
        confidence=1.0,
        source="common_usage",
        tags=["tech"],
    ),
    "LLM": PronunciationEntry(
        written_form="LLM",
        preferred_spoken_form="L-L-M",
        language="english",
        phonetic_hint="EL-EL-EM",
        confidence=1.0,
        source="common_usage",
        tags=["tech"],
    ),
    "RAG": PronunciationEntry(
        written_form="RAG",
        preferred_spoken_form="RAG",
        language="english",
        phonetic_hint="RAG (rhymes with 'bag')",
        confidence=0.9,
        source="common_usage",
        tags=["tech"],
    ),
    "STT": PronunciationEntry(
        written_form="STT",
        preferred_spoken_form="S-T-T",
        language="english",
        phonetic_hint="ESS-TEE-TEE",
        confidence=1.0,
        source="common_usage",
        tags=["tech", "voice"],
    ),
    "TTS": PronunciationEntry(
        written_form="TTS",
        preferred_spoken_form="T-T-S",
        language="english",
        phonetic_hint="TEE-TEE-ESS",
        confidence=1.0,
        source="common_usage",
        tags=["tech", "voice"],
    ),
    "IVR": PronunciationEntry(
        written_form="IVR",
        preferred_spoken_form="I-V-R",
        language="english",
        phonetic_hint="EYE-VEE-AR",
        confidence=1.0,
        source="common_usage",
        tags=["telephony"],
    ),
    "SIP": PronunciationEntry(
        written_form="SIP",
        preferred_spoken_form="SIP",
        language="english",
        phonetic_hint="SIP (like 'sip tea')",
        confidence=1.0,
        source="common_usage",
        tags=["telephony"],
    ),
    "VoIP": PronunciationEntry(
        written_form="VoIP",
        preferred_spoken_form="V-O-I-P",
        language="english",
        phonetic_hint="VEE-OH-EYE-PEE",
        confidence=0.9,
        source="common_usage",
        tags=["telephony"],
    ),

    # Indian business terms
    "GST": PronunciationEntry(
        written_form="GST",
        preferred_spoken_form="G-S-T",
        language="english",
        phonetic_hint="JEE-ESS-TEE",
        confidence=1.0,
        source="common_usage",
        tags=["business", "india"],
    ),
    "PAN": PronunciationEntry(
        written_form="PAN",
        preferred_spoken_form="PAN",
        language="english",
        phonetic_hint="PAN (like 'pan card')",
        confidence=1.0,
        source="common_usage",
        tags=["business", "india"],
    ),
    "UPI": PronunciationEntry(
        written_form="UPI",
        preferred_spoken_form="U-P-I",
        language="english",
        phonetic_hint="YOO-PEE-EYE",
        confidence=1.0,
        source="common_usage",
        tags=["payment", "india"],
    ),
    "DLT": PronunciationEntry(
        written_form="DLT",
        preferred_spoken_form="D-L-T",
        language="english",
        phonetic_hint="DEE-EL-TEE",
        confidence=1.0,
        source="common_usage",
        tags=["telecom", "india"],
    ),
    "TRAI": PronunciationEntry(
        written_form="TRAI",
        preferred_spoken_form="TRAI",
        language="english",
        phonetic_hint="TRY (rhymes with 'eye')",
        confidence=0.95,
        source="common_usage",
        tags=["telecom", "india"],
    ),

    # Companies / Brands (Indian)
    "Tata": PronunciationEntry(
        written_form="Tata",
        preferred_spoken_form="Tata",
        language="hinglish",
        phonetic_hint="TAH-tah",
        confidence=1.0,
        source="common_usage",
        tags=["brand", "india"],
    ),
    "Jio": PronunciationEntry(
        written_form="Jio",
        preferred_spoken_form="Jio",
        language="hinglish",
        phonetic_hint="JEE-oh",
        confidence=1.0,
        source="common_usage",
        tags=["brand", "telecom", "india"],
    ),
    "Smartflo": PronunciationEntry(
        written_form="Smartflo",
        preferred_spoken_form="Smartflo",
        language="english",
        phonetic_hint="SMART-floh",
        confidence=0.9,
        source="verified_call",
        tags=["brand", "partner"],
    ),

    # Common Hinglish words that need consistent pronunciation
    "haan": PronunciationEntry(
        written_form="haan",
        preferred_spoken_form="haan",
        language="hinglish",
        phonetic_hint="HAAN (nasal 'n')",
        confidence=0.95,
        source="common_usage",
        tags=["hinglish", "affirmation"],
    ),
    "nahi": PronunciationEntry(
        written_form="nahi",
        preferred_spoken_form="nahin",
        language="hinglish",
        phonetic_hint="na-HEEN",
        confidence=0.95,
        source="common_usage",
        tags=["hinglish", "negation"],
    ),
    "bilkul": PronunciationEntry(
        written_form="bilkul",
        preferred_spoken_form="bilkul",
        language="hinglish",
        phonetic_hint="bil-KUL",
        confidence=0.9,
        source="common_usage",
        tags=["hinglish", "affirmation"],
    ),
    "zaroor": PronunciationEntry(
        written_form="zaroor",
        preferred_spoken_form="zaroor",
        language="hinglish",
        phonetic_hint="za-ROOR",
        confidence=0.9,
        source="common_usage",
        tags=["hinglish", "affirmation"],
    ),
    "thik hai": PronunciationEntry(
        written_form="thik hai",
        preferred_spoken_form="thik hai",
        language="hinglish",
        phonetic_hint="THIK ha-EYE",
        confidence=0.9,
        source="common_usage",
        tags=["hinglish", "agreement"],
    ),
    "samjha": PronunciationEntry(
        written_form="samjha",
        preferred_spoken_form="samjha",
        language="hinglish",
        phonetic_hint="sam-JHA",
        confidence=0.9,
        source="common_usage",
        tags=["hinglish", "understanding"],
    ),
    "pata hai": PronunciationEntry(
        written_form="pata hai",
        preferred_spoken_form="pata hai",
        language="hinglish",
        phonetic_hint="pa-TA ha-EYE",
        confidence=0.9,
        source="common_usage",
        tags=["hinglish", "knowledge"],
    ),
}


# -----------------------------------------------------------------------------
# STORAGE
# -----------------------------------------------------------------------------

class PronunciationDictionary:
    """
    Thread-safe pronunciation dictionary with persistence.

    Features:
    - In-memory cache with JSONL persistence
    - Versioned entries (Rule 19)
    - Confidence scoring
    - Customer name special handling (never invent when uncertain)
    """

    def __init__(self) -> None:
        self._entries: dict[str, PronunciationEntry] = {}
        self._lock = threading.RLock()
        self._jsonl_path: str | None = None
        self._loaded = False

    def _init_jsonl(self) -> str | None:
        if self._jsonl_path is not None:
            return self._jsonl_path
        base = os.getenv("PRONUNCIATION_DATA_DIR", "data/pronunciation")
        try:
            os.makedirs(base, exist_ok=True)
            self._jsonl_path = os.path.join(base, "pronunciation_dict.jsonl")
        except Exception as e:
            logger.warning(f"[pronunciation] Cannot init JSONL path: {e}")
            self._jsonl_path = None
        return self._jsonl_path

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return

            # Load defaults first
            for key, entry in DEFAULT_PRONUNCIATIONS.items():
                self._entries[key.lower()] = entry

            # Load persisted overrides
            path = self._init_jsonl()
            if path and Path(path).exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                entry = PronunciationEntry(**data)
                                self._entries[entry.written_form.lower()] = entry
                            except Exception as e:
                                logger.debug(f"[pronunciation] Skipping malformed line: {e}")
                except Exception as e:
                    logger.warning(f"[pronunciation] Load failed: {e}")

            self._loaded = True
            logger.info(f"[pronunciation] Loaded {len(self._entries)} entries")

    def _persist(self, entry: PronunciationEntry) -> None:
        path = self._init_jsonl()
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[pronunciation] Persist failed: {e}")

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def get(self, written_form: str) -> PronunciationEntry | None:
        """Get pronunciation entry. Returns None if not found (never invents)."""
        self._load()
        with self._lock:
            return self._entries.get(written_form.lower())

    def get_spoken(self, written_form: str) -> str | None:
        """Get the preferred spoken form, or None if unknown."""
        entry = self.get(written_form)
        return entry.preferred_spoken_form if entry else None

    def set(
        self,
        written_form: str,
        preferred_spoken_form: str,
        language: str = "hinglish",
        phonetic_hint: str = "",
        confidence: float = 0.8,
        source: str = "manual",
        tags: list[str] | None = None,
    ) -> PronunciationEntry:
        """Add or update a pronunciation entry."""
        self._load()
        with self._lock:
            entry = PronunciationEntry(
                written_form=written_form,
                preferred_spoken_form=preferred_spoken_form,
                language=language,
                phonetic_hint=phonetic_hint,
                confidence=confidence,
                source=source,
                tags=tags or [],
            )
            self._entries[written_form.lower()] = entry
            self._persist(entry)
            logger.info(f"[pronunciation] Set: {written_form} -> {preferred_spoken_form} (confidence={confidence})")
            return entry

    def add_customer_name(self, name: str, pronunciation: str, confidence: float = 0.7) -> PronunciationEntry:
        """Add a customer name with special care (Rule 7).

        Customer names must receive special care. Never confidently invent
        pronunciation when uncertain — defaults to lower confidence.
        """
        return self.set(
            written_form=name,
            preferred_spoken_form=pronunciation,
            language="hinglish",
            confidence=confidence,
            source="customer_name",
            tags=["customer_name"],
        )

    def record_correction(self, written_form: str, corrected_form: str, source: str = "owner_correction") -> PronunciationEntry:
        """Record an owner correction (high confidence)."""
        entry = self.get(written_form)
        if entry:
            # Update existing
            entry.preferred_spoken_form = corrected_form
            entry.confidence = max(entry.confidence, 0.95)
            entry.source = source
            entry.last_verified = datetime.now(timezone.utc).isoformat()
            self._persist(entry)
            logger.info(f"[pronunciation] Owner correction: {written_form} -> {corrected_form}")
            return entry
        else:
            # New entry from correction
            return self.set(
                written_form=written_form,
                preferred_spoken_form=corrected_form,
                confidence=0.95,
                source=source,
            )

    def search(self, query: str, limit: int = 20) -> list[PronunciationEntry]:
        """Search entries by written form or tags."""
        self._load()
        query_lower = query.lower()
        with self._lock:
            results = [
                e for e in self._entries.values()
                if query_lower in e.written_form.lower() or
                query_lower in e.preferred_spoken_form.lower() or
                any(query_lower in tag.lower() for tag in e.tags)
            ]
        return results[:limit]

    def get_by_tag(self, tag: str) -> list[PronunciationEntry]:
        """Get all entries with a specific tag."""
        self._load()
        with self._lock:
            return [e for e in self._entries.values() if tag in e.tags]

    def get_customer_names(self) -> list[PronunciationEntry]:
        """Get all customer name entries."""
        return self.get_by_tag("customer_name")

    def stats(self) -> dict[str, Any]:
        """Get dictionary statistics."""
        self._load()
        with self._lock:
            by_language = {}
            by_source = {}
            by_tag = {}
            for e in self._entries.values():
                by_language[e.language] = by_language.get(e.language, 0) + 1
                by_source[e.source] = by_source.get(e.source, 0) + 1
                for tag in e.tags:
                    by_tag[tag] = by_tag.get(tag, 0) + 1
            return {
                "total_entries": len(self._entries),
                "by_language": by_language,
                "by_source": by_source,
                "by_tag": by_tag,
                "version": "swara_pronunciation_dict_v1",
            }


# -----------------------------------------------------------------------------
# SINGLETON
# -----------------------------------------------------------------------------

_dict: PronunciationDictionary | None = None


def get_pronunciation_dict() -> PronunciationDictionary:
    """Get the singleton pronunciation dictionary."""
    global _dict
    if _dict is None:
        _dict = PronunciationDictionary()
    return _dict


# -----------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# -----------------------------------------------------------------------------

def get_spoken_form(written_form: str, default: str | None = None) -> str:
    """Get spoken form, returning written_form if not found (safe fallback)."""
    entry = get_pronunciation_dict().get(written_form)
    if entry:
        return entry.preferred_spoken_form
    return default or written_form


def normalize_text_with_pronunciation(text: str) -> str:
    """Replace known terms in text with their preferred spoken forms.

    Used by TTS pipeline to ensure consistent pronunciation.
    """
    dict_ = get_pronunciation_dict()
    dict_._load()

    # Sort by length descending to match longer phrases first
    entries = sorted(dict_._entries.values(), key=lambda e: len(e.written_form), reverse=True)

    result = text
    for entry in entries:
        # Case-insensitive replacement, preserving case of surrounding text
        import re
        pattern = re.compile(re.escape(entry.written_form), re.IGNORECASE)
        result = pattern.sub(entry.preferred_spoken_form, result)

    return result


__all__ = [
    "PronunciationEntry",
    "PronunciationDictionary",
    "get_pronunciation_dict",
    "get_spoken_form",
    "normalize_text_with_pronunciation",
    "DEFAULT_PRONUNCIATIONS",
]