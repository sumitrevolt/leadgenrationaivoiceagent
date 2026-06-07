"""
free_ai.py — Free multi-provider AI layer (STT + LLM) for the phone voice agent.
================================================================================

WHY THIS EXISTS
---------------
Gemini free-tier quota (STT + LLM ek hi key par) din-bhar ke calls/tests me khatam
ho jaati hai → agent "samajhta/bolta nahi". Yeh module Gemini ke aage (STT) aur
peeche (LLM) FREE, OpenAI-compatible providers ka chain lagata hai taaki quota
khatam hone par bhi agent sunta + bolta rahe:

  STT chain (vobiz_stream._stt me): Groq whisper-large-v3 → Gemini audio → local faster-whisper
  LLM chain (yahan chat() me):      Cerebras llama-3.3-70b → Groq llama-3.3-70b → OpenRouter deepseek:free

Groq, Cerebras, OpenRouter — teeno OpenAI-compatible hain (sirf base_url + api_key
badalta hai, wahi `openai` SDK seedha chalta hai). Keys env se:
GROQ_API_KEY / CEREBRAS_API_KEY / OPENROUTER_API_KEY.

SAB OPTIONAL — koi key na ho to woh provider chup-chaap skip ho jaata hai. Yeh
module import-safe hai aur KABHI raise nahi karta: zero keys par bhi app boot karti
hai, transcribe_audio()/chat() bas ("","") return karte hain (caller agle link par
fall back kar leta hai).
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# --- openai SDK guard (requirements me hai, par import-safe rakho) --- #
try:
    from openai import AsyncOpenAI  # type: ignore

    _OPENAI_OK = True
except Exception:  # pragma: no cover - SDK missing
    AsyncOpenAI = None  # type: ignore
    _OPENAI_OK = False


# Provider endpoints — sab OpenAI-compatible /v1.
_GROQ_BASE = "https://api.groq.com/openai/v1"
_CEREBRAS_BASE = "https://api.cerebras.ai/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_XAI_BASE = "https://api.x.ai/v1"  # xAI Grok (NOTE: Groq se alag company!)

# Models.
# turbo = faster decode, same free tier + comparable Hindi quality → lower STT latency.
_GROQ_STT_MODEL = "whisper-large-v3-turbo"
_CEREBRAS_LLM_MODEL = "gpt-oss-120b"  # is account pe available (models API se confirmed): gpt-oss-120b + zai-glm-4.7
_GROQ_LLM_MODEL = "llama-3.3-70b-versatile"
_OPENROUTER_LLM_MODEL = "deepseek/deepseek-chat:free"
_XAI_LLM_MODEL = "grok-3-mini"  # fast/cheap Grok; credits-based (user ke paas keys)

# Hard per-call latency cap (phone par lambi wait = dead air). 6s: slow provider
# (free-tier load spike) par jaldi next provider pe failover ho — QA-tester ne
# kabhi-kabhi 11-12s turns pakde the (Cerebras slow → Groq). 6s tail kaatega.
_CALL_TIMEOUT_S = 6.0

# provider -> (settings attr, base_url)
_PROVIDER_CFG: Dict[str, Tuple[str, str]] = {
    "groq": ("groq_api_key", _GROQ_BASE),
    "cerebras": ("cerebras_api_key", _CEREBRAS_BASE),
    "openrouter": ("openrouter_api_key", _OPENROUTER_BASE),
    "xai": ("xai_api_key", _XAI_BASE),
}


def _key(attr: str) -> str:
    """settings.<attr> ka stripped value (gracefully empty agar settings tooti ho)."""
    try:
        from app.config import settings

        return (getattr(settings, attr, "") or "").strip()
    except Exception:
        return ""


def _has_key(provider: str) -> bool:
    attr = _PROVIDER_CFG.get(provider, ("", ""))[0]
    return bool(attr) and bool(_key(attr))


def _provider_flags() -> Dict[str, bool]:
    """Live snapshot: kaunse free providers usable hain (SDK + key dono chahiye)."""
    return {p: (_OPENAI_OK and _has_key(p)) for p in _PROVIDER_CFG}


# Import-time flags (status/diagnostics ke liye). describe() live recompute karta.
PROVIDERS_AVAILABLE: Dict[str, bool] = _provider_flags()


# --- lazy AsyncOpenAI client cache (per provider) --- #
_CLIENTS: Dict[str, Optional[Any]] = {}


def _client(provider: str) -> Optional[Any]:
    """Lazy AsyncOpenAI client for a provider — None agar SDK missing ya key absent.
    Result cache hota hai (None bhi), taaki bar-bar build na ho."""
    if not _OPENAI_OK:
        return None
    if provider in _CLIENTS:
        return _CLIENTS[provider]
    attr, base = _PROVIDER_CFG.get(provider, ("", ""))
    api_key = _key(attr) if attr else ""
    client: Optional[Any] = None
    if api_key and base:
        try:
            client = AsyncOpenAI(api_key=api_key, base_url=base, timeout=_CALL_TIMEOUT_S)
        except Exception as e:  # pragma: no cover - init failure
            logger.warning(f"[free_ai] {provider} client init failed: {e}")
            client = None
    _CLIENTS[provider] = client
    return client


# --------------------------------------------------------------------------- #
# STT — Groq whisper-large-v3 (free, OpenAI-compatible audio.transcriptions)
# --------------------------------------------------------------------------- #
async def transcribe_audio(wav_bytes: bytes, language: str = "hi") -> Tuple[str, str]:
    """Groq whisper-large-v3 se WAV bytes transcribe karo.

    Returns (text, "groq") on success, ya ("","") on any failure/absence.
    (Gemini audio-in + local faster-whisper caller ke agle links hain.)
    """
    if not wav_bytes:
        return "", ""
    client = _client("groq")
    if client is None:
        return "", ""
    try:
        resp = await asyncio.wait_for(
            client.audio.transcriptions.create(
                model=_GROQ_STT_MODEL,
                file=("audio.wav", wav_bytes, "audio/wav"),
                language=language or "hi",
            ),
            timeout=_CALL_TIMEOUT_S,
        )
        text = (getattr(resp, "text", "") or "").strip()
        if text:
            return text, "groq"
    except Exception as e:
        logger.warning(f"[free_ai] Groq STT failed: {e}")
    return "", ""


# --------------------------------------------------------------------------- #
# LLM — chain: Cerebras → Groq → OpenRouter (pehla non-empty reply jeet jaata)
# --------------------------------------------------------------------------- #
async def chat(
    system: str,
    messages: List[Dict[str, str]],
    max_tokens: int = 90,
    temperature: float = 0.6,
) -> Tuple[str, str]:
    """Free LLM chain par ek short reply lo.

    Chain: Cerebras llama-3.3-70b → Groq llama-3.3-70b-versatile →
    OpenRouter deepseek/deepseek-chat:free. Har provider asyncio.wait_for 8s ke
    andar; pehla non-empty reply jeet jaata hai. Returns (reply, provider) ya
    ("","") agar SAB fail/absent. Kabhi raise nahi karta.
    """
    msgs: List[Dict[str, str]] = []
    if system and system.strip():
        msgs.append({"role": "system", "content": system.strip()})
    for m in (messages or []):
        role = m.get("role") or "user"
        if role not in ("system", "user", "assistant"):
            role = "user"
        content = str(m.get("content") or "").strip()
        if content:
            msgs.append({"role": role, "content": content})
    if not msgs:
        return "", ""

    chain = [
        ("cerebras", _CEREBRAS_LLM_MODEL),
        ("groq", _GROQ_LLM_MODEL),
        ("xai", _XAI_LLM_MODEL),
        ("openrouter", _OPENROUTER_LLM_MODEL),
    ]
    for provider, model in chain:
        client = _client(provider)
        if client is None:
            continue
        try:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                ),
                timeout=_CALL_TIMEOUT_S,
            )
            text = ""
            try:
                text = (resp.choices[0].message.content or "").strip()
            except Exception:
                text = ""
            if text:
                return text, provider
        except Exception as e:
            logger.warning(f"[free_ai] {provider} chat failed: {e}")
            continue
    return "", ""


def describe() -> Dict[str, Any]:
    """/status diagnostics — kaunse free providers configured hain + chains."""
    return {
        "openai_sdk": _OPENAI_OK,
        "providers": _provider_flags(),
        "stt_chain": [f"groq:{_GROQ_STT_MODEL}", "gemini-audio", "local:faster-whisper"],
        "llm_chain": [
            f"cerebras:{_CEREBRAS_LLM_MODEL}",
            f"groq:{_GROQ_LLM_MODEL}",
            f"xai:{_XAI_LLM_MODEL}",
            f"openrouter:{_OPENROUTER_LLM_MODEL}",
        ],
    }


__all__ = ["transcribe_audio", "chat", "describe", "PROVIDERS_AVAILABLE"]
