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
import time
from typing import Any

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
# COMPLETELY FREE providers only (no credit card, no paid credits required).
_GROQ_BASE = "https://api.groq.com/openai/v1"
_CEREBRAS_BASE = "https://api.cerebras.ai/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_XAI_BASE = "https://api.x.ai/v1"          # credits-based, kept for config compat only
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
_SAMBANOVA_BASE = "https://api.sambanova.ai/v1"   # 100% free, no card — cloud.sambanova.ai
_MISTRAL_BASE = "https://api.mistral.ai/v1"       # free tier La Plateforme — console.mistral.ai

# Models — all free tier.
_GROQ_STT_MODEL = "whisper-large-v3-turbo"
_CEREBRAS_LLM_MODEL = "gpt-oss-120b"       # free, fastest 120B
_GROQ_LLM_MODEL = "llama-3.1-8b-instant"  # free, 6000 RPM, 14k RPD
_GEMINI_LLM_MODEL = "gemini-2.0-flash-lite"  # free, 1500 RPD, 30 RPM — key already set
_SAMBANOVA_LLM_MODEL = "Meta-Llama-3.3-70B-Instruct"  # free, fast inference chip
_MISTRAL_LLM_MODEL = "mistral-small-latest"  # free tier (La Plateforme)
# OpenRouter multiple free models — fallback cascade
_OPENROUTER_LLM_MODEL = "deepseek/deepseek-chat:free"
_OPENROUTER_LLM_MODEL2 = "meta-llama/llama-3.1-8b-instruct:free"
_OPENROUTER_LLM_MODEL3 = "google/gemma-2-9b-it:free"
_XAI_LLM_MODEL = "grok-3-mini"  # credits-based — NOT in chain, kept for key compat

# Hard per-call latency cap. 8s: Cerebras normally 4-5s; 6s ne use beech me
# kaat ke weak generic fallback ("samajh gayi, aur bataiye") + repeats paida
# kiye (QA-tester proven). 8s = professional replies, no repeats; occasional
# spike phone par cached filler ("hmm/achha ji") se mask hota hai.
_CALL_TIMEOUT_S = 8.0

# Circuit-breaker: jab koi provider 429/rate-limit de, use skip karo (har call pe
# wasted retry-latency na ho). Auto-reopen. UPGRADE (patches 6e7af062/c01b6766):
# flat 60s kaafi nahi tha — daily-quota (Groq TPD) exhaust hone pe provider poore din
# har 60s pe retry karke fail hota raha (ok-rate 0.4-0.48 tank). Ab ESCALATING backoff:
# consecutive trips pe 60s → 2min → 4min ... cap 30min; "per day/TPD/daily" wording
# dikhe to seedha 30min (din-bhar ke liye repeated useless retries band). Success pe
# streak reset — provider wapas aate hi normal 60s sensitivity.
_LLM_COOLDOWN_UNTIL: dict[str, float] = {}
_LLM_COOLDOWN_S = 60.0
_LLM_COOLDOWN_MAX_S = 1800.0
_LLM_TRIP_STREAK: dict[str, int] = {}


def _provider_down(p: str) -> bool:
    return _LLM_COOLDOWN_UNTIL.get(p, 0.0) > time.time()


def _trip_cooldown(p: str, err: str) -> None:
    e = (err or "").lower()
    # 403 = no credits / permission denied — treat as long cooldown (permanent until restart)
    if "403" in e or "permission-denied" in e or "permission denied" in e:
        _LLM_TRIP_STREAK[p] = 99  # force max cooldown
        _LLM_COOLDOWN_UNTIL[p] = time.time() + _LLM_COOLDOWN_MAX_S
        return
    if not any(k in e for k in ("429", "rate", "quota", "queue", "too_many", "exhaust")):
        return
    streak = _LLM_TRIP_STREAK.get(p, 0) + 1
    _LLM_TRIP_STREAK[p] = streak
    cd = min(_LLM_COOLDOWN_S * (2 ** (streak - 1)), _LLM_COOLDOWN_MAX_S)
    if any(k in e for k in ("per day", "daily", "tpd", "tokens per day", "limit reached for model")):
        cd = _LLM_COOLDOWN_MAX_S
    _LLM_COOLDOWN_UNTIL[p] = time.time() + cd


def _reset_cooldown_streak(p: str) -> None:
    """Provider ne kaam kiya — backoff streak reset (60s base pe wapas)."""
    _LLM_TRIP_STREAK.pop(p, None)


# provider -> (settings attr, base_url)
_PROVIDER_CFG: dict[str, tuple[str, str]] = {
    "groq":       ("groq_api_key",      _GROQ_BASE),
    "cerebras":   ("cerebras_api_key",  _CEREBRAS_BASE),
    "openrouter": ("openrouter_api_key", _OPENROUTER_BASE),
    "xai":        ("xai_api_key",       _XAI_BASE),       # credits-based, chain me nahi
    "gemini":     ("gemini_api_key",    _GEMINI_BASE),
    "sambanova":  ("sambanova_api_key", _SAMBANOVA_BASE),  # free — cloud.sambanova.ai
    "mistral":    ("mistral_api_key",   _MISTRAL_BASE),    # free tier — console.mistral.ai
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


def _provider_flags() -> dict[str, bool]:
    """Live snapshot: kaunse free providers usable hain (SDK + key dono chahiye)."""
    return {p: (_OPENAI_OK and _has_key(p)) for p in _PROVIDER_CFG}


# Import-time flags (status/diagnostics ke liye). describe() live recompute karta.
PROVIDERS_AVAILABLE: dict[str, bool] = _provider_flags()


# --- lazy AsyncOpenAI client cache (per provider) --- #
_CLIENTS: dict[str, Any | None] = {}


def _client(provider: str) -> Any | None:
    """Lazy AsyncOpenAI client for a provider — None agar SDK missing ya key absent.
    Result cache hota hai (None bhi), taaki bar-bar build na ho."""
    if not _OPENAI_OK:
        return None
    if provider in _CLIENTS:
        return _CLIENTS[provider]
    attr, base = _PROVIDER_CFG.get(provider, ("", ""))
    api_key = _key(attr) if attr else ""
    client: Any | None = None
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
async def transcribe_audio(
    wav_bytes: bytes,
    language: str = "hi",
    filename: str = "audio.wav",
    mime: str = "audio/wav",
) -> tuple[str, str]:
    """Groq whisper-large-v3 se audio bytes transcribe karo.

    Default WAV (phone paths unchanged); web-call webm/ogg bhi bhej sakta hai
    (`filename`/`mime` se format batao — Groq extension se pehchanta hai).
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
                file=(filename or "audio.wav", wav_bytes, mime or "audio/wav"),
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
    messages: list[dict[str, str]],
    max_tokens: int = 90,
    temperature: float = 0.6,
) -> tuple[str, str]:
    """Free LLM chain par ek short reply lo.

    Chain: Cerebras gpt-oss-120b → Groq llama-3.1-8b-instant →
    OpenRouter deepseek/deepseek-chat:free. Har provider asyncio.wait_for 8s ke
    andar; pehla non-empty reply jeet jaata hai. Returns (reply, provider) ya
    ("","") agar SAB fail/absent. Kabhi raise nahi karta.
    """
    msgs: list[dict[str, str]] = []
    if system and system.strip():
        msgs.append({"role": "system", "content": system.strip()})
    for m in messages or []:
        role = m.get("role") or "user"
        if role not in ("system", "user", "assistant"):
            role = "user"
        content = str(m.get("content") or "").strip()
        if content:
            msgs.append({"role": role, "content": content})
    if not msgs:
        return "", ""

    # COMPLETELY FREE chain — no credit card, no paid credits.
    # Sign-up URLs: cloud.sambanova.ai | console.mistral.ai | openrouter.ai
    chain = [
        ("cerebras",   _CEREBRAS_LLM_MODEL),   # free, 120B, ~4-5s
        ("groq",       _GROQ_LLM_MODEL),        # free, 8B, ~1s, 6000 RPM
        ("gemini",     _GEMINI_LLM_MODEL),      # free, 1500 RPD — key set
        ("sambanova",  _SAMBANOVA_LLM_MODEL),   # free, 70B fast — SAMBANOVA_API_KEY
        ("mistral",    _MISTRAL_LLM_MODEL),     # free tier — MISTRAL_API_KEY
        ("openrouter", _OPENROUTER_LLM_MODEL),  # deepseek:free
        ("openrouter", _OPENROUTER_LLM_MODEL2), # llama-3.1-8b:free fallback
        ("openrouter", _OPENROUTER_LLM_MODEL3), # gemma-2-9b:free last resort
    ]
    for provider, model in chain:
        if _provider_down(provider):
            continue  # circuit-breaker: provider abhi cooldown me hai
        client = _client(provider)
        if client is None:
            continue
        _t0 = time.monotonic()
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
                _reset_cooldown_streak(provider)
                # LLM observability hook (ultra-light, never-raise)
                try:
                    from app.platform import llm_metrics

                    llm_metrics.record(provider, True, (time.monotonic() - _t0) * 1000)
                except Exception:
                    pass
                return text, provider
        except Exception as e:
            _trip_cooldown(provider, str(e))
            try:
                from app.platform import llm_metrics

                llm_metrics.record(provider, False, (time.monotonic() - _t0) * 1000, str(e))
            except Exception:
                pass
            logger.warning(f"[free_ai] {provider} chat failed: {e}")
            continue
    return "", ""


def describe() -> dict[str, Any]:
    """/status diagnostics — kaunse free providers configured hain + chains."""
    return {
        "openai_sdk": _OPENAI_OK,
        "providers": _provider_flags(),
        "stt_chain": [f"groq:{_GROQ_STT_MODEL}", "gemini-audio", "local:faster-whisper"],
        "llm_chain": [
            f"cerebras:{_CEREBRAS_LLM_MODEL}",
            f"groq:{_GROQ_LLM_MODEL}",
            f"gemini:{_GEMINI_LLM_MODEL}",
            f"sambanova:{_SAMBANOVA_LLM_MODEL}",
            f"mistral:{_MISTRAL_LLM_MODEL}",
            f"openrouter:{_OPENROUTER_LLM_MODEL}",
            f"openrouter:{_OPENROUTER_LLM_MODEL2}",
            f"openrouter:{_OPENROUTER_LLM_MODEL3}",
        ],
    }


__all__ = ["transcribe_audio", "chat", "describe", "PROVIDERS_AVAILABLE"]
