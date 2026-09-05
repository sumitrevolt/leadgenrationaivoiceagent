"""
Swara Voice Configuration — SINGLE SOURCE OF TRUTH for all voice identity.

Rule 1: One Swara Voice, Everywhere — exactly ONE canonical production identity.
Rule 20: Single voice configuration pattern — no duplicate hidden config scattered across services.

Environment variables (all optional, with safe defaults):
    SWARA_VOICE_PROVIDER      — "openai" | "gemini" | "edge" (default: "openai")
    SWARA_VOICE_ID            — Canonical voice ID (default: "alloy" for OpenAI, "Leda" for Gemini, "hi-IN-SwaraNeural" for EdgeTTS)
    OPENCLAW_OWNER_VOICE_ID   — Owner-facing voice (defaults to SWARA_VOICE_ID)
    SWARA_CUSTOMER_VOICE_ID   — Customer-facing voice (defaults to SWARA_VOICE_ID)
    SWARA_VOICE_MODEL         — TTS model (provider-specific)
    VOICE_LEARNING_ENABLED    — Enable voice learning pipeline (default: "1")
    VOICE_LEARNING_AUTO_COLLECT — Auto-collect learning events (default: "1")
    VOICE_LEARNING_AUTO_PROMOTE — Auto-promote candidates (default: "0" — MUST be 0 per Rule 9)
    VOICE_EVAL_ENABLED        — Enable evaluation framework (default: "1")
    PRONUNCIATION_MEMORY_ENABLED — Enable pronunciation dictionary (default: "1")
    HINGLISH_ADAPTATION_ENABLED — Enable Hinglish adaptation (default: "1")

Version: swara_voice_profile_v1
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


VoiceProvider = Literal["openai", "gemini", "edge"]


@dataclass(frozen=True)
class SwaraVoiceProfile:
    """Immutable canonical Swara voice profile — single source of truth."""
    provider: VoiceProvider
    voice_id: str
    model: str | None = None
    # Derived/aliased IDs (Rule 1 & 20)
    owner_voice_id: str = field(init=False)
    customer_voice_id: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "owner_voice_id", self.voice_id)
        object.__setattr__(self, "customer_voice_id", self.voice_id)


# =============================================================================
# DEFAULT VOICE PROFILES PER PROVIDER
# =============================================================================
# These are the canonical Swara voices per provider. The active profile is
# determined by SWARA_VOICE_PROVIDER env var.

_DEFAULT_PROFILES: dict[VoiceProvider, SwaraVoiceProfile] = {
    "openai": SwaraVoiceProfile(
        provider="openai",
        voice_id="alloy",  # premium feminine, warm, professional
        model="tts-1-hd",
    ),
    "gemini": SwaraVoiceProfile(
        provider="gemini",
        voice_id="Leda",  # warm female, closest to Swara persona
        model="gemini-2.5-flash-preview-tts",
    ),
    "edge": SwaraVoiceProfile(
        provider="edge",
        voice_id="hi-IN-SwaraNeural",  # Indian female, natural Hinglish
        model=None,
    ),
}


# =============================================================================
# CONFIGURATION RESOLUTION
# =============================================================================

def _resolve_provider() -> VoiceProvider:
    """Resolve active provider from env, defaulting to openai."""
    raw = (os.getenv("SWARA_VOICE_PROVIDER") or "openai").strip().lower()
    if raw in ("openai", "gemini", "edge"):
        return raw  # type: ignore[return-value]
    logger.warning(f"[swara_config] Unknown SWARA_VOICE_PROVIDER={raw!r}, defaulting to 'openai'")
    return "openai"


def _resolve_voice_id(provider: VoiceProvider) -> str:
    """Resolve voice ID from env, with provider-specific defaults."""
    env_id = (os.getenv("SWARA_VOICE_ID") or "").strip()
    if env_id:
        return env_id
    # Provider-specific default
    return _DEFAULT_PROFILES[provider].voice_id


def _resolve_model(provider: VoiceProvider, voice_id: str) -> str | None:
    """Resolve model from env, with provider-specific defaults."""
    env_model = (os.getenv("SWARA_VOICE_MODEL") or "").strip()
    if env_model:
        return env_model
    # Provider-specific default
    return _DEFAULT_PROFILES[provider].model


def _resolve_owner_voice_id(voice_id: str) -> str:
    """Resolve owner-facing voice ID (Rule 1 & 20: defaults to SWARA_VOICE_ID)."""
    return (os.getenv("OPENCLAW_OWNER_VOICE_ID") or voice_id).strip()


def _resolve_customer_voice_id(voice_id: str) -> str:
    """Resolve customer-facing voice ID (Rule 1 & 20: defaults to SWARA_VOICE_ID)."""
    return (os.getenv("SWARA_CUSTOMER_VOICE_ID") or voice_id).strip()


# =============================================================================
# SINGLETON: ACTIVE SWARA PROFILE
# =============================================================================

_active_profile: SwaraVoiceProfile | None = None


def get_active_profile() -> SwaraVoiceProfile:
    """Get the canonical active Swara voice profile (cached singleton)."""
    global _active_profile
    if _active_profile is not None:
        return _active_profile

    provider = _resolve_provider()
    voice_id = _resolve_voice_id(provider)
    model = _resolve_model(provider, voice_id)

    base_profile = _DEFAULT_PROFILES[provider]
    _active_profile = SwaraVoiceProfile(
        provider=provider,
        voice_id=voice_id,
        model=model,
    )
    # Override aliases if explicitly set
    _active_profile = SwaraVoiceProfile(
        provider=_active_profile.provider,
        voice_id=_active_profile.voice_id,
        model=_active_profile.model,
    )
    # Apply alias overrides
    object.__setattr__(_active_profile, "owner_voice_id", _resolve_owner_voice_id(_active_profile.voice_id))
    object.__setattr__(_active_profile, "customer_voice_id", _resolve_customer_voice_id(_active_profile.voice_id))

    logger.info(
        "[swara_config] Active profile: provider=%s voice_id=%s model=%s owner=%s customer=%s",
        _active_profile.provider,
        _active_profile.voice_id,
        _active_profile.model,
        _active_profile.owner_voice_id,
        _active_profile.customer_voice_id,
    )
    return _active_profile


def reset_active_profile() -> None:
    """Reset cached profile (for testing or env changes)."""
    global _active_profile
    _active_profile = None


# =============================================================================
# FEATURE FLAGS (Rules 9, 19)
# =============================================================================

def voice_learning_enabled() -> bool:
    """Rule 9: Voice learning pipeline enabled (collection allowed)."""
    return (os.getenv("VOICE_LEARNING_ENABLED", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


def voice_learning_auto_collect() -> bool:
    """Rule 9: Auto-collect learning events (allowed)."""
    return (os.getenv("VOICE_LEARNING_AUTO_COLLECT", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


def voice_learning_auto_promote() -> bool:
    """Rule 9: Auto-promote to production (FORBIDDEN — default 0, must stay 0)."""
    return (os.getenv("VOICE_LEARNING_AUTO_PROMOTE", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def voice_eval_enabled() -> bool:
    """Rule 10: Evaluation framework enabled."""
    return (os.getenv("VOICE_EVAL_ENABLED", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


def pronunciation_memory_enabled() -> bool:
    """Rule 7: Pronunciation dictionary enabled."""
    return (os.getenv("PRONUNCIATION_MEMORY_ENABLED", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


def hinglish_adaptation_enabled() -> bool:
    """Rule 5: English → Hinglish adaptation enabled."""
    return (os.getenv("HINGLISH_ADAPTATION_ENABLED", "1") or "1").strip().lower() not in ("0", "false", "no", "off")


# =============================================================================
# VERSION METADATA (Rule 19)
# =============================================================================

SWARA_VOICE_PROFILE_VERSION = "swara_voice_profile_v1"
SWARA_LANGUAGE_POLICY_VERSION = "swara_language_policy_v1"
SWARA_HINGLISH_LEXICON_VERSION = "swara_hinglish_lexicon_v1"
SWARA_PRONUNCIATION_DICT_VERSION = "swara_pronunciation_dict_v1"
SWARA_GOLDEN_UTTERANCES_VERSION = "swara_golden_utterances_v1"
VOICE_LEARNING_PIPELINE_VERSION = "voice_learning_pipeline_v1"

ALL_VERSIONS = {
    "voice_profile": SWARA_VOICE_PROFILE_VERSION,
    "language_policy": SWARA_LANGUAGE_POLICY_VERSION,
    "hinglish_lexicon": SWARA_HINGLISH_LEXICON_VERSION,
    "pronunciation_dict": SWARA_PRONUNCIATION_DICT_VERSION,
    "golden_utterances": SWARA_GOLDEN_UTTERANCES_VERSION,
    "learning_pipeline": VOICE_LEARNING_PIPELINE_VERSION,
}


def get_version_info() -> dict[str, str]:
    """Get all version metadata for observability (Rule 18)."""
    return {**ALL_VERSIONS, "active_profile": str(get_active_profile())}


# =============================================================================
# CONVENIENCE EXPORTS
# =============================================================================

__all__ = [
    "SwaraVoiceProfile",
    "VoiceProvider",
    "get_active_profile",
    "reset_active_profile",
    "voice_learning_enabled",
    "voice_learning_auto_collect",
    "voice_learning_auto_promote",
    "voice_eval_enabled",
    "pronunciation_memory_enabled",
    "hinglish_adaptation_enabled",
    "get_version_info",
    "SWARA_VOICE_PROFILE_VERSION",
    "SWARA_LANGUAGE_POLICY_VERSION",
    "SWARA_HINGLISH_LEXICON_VERSION",
    "SWARA_PRONUNCIATION_DICT_VERSION",
    "SWARA_GOLDEN_UTTERANCES_VERSION",
    "VOICE_LEARNING_PIPELINE_VERSION",
]