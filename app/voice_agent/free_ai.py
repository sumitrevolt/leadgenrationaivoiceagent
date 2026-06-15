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

# LLM observability (G1) — optional OTel/Langfuse trace per call. Hot path ko
# KABHI nahi todta agar module/deps absent ho (graceful no-op fallback).
try:
    from app.observability_llm import llm_span as _llm_span
except Exception:  # pragma: no cover
    from contextlib import contextmanager as _contextmanager

    @_contextmanager
    def _llm_span(*_a, **_k):
        class _NoopSpan:
            def record(self, *_a, **_k):
                pass

        yield _NoopSpan()

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
# OpenRouter free models — cascade (deepseek/deepseek-chat:free deprecated 2026-06 → 404)
_OPENROUTER_LLM_MODEL = "meta-llama/llama-3.1-8b-instruct:free"   # primary (llama 8B free)
_OPENROUTER_LLM_MODEL2 = "deepseek/deepseek-r1:free"              # deepseek R1 free
_OPENROUTER_LLM_MODEL3 = "google/gemma-2-9b-it:free"              # gemma fallback
_XAI_LLM_MODEL = "grok-3-mini"  # credits-based — NOT in chain, kept for key compat

# --------------------------------------------------------------------------- #
# SELF-HOSTED LLM (OWN STACK — kisi free/paid tier pe NIRBHAR nahi). Ollama
# OpenAI-compatible (/v1). OLLAMA_URL set hote hi provider ACTIVE — UNLIMITED,
# no quota, no 429, no per-call cost (sirf apna compute). Free providers exhaust
# (groq TPD, gemini quota) hone par bhi yeh KABHI down nahi — true independence.
# CPU inference slow hai isliye apna lamba timeout. Default model Hinglish-strong.
# OLLAMA_PRIMARY=1 -> chain me sabse pehle (pure self-reliance); warna reliable
# fallback (fast cloud pehle, own-LLM guaranteed catch).
# --------------------------------------------------------------------------- #
def _ollama_url() -> str:
    import os as _os
    return (_os.environ.get("OLLAMA_URL") or "").strip()


def _ollama_model() -> str:
    import os as _os
    return (_os.environ.get("OLLAMA_MODEL") or "qwen2.5:3b-instruct").strip()


def _ollama_timeout() -> float:
    import os as _os
    try:
        return float(_os.environ.get("OLLAMA_TIMEOUT_S", "30") or 30)
    except Exception:
        return 30.0


def _ollama_primary() -> bool:
    import os as _os
    return bool(_ollama_url()) and _os.environ.get("OLLAMA_PRIMARY", "0").strip().lower() in ("1", "true", "yes")

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
    # 403 = no credits/permission · 404 = model not found/deprecated (OpenRouter :free
    # variants rotate → 404). DONO ko LONG cooldown (max, ~restart tak) do — warna dead
    # endpoint har chat() fallback pe dobara retry hota hai (LIVE: openrouter :free 404
    # → 52% LLM fallback waste). Provider-agnostic dead-model sideline.
    if any(k in e for k in (
        "403", "permission-denied", "permission denied",
        "404", "not found", "no endpoints", "model_not_found", "no allowed providers",
    )):
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


# OpenRouter multi-key rotation — 4 accounts, har ek alag circuit-breaker
# Keys: OPENROUTER_API_KEY (primary) + OPENROUTER_API_KEY_2/3/4 (rotation)
def _or_keys() -> list[str]:
    """Return all non-empty OpenRouter keys in order."""
    try:
        from app.config import settings
        keys = []
        for attr in ("openrouter_api_key", "openrouter_api_key_2", "openrouter_api_key_3", "openrouter_api_key_4"):
            v = (getattr(settings, attr, "") or "").strip()
            if v:
                keys.append(v)
        return keys
    except Exception:
        return []


# provider -> (settings attr, base_url)
_PROVIDER_CFG: dict[str, tuple[str, str]] = {
    "groq":         ("groq_api_key",          _GROQ_BASE),
    "cerebras":     ("cerebras_api_key",       _CEREBRAS_BASE),
    "openrouter":   ("openrouter_api_key",     _OPENROUTER_BASE),
    "openrouter_2": ("openrouter_api_key_2",   _OPENROUTER_BASE),
    "openrouter_3": ("openrouter_api_key_3",   _OPENROUTER_BASE),
    "openrouter_4": ("openrouter_api_key_4",   _OPENROUTER_BASE),
    "xai":          ("xai_api_key",            _XAI_BASE),  # credits-based, chain me nahi
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
    if provider == "ollama":
        return bool(_ollama_url())  # self-hosted: URL = "key"
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
    if provider == "ollama":
        url = _ollama_url()
        client = None
        if url:
            try:
                # Ollama api_key ignore karta — dummy. CPU inference slow -> lamba timeout.
                client = AsyncOpenAI(api_key="ollama", base_url=url, timeout=_ollama_timeout())
            except Exception as e:  # pragma: no cover
                logger.warning(f"[free_ai] ollama client init failed: {e}")
                client = None
        _CLIENTS["ollama"] = client
        return client
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
# --- LLM response cache (R11#4) — gated LLM_CACHE=1 (default OFF = zero change).
# Identical (system+messages+params) -> reuse reply, API calls bachao. In-memory
# TTL cache, never-raise. Default off taaki dynamic/varied replies pe asar na ho.
import hashlib as _hashlib
import os as _os

_LLM_CACHE: dict[str, tuple[float, tuple[str, str]]] = {}
_LLM_CACHE_TTL_S = float(_os.environ.get("LLM_CACHE_TTL_S", "300") or 300)
_LLM_CACHE_MAX = 500


def _llm_cache_on() -> bool:
    return _os.environ.get("LLM_CACHE", "0").strip().lower() in ("1", "true", "yes")


def _llm_cache_key(system: Any, msgs: Any, max_tokens: Any, temperature: Any) -> str:
    try:
        raw = repr((system, msgs, max_tokens, round(float(temperature), 2)))
        return _hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()
    except Exception:
        return ""


def _llm_cache_get(key: str):
    try:
        if not key:
            return None
        v = _LLM_CACHE.get(key)
        if not v:
            return None
        ts, val = v
        if time.time() - ts > _LLM_CACHE_TTL_S:
            _LLM_CACHE.pop(key, None)
            return None
        return val
    except Exception:
        return None


def _llm_cache_put(key: str, val: tuple[str, str]) -> None:
    try:
        if not key:
            return
        if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
            _LLM_CACHE.clear()  # simple bound
        _LLM_CACHE[key] = (time.time(), val)
    except Exception:
        pass


async def chat(
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 90,
    temperature: float = 0.6,
    scope: str = "global",
) -> tuple[str, str]:
    """Free LLM chain par ek short reply lo.

    Chain: Cerebras gpt-oss-120b → Groq llama-3.1-8b-instant →
    OpenRouter deepseek/deepseek-chat:free. Har provider asyncio.wait_for 8s ke
    andar; pehla non-empty reply jeet jaata hai. Returns (reply, provider) ya
    ("","") agar SAB fail/absent. Kabhi raise nahi karta.

    scope: per-tenant/per-loop budget attribution (e.g. client_id / "self_improve").
           budget_guard (LLM_BUDGET_GUARD flag) is scope ke daily cap enforce karta;
           flag OFF (default) = zero overhead, koi behaviour change nahi.
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

    # Response cache (gated LLM_CACHE) — identical prompt -> reuse, API call bachao.
    # Budget guard ke PEHLE: cached reply ka zero real LLM cost hai, isliye over-budget
    # hone par bhi cache-hit serve hona chahiye (review finding #5).
    _ck = _llm_cache_key(system, msgs, max_tokens, temperature) if _llm_cache_on() else ""
    if _ck:
        _hit = _llm_cache_get(_ck)
        if _hit is not None:
            return _hit

    # Per-scope LLM budget guard (gated LLM_BUDGET_GUARD ya emergency LLM_BUDGET_HARD_KILL).
    # Over-budget / hard-kill = graceful ("","") jaise saare providers exhaust. Fail-open.
    # active() = guard ON YA hard-kill ON — taaki sirf hard-kill set karne pe bhi block ho.
    try:
        from app.llm import budget_guard

        if budget_guard.active():
            _ok, _bi = await budget_guard.allow(scope)
            if not _ok:
                logger.warning("[free_ai] budget guard blocked scope=%s reason=%s", scope, _bi.get("reason"))
                return "", ""
    except Exception:
        pass  # guard error = proceed normally (fail-open)

    # COMPLETELY FREE chain — no credit card, no paid credits.
    # OpenRouter 4 keys = 4x rate-limit headroom (each alag circuit-breaker)
    # ORDER = LIVE measured ok-rate (data/llm_calls.jsonl), NOT theory.
    # 2026-06-13 audit: mistral 99% · groq 96% · cerebras 9% (429 queue) ·
    # gemini/sambanova/openrouter ~0% (quota/deprecated). Pehle proven
    # performers try karo taaki har call me 2-5 dead attempts waste na hon
    # (aggregate ok 50% -> ~97%, latency bhi girti). Saare providers retain
    # (fallback headroom) — sirf order badla. Naye keys aayein to wapas tune karo.
    # SELF-HOSTED own LLM (OLLAMA_URL set hote hi active) — UNLIMITED, no quota, kisi
    # tier pe nirbhar nahi. OLLAMA_PRIMARY=1 -> sabse pehle (pure self-reliance); warna
    # proven cloud (mistral/groq/cerebras) ke BAAD + flaky cloud se PEHLE = fast jab
    # cloud up, par cloud exhaust hote hi OWN LLM guaranteed answer (kabhi fully down nahi).
    # OLLAMA_URL unset = _client("ollama") None -> instantly skip (zero change).
    _ollama_entry = ("ollama", _ollama_model())
    chain: list[tuple[str, str]] = []
    if _ollama_primary():
        chain.append(_ollama_entry)
    chain += [
        ("mistral",      _MISTRAL_LLM_MODEL),      # LIVE 99% ok — primary workhorse
        ("groq",         _GROQ_LLM_MODEL),         # LIVE 96% ok, ~1s, 6000 RPM
        ("cerebras",     _CEREBRAS_LLM_MODEL),     # 120B free but 429-prone; circuit-breaker handles
    ]
    if not _ollama_primary():
        chain.append(_ollama_entry)               # own LLM: reliable floor before flaky cloud
    chain += [
        ("gemini",       _GEMINI_LLM_MODEL),       # free, 1500 RPD
        ("sambanova",    _SAMBANOVA_LLM_MODEL),    # free, 70B fast
        ("openrouter",   _OPENROUTER_LLM_MODEL),   # key1 deepseek:free
        ("openrouter_2", _OPENROUTER_LLM_MODEL),   # key2 deepseek:free
        ("openrouter_3", _OPENROUTER_LLM_MODEL),   # key3 deepseek:free
        ("openrouter_4", _OPENROUTER_LLM_MODEL),   # key4 deepseek:free
        ("openrouter",   _OPENROUTER_LLM_MODEL2),  # llama:free
        ("openrouter_2", _OPENROUTER_LLM_MODEL2),  # llama:free key2
        ("openrouter",   _OPENROUTER_LLM_MODEL3),  # gemma:free
    ]
    for provider, model in chain:
        if _provider_down(provider):
            continue  # circuit-breaker: provider abhi cooldown me hai
        client = _client(provider)
        if client is None:
            continue
        _t0 = time.monotonic()
        try:
            with _llm_span("chat", model=model, provider=provider) as _obs:
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
                try:
                    _u = getattr(resp, "usage", None)
                    _obs.record(
                        prompt_tokens=getattr(_u, "prompt_tokens", None),
                        completion_tokens=getattr(_u, "completion_tokens", None),
                        latency_ms=(time.monotonic() - _t0) * 1000.0,
                        output_preview=text,
                        ok=bool(text),
                    )
                except Exception:
                    pass
            if text:
                _reset_cooldown_streak(provider)
                # LLM observability hook (ultra-light, never-raise)
                try:
                    from app.platform import llm_metrics

                    llm_metrics.record(provider, True, (time.monotonic() - _t0) * 1000)
                except Exception:
                    pass
                # Budget guard: per-scope usage record (best-effort, never-raise).
                try:
                    from app.llm import budget_guard

                    if budget_guard.is_enabled():
                        _bu = getattr(resp, "usage", None)
                        await budget_guard.record(
                            scope,
                            calls=1,
                            prompt_tokens=getattr(_bu, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(_bu, "completion_tokens", 0) or 0,
                        )
                except Exception:
                    pass
                if _ck:
                    _llm_cache_put(_ck, (text, provider))
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
