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
  LLM chain (yahan chat() me):      Groq gpt-oss-20b → Cerebras gpt-oss-120b → Mistral/OpenRouter fallbacks

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
import os
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

# --- Vertex AI bearer token cache (Google Cloud subscription support) --- #
# GOOGLE_CLOUD_PROJECT_ID + GOOGLE_CLOUD_LOCATION set hone par Gemini Vertex AI
# endpoint use hota hai (subscription plan, no per-key quota). Token 55-min cache;
# google-auth ADC ya GOOGLE_APPLICATION_CREDENTIALS JSON dono support.
import os as _os

_VERTEX_TOKEN_CACHE: dict = {"token": "", "exp": 0.0}


def _vertex_project() -> str:
    return (
        _os.environ.get("GOOGLE_CLOUD_PROJECT_ID") or _os.environ.get("GOOGLE_CLOUD_PROJECT") or ""
    ).strip()


def _vertex_location() -> str:
    return (_os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1").strip()


def _vertex_base_url() -> str:
    loc = _vertex_location()
    proj = _vertex_project()
    if not proj:
        return ""
    return f"https://{loc}-aiplatform.googleapis.com/v1beta1/projects/{proj}/locations/{loc}/endpoints/openapi/"


def _vertex_available() -> bool:
    """True jab Google Cloud project set ho (subscription plan route)."""
    return bool(_vertex_project())


async def _vertex_bearer_token() -> str:
    """Google Cloud access token lo (ADC ya service-account JSON). 55-min cache.
    Fail-soft: "" on any error (caller falls through to next provider)."""
    if _VERTEX_TOKEN_CACHE["token"] and time.time() < _VERTEX_TOKEN_CACHE["exp"] - 60:
        return _VERTEX_TOKEN_CACHE["token"]
    try:
        import google.auth  # type: ignore
        import google.auth.transport.requests  # type: ignore

        creds, _ = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"]),
        )
        req = google.auth.transport.requests.Request()
        await asyncio.get_event_loop().run_in_executor(None, creds.refresh, req)
        token: str = creds.token or ""
        if token:
            _VERTEX_TOKEN_CACHE["token"] = token
            _VERTEX_TOKEN_CACHE["exp"] = time.time() + 3300  # 55 min
        return token
    except Exception as e:
        logger.warning(f"[free_ai] Vertex AI token refresh failed: {e}")
        return ""


# Provider endpoints — sab OpenAI-compatible /v1.
# COMPLETELY FREE providers only (no credit card, no paid credits required).
_GROQ_BASE = "https://api.groq.com/openai/v1"
_CEREBRAS_BASE = "https://api.cerebras.ai/v1"
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"
_XAI_BASE = "https://api.x.ai/v1"  # credits-based, kept for config compat only
_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
_SAMBANOVA_BASE = "https://api.sambanova.ai/v1"  # 100% free, no card — cloud.sambanova.ai
_MISTRAL_BASE = "https://api.mistral.ai/v1"  # free tier La Plateforme — console.mistral.ai
# NVIDIA NIM — OpenAI-compatible (/v1). FREE tier = 40 RPM (upgradable ~200) + METERED
# inference credits (~1k-5k lifetime, NOT free-unlimited like Groq/Cerebras). Deep-tail
# fallback only — fires when proven primaries are all circuit-broken; conserves credits.
_NVIDIA_BASE = "https://integrate.api.nvidia.com/v1"  # build.nvidia.com

# Models — all free tier.
# STT accuracy-first for Hinglish: web test-calls showed `-turbo` garbling short
# code-switched utterances ("I'm interested" -> "वो इंट तर सेलू"), which broke the
# brain's question-detection. `whisper-large-v3` (non-turbo) is more accurate on
# Hindi/Hinglish; set GROQ_STT_MODEL=whisper-large-v3-turbo to trade accuracy for speed.
_GROQ_STT_MODEL = _os.environ.get("GROQ_STT_MODEL", "").strip() or "whisper-large-v3"
_CEREBRAS_LLM_MODEL = "gpt-oss-120b"  # free, fastest 120B
# Groq deprecation (console.groq.com/docs/deprecations, research 2026-08-01):
# llama-3.1-8b-instant + llama-3.3-70b-versatile decommission 2026-08-16.
# Official replacements: openai/gpt-oss-20b (8B) and openai/gpt-oss-120b (70B).
# Env override keeps emergency pin until shutdown day if needed.
_GROQ_LLM_MODEL = _os.environ.get("GROQ_LLM_MODEL", "").strip() or "openai/gpt-oss-20b"
_GEMINI_LLM_MODEL = (
    "gemini-2.5-flash"  # paid tier — key set, 2.5-flash works (2.0-flash-lite free_tier=0)
)
_SAMBANOVA_LLM_MODEL = "Meta-Llama-3.3-70B-Instruct"  # free, fast inference chip
_MISTRAL_LLM_MODEL = "mistral-small-latest"  # free tier (La Plateforme)
_NVIDIA_LLM_MODEL = "meta/llama-3.3-70b-instruct"  # NVIDIA NIM free — quality fallback (env override: NVIDIA_LLM_MODEL)
# 2026 EXTRA low-priority free models — sirf tab hit hote hain jab proven primaries
# (mistral/groq-head/cerebras) exhaust ho jaayein. Dead ids REMOVED (research 2026-08-01):
# qwen/qwen3-32b shut 2026-07-17; moonshotai/kimi-k2-instruct shut 2025-10-10.
_GROQ_QWEN3_MODEL = (
    _os.environ.get("GROQ_QWEN3_MODEL", "").strip() or "qwen/qwen3.6-27b"
)  # Groq recommended multilingual / strict-adjacent replacement
_GROQ_LLAMA70B_MODEL = (
    _os.environ.get("GROQ_LLAMA70B_MODEL", "").strip() or "openai/gpt-oss-120b"
)  # name kept for callers; id is gpt-oss-120b (not Llama)
# OpenRouter free models — cascade (deepseek/deepseek-chat:free deprecated 2026-06 → 404;
# 2026-07-05: llama-3.1-8b-instruct:free / deepseek-r1:free / gemma-2-9b-it:free ALL
# deprecated too → 404 on every openrouter_1..4 account, live-verified via
# openrouter.ai/api/v1/models $0-pricing listing. Swapped to currently-live free ids.)
_OPENROUTER_LLM_MODEL = "meta-llama/llama-3.3-70b-instruct:free"  # primary (llama 70B free)
_OPENROUTER_LLM_MODEL2 = "openai/gpt-oss-20b:free"  # gpt-oss 20B free
_OPENROUTER_LLM_MODEL3 = "google/gemma-4-31b-it:free"  # gemma-4 fallback (gemma-2 line retired)
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

    return bool(_ollama_url()) and _os.environ.get("OLLAMA_PRIMARY", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


# Hard per-call latency cap. 8s: Cerebras normally 4-5s; 6s ne use beech me
# kaat ke weak generic fallback ("samajh gayi, aur bataiye") + repeats paida
# kiye (QA-tester proven). 8s = professional replies, no repeats; occasional
# spike phone par cached filler ("hmm/achha ji") se mask hota hai.
_CALL_TIMEOUT_S = 8.0


# STREAMING token-loop deadlines (chat_stream). The OLD code wrapped only stream
# CREATION in a timeout; the `async for chunk in stream` token loop was UNBOUNDED,
# so a free provider that stalls mid-stream (TCP open, no more bytes — common under
# throttle) hung the generator FOREVER. On the live phone path that froze the call's
# `_thinking` flag => agent went permanently deaf after ~1 turn (root cause, 2026-06-22).
# Now every token wait is bounded: a generous FIRST-token deadline (the thinking
# filler masks it), a tight INTER-token idle deadline (a stalled stream trips fast),
# and an overall WALL cap. All env-overridable; floats so a bad value can't crash.
def _stream_num(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "") or default)
    except Exception:
        return default


_STREAM_FIRST_TOKEN_S = _stream_num("LLM_STREAM_FIRST_TOKEN_S", 5.0)  # wait for the 1st delta
_STREAM_IDLE_S = _stream_num("LLM_STREAM_IDLE_S", 3.0)  # max gap between deltas once flowing
_STREAM_TOTAL_S = _stream_num("LLM_STREAM_TOTAL_S", 12.0)  # overall wall budget per provider

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


def _err_str(e: BaseException | str) -> str:
    """str(exception) ko never-empty banao (dashboard/breaker dono ke liye).

    httpx/openai-sdk kabhi bare ConnectTimeout/ConnectError raise karte jinka
    str() khaali hota hai ("") — isse llm_metrics dashboard pe blank error
    dikhta (2026-07-05 live: nvidia 0% ok, blank last_error) AND _trip_cooldown
    ka koi keyword-branch match nahi karta (neither 429 na 403/404) => provider
    KABHI cooldown nahi hota, har single chat() call pe dobara retry hota rehta
    (silent latency tax). Fallback = exception class name, taaki hamesha kuch
    meaningful record ho."""
    if isinstance(e, str):
        s = e.strip()
        return s
    s = str(e).strip()
    return s if s else type(e).__name__


def _trip_cooldown(p: str, err: str) -> None:
    e = (err or "").lower()
    # 403 = no credits/permission · 404 = model not found/deprecated (OpenRouter :free
    # variants rotate → 404) · 402/out-of-credits = metered-credit exhaustion (NVIDIA NIM
    # free tier ~5k lifetime credits — once spent, returns persistent error, NOT a
    # transient 429). DONO ko LONG cooldown (max, ~restart tak) do — warna dead endpoint
    # har chat() fallback pe dobara retry hota hai (LIVE: openrouter :free 404 → 52% LLM
    # fallback waste). Provider-agnostic dead-model/dead-credit sideline.
    if any(
        k in e
        for k in (
            "403",
            "permission-denied",
            "permission denied",
            "404",
            "not found",
            "no endpoints",
            "model_not_found",
            "no allowed providers",
            "402",
            "payment required",
            "out of credits",
            "insufficient_quota",
            "insufficient credit",
        )
    ):
        _LLM_TRIP_STREAK[p] = 99  # force max cooldown
        _LLM_COOLDOWN_UNTIL[p] = time.time() + _LLM_COOLDOWN_MAX_S
        return
    is_rate_limit = any(k in e for k in ("429", "rate", "quota", "queue", "too_many", "exhaust"))
    # CATCH-ALL (added 2026-07-05): connection errors ("Connection error.", DNS/refused,
    # self-hosted Ollama down), timeouts, and blank/unrecognized exception strings (see
    # _err_str) matched NEITHER branch above → this function returned silently, so a
    # genuinely-broken provider (ollama connection-error, nvidia blank-error) got ZERO
    # cooldown and was retried on every single chat() call forever (live: ollama 26% ok,
    # nvidia 0% ok, both with no backoff). Any non-empty error now trips at least the
    # short escalating cooldown so broken providers get sidelined like the others.
    if not e:
        return
    streak = _LLM_TRIP_STREAK.get(p, 0) + 1
    _LLM_TRIP_STREAK[p] = streak
    cd = min(_LLM_COOLDOWN_S * (2 ** (streak - 1)), _LLM_COOLDOWN_MAX_S)
    if is_rate_limit and any(
        k in e for k in ("per day", "daily", "tpd", "tokens per day", "limit reached for model")
    ):
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
        for attr in (
            "openrouter_api_key",
            "openrouter_api_key_2",
            "openrouter_api_key_3",
            "openrouter_api_key_4",
        ):
            v = (getattr(settings, attr, "") or "").strip()
            if v:
                keys.append(v)
        return keys
    except Exception:
        return []


# provider -> (settings attr, base_url)
_PROVIDER_CFG: dict[str, tuple[str, str]] = {
    "groq": ("groq_api_key", _GROQ_BASE),
    "cerebras": ("cerebras_api_key", _CEREBRAS_BASE),
    "openrouter": ("openrouter_api_key", _OPENROUTER_BASE),
    "openrouter_2": ("openrouter_api_key_2", _OPENROUTER_BASE),
    "openrouter_3": ("openrouter_api_key_3", _OPENROUTER_BASE),
    "openrouter_4": ("openrouter_api_key_4", _OPENROUTER_BASE),
    "xai": ("xai_api_key", _XAI_BASE),  # credits-based, chain me nahi
    "gemini": ("gemini_api_key", _GEMINI_BASE),
    "sambanova": ("sambanova_api_key", _SAMBANOVA_BASE),  # free — cloud.sambanova.ai
    "mistral": ("mistral_api_key", _MISTRAL_BASE),  # free tier — console.mistral.ai
    "nvidia": (
        "nvidia_api_key",
        _NVIDIA_BASE,
    ),  # NVIDIA NIM free-tier fallback — integrate.api.nvidia.com
}


def _key(attr: str) -> str:
    """settings.<attr> ka stripped value (gracefully empty agar settings tooti ho).

    CRED_POOLS=1 pe multi-key round-robin (cred_pool) — load <attr>_2.._5 env keys
    par spread hota (higher aggregate free rate-limit). Default OFF = base value
    unchanged. Never-raise (pool error → base key).
    """
    try:
        from app.config import settings

        base = (getattr(settings, attr, "") or "").strip()
    except Exception:
        return ""
    try:
        from app.agents import cred_pool

        if base and cred_pool.enabled():
            return cred_pool.rotate(attr, base) or base
    except Exception:
        pass
    return base


def _has_key(provider: str) -> bool:
    if provider == "ollama":
        return bool(_ollama_url())  # self-hosted: URL = "key"
    if provider == "gemini_vertex":
        return _vertex_available()  # Cloud project = "key"
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
    if provider == "gemini_vertex":
        # Dynamic token — cache nahi karte (token expire hota hai).
        # Caller `chat_provider` / `_chat_one` is token ko fresh call pe inject karta.
        # Yahan None return karo; special path `_vertex_chat_one` se handle hoga.
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
    prompt: str = "",
) -> tuple[str, str]:
    """Groq whisper-large-v3 se audio bytes transcribe karo.

    Default WAV (phone paths unchanged); web-call webm/ogg bhi bhej sakta hai
    (`filename`/`mime` se format batao — Groq extension se pehchanta hai).
    `prompt` (D-11, optional): niche/brand bias string — Whisper isse domain
    entities + Hinglish register ki taraf bias hota hai (default "" = unchanged).
    Returns (text, "groq") on success, ya ("","") on any failure/absence.
    (Gemini audio-in + local faster-whisper caller ke agle links hain.)
    """
    if not wav_bytes:
        return "", ""
    client = _client("groq")
    if client is None:
        return "", ""
    try:
        _kw = {"prompt": prompt} if (prompt or "").strip() else {}
        resp = await asyncio.wait_for(
            client.audio.transcriptions.create(
                model=_GROQ_STT_MODEL,
                file=(filename or "audio.wav", wav_bytes, mime or "audio/wav"),
                language=language or "hi",
                **_kw,
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


def _llm_cache_on(prof: str = "") -> bool:
    """W1.10: bulk/content profile DEFAULT-ON (identical content/blog/SEO prompts cache
    → duplicate free-provider API calls + 429 bacho); realtime/voice OFF (dynamic replies
    pe asar na ho). Global `LLM_CACHE` env override: =1 force-on (saare profiles), =0
    force-off (sab). Unset → profile-based default."""
    env = _os.environ.get("LLM_CACHE", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    return prof == "bulk"


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


def _llm_cache_evict() -> None:
    """W1.11: bound pe poora `.clear()` (saara cache nuke, hit-rate→0) ki jagah
    TTL+LRU-ish — pehle expired entries drop; phir bhi full ho to oldest-by-timestamp
    ~20% nikalo. Hot entries survive. Never-raise (caller guarded bhi hai)."""
    now = time.time()
    for k in [k for k, (ts, _) in list(_LLM_CACHE.items()) if now - ts > _LLM_CACHE_TTL_S]:
        _LLM_CACHE.pop(k, None)
    if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
        n_evict = max(1, _LLM_CACHE_MAX // 5)
        for k, _v in sorted(_LLM_CACHE.items(), key=lambda kv: kv[1][0])[:n_evict]:
            _LLM_CACHE.pop(k, None)


def _llm_cache_put(key: str, val: tuple[str, str]) -> None:
    try:
        if not key:
            return
        if len(_LLM_CACHE) >= _LLM_CACHE_MAX:
            _llm_cache_evict()  # W1.11: partial evict (expired + oldest), full clear nahi
        _LLM_CACHE[key] = (time.time(), val)
    except Exception:
        pass


def _resolve_llm_profile(profile: str | None, max_tokens: int) -> str:
    if profile:
        p = profile.strip().lower()
        if p in ("bulk", "batch", "content"):
            return "bulk"
        if p in ("realtime", "voice", "live"):
            return "realtime"
    try:
        thresh = int(os.getenv("LLM_BULK_TOKEN_THRESHOLD", "180") or 180)
    except Exception:
        thresh = 180
    return "bulk" if max_tokens >= thresh else "realtime"


def _build_llm_chain(profile: str) -> list[tuple[str, str]]:
    """Provider order — realtime favours latency; bulk favours Cerebras throughput."""
    import os as _os

    gemini_model = (_os.getenv("GEMINI_LLM_MODEL", "") or "").strip() or _GEMINI_LLM_MODEL
    try:
        from app.config import settings

        gemini_primary = getattr(settings, "gemini_primary", False)
        default_llm = (getattr(settings, "default_llm", "") or "").strip()
        if not _os.getenv("GEMINI_LLM_MODEL", "").strip() and default_llm.lower().startswith(
            "gemini"
        ):
            gemini_model = default_llm
    except Exception:
        gemini_primary = _os.getenv("GEMINI_PRIMARY", "0").strip().lower() in ("1", "true", "yes")
        gemini_model = (
            (_os.getenv("GEMINI_LLM_MODEL", "") or "").strip()
            or (
                (_os.getenv("DEFAULT_LLM", "") or "").strip()
                if (_os.getenv("DEFAULT_LLM", "") or "").strip().lower().startswith("gemini")
                else ""
            )
            or _GEMINI_LLM_MODEL
        )

    # NVIDIA NIM (free tier: 40 RPM + metered credits) — deep-tail FALLBACK by default.
    # Model env-overridable; NVIDIA_PRIMARY=1 promotes it to the chain HEAD (NOT
    # recommended: latency + 40 RPM + finite credits make it unfit for the hot path).
    nvidia_model = _os.getenv("NVIDIA_LLM_MODEL", _NVIDIA_LLM_MODEL)
    nvidia_primary = _os.getenv("NVIDIA_PRIMARY", "0").strip().lower() in ("1", "true", "yes")

    _ollama_entry = ("ollama", _ollama_model())
    if profile == "bulk":
        core = [
            ("cerebras", _CEREBRAS_LLM_MODEL),
            ("groq", _GROQ_LLM_MODEL),
            ("mistral", _MISTRAL_LLM_MODEL),
        ]
    else:
        # realtime = latency-first: Groq fastest free inference, Cerebras ~instant,
        # Mistral = reliable but p50 latency higher → bulk primary, not realtime.
        # (audit §10 [LOW] 2026-07-06: old order was mistral→groq→cerebras)
        core = [
            ("groq", _GROQ_LLM_MODEL),
            ("cerebras", _CEREBRAS_LLM_MODEL),
            ("mistral", _MISTRAL_LLM_MODEL),
        ]
    chain: list[tuple[str, str]] = []

    if gemini_primary:
        # Vertex AI (subscription/Cloud) pehle — API key se zyada stable quota
        if _vertex_available():
            chain.append(("gemini_vertex", gemini_model))
        # API-key Gemini bhi — agar key available ho (fallback ya standalone)
        chain.append(("gemini", gemini_model))

    if _ollama_primary():
        chain.append(_ollama_entry)
    chain += core
    if not _ollama_primary():
        chain.append(_ollama_entry)
    # 2026 EXTRA free models — proven primaries (mistral/groq-head/cerebras) ke BAAD,
    # weaker gemini/openrouter-:free tail se PEHLE. Yeh tab kaam aate jab primary model
    # 429/TPD/decommission ho par provider zinda ho (Groq-TPD ke baad bhi Groq dusre
    # model serve kar sakta). Pure additive low-priority entries — koi flag nahi.
    # Kimi K2 + qwen3-32b removed (already decommissioned on Groq — research 2026-08-01).
    chain += [
        ("groq", _GROQ_LLAMA70B_MODEL),
        ("groq", _GROQ_QWEN3_MODEL),
    ]

    if not gemini_primary:
        # BUGFIX (2026-07-05): yahan hardcoded _GEMINI_LLM_MODEL (paid 2.5-flash) tha
        # jo GEMINI_LLM_MODEL/DEFAULT_LLM override ko IGNORE karta — free keys pe paid
        # model = 429/quota burn. Ab wahi overridable `gemini_model` (line ~544) use karo
        # jo gemini_primary path bhi use karta.
        chain.append(("gemini", gemini_model))

    chain += [
        ("sambanova", _SAMBANOVA_LLM_MODEL),
        # NVIDIA NIM deep-tail: AFTER sambanova (free-unlimited) to conserve metered
        # credits, but BEFORE the 404-prone openrouter :free tail (70B > flaky :free).
        ("nvidia", nvidia_model),
        ("openrouter", _OPENROUTER_LLM_MODEL),
        ("openrouter_2", _OPENROUTER_LLM_MODEL),
        ("openrouter_3", _OPENROUTER_LLM_MODEL),
        ("openrouter_4", _OPENROUTER_LLM_MODEL),
        ("openrouter", _OPENROUTER_LLM_MODEL2),
        ("openrouter_2", _OPENROUTER_LLM_MODEL2),
        ("openrouter", _OPENROUTER_LLM_MODEL3),
    ]
    if nvidia_primary:
        # Explicit opt-in only — put NVIDIA first (tail entry stays as harmless fallback;
        # shares the per-provider "nvidia" circuit-breaker so a tripped head skips the tail).
        chain.insert(0, ("nvidia", nvidia_model))
    return chain


def _blocked_for_provider(msgs: Any, provider: str) -> bool:
    """True if this (already-masked) payload must NOT be sent to this provider.

    Defense-in-depth after mask_customer_data(): catches anything the regex-based
    masker missed (e.g. a secret-looking token) before it reaches a free/unsafe
    external provider. Fail-open on unrelated errors — never breaks the chat path.
    """
    # Never stringify arbitrary objects: their repr may contain a hexadecimal memory
    # address that accidentally satisfies the phone-number matcher. Real call paths
    # provide message strings/lists/dicts; malformed input stays fail-open by contract.
    if not isinstance(msgs, str | list | dict):
        return False
    try:
        from app.platform.safe_ai_payload import SafePayloadError, block_if_sensitive

        block_if_sensitive(msgs, provider)
        return False
    except SafePayloadError as e:
        logger.warning("[free_ai] blocked provider=%s reason=%s", provider, e)
        return True
    except Exception:
        return False


async def chat_provider(
    provider: str,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 512,
    temperature: float = 0.5,
    scope: str = "council",
    timeout_s: float | None = None,
) -> tuple[str, str]:
    """Single forced provider+model call — LLM Council diversity ke liye.

    Chain fallback NAHI; provider down/missing ho to ("", provider). Never raises.
    """
    if not _OPENAI_OK:
        return "", provider or "none"
    p = (provider or "").strip()
    if _provider_down(p):
        return "", p
    client = _client(p)
    if client is None:
        return "", p
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
        return "", p
    try:
        from app.llm import budget_guard

        if budget_guard.active():
            _ok, _bi = await budget_guard.allow(scope)
            if not _ok:
                logger.warning(
                    "[free_ai] budget guard blocked scope=%s reason=%s", scope, _bi.get("reason")
                )
                return "", p
    except Exception:
        pass
    # PII masking — chat_provider bhi external providers use karta hai.
    _msgs_original = msgs
    try:
        from app.platform.safe_ai_payload import mask_customer_data

        msgs = mask_customer_data(msgs)
        if msgs is None:
            msgs = _msgs_original
    except Exception:
        msgs = _msgs_original
    if _blocked_for_provider(msgs, p):
        return "", p

    tlim = timeout_s if timeout_s and timeout_s > 0 else max(_CALL_TIMEOUT_S, 30.0)
    # 2026-08-23 fix: gpt-oss* = REASONING models — hidden reasoning tokens
    # `max_tokens` se pehle khate hain. Prod evidence: telecaller max_tokens=56
    # par Groq gpt-oss-20b ne finish='length' + content='' diya (T1 probe);
    # max_tokens=512 par 'GROQ_OK' (T2). Bina headroom ke har voice turn top-2
    # providers (groq+cerebras dono gpt-oss) se EMPTY aata tha -> Mistral fallback.
    _mt = int(max_tokens or 0)
    if "gpt-oss" in (model or "") and 0 < _mt < 512:
        _mt = 512
    _t0 = time.monotonic()
    try:
        with _llm_span("chat_provider", model=model, provider=p) as _obs:
            resp = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    max_tokens=_mt,
                    temperature=temperature,
                ),
                timeout=tlim,
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
            _reset_cooldown_streak(p)
            try:
                from app.platform import llm_metrics

                llm_metrics.record(p, True, (time.monotonic() - _t0) * 1000)
            except Exception:
                pass
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
            return text, p
    except Exception as e:
        _es = _err_str(e)
        _trip_cooldown(p, _es)
        try:
            from app.platform import llm_metrics

            llm_metrics.record(p, False, (time.monotonic() - _t0) * 1000, _es)
        except Exception:
            pass
        logger.warning(f"[free_ai] chat_provider {p}/{model} failed: {e}")
    return "", p


async def chat(
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 90,
    temperature: float = 0.6,
    scope: str = "global",
    profile: str | None = None,
    agent_key: str | None = None,
    product: str | None = None,
) -> tuple[str, str]:
    """Free LLM chain par ek short reply lo.

    ``profile``: ``realtime`` (voice/low-latency, default) ya ``bulk`` (content/blog).
    Unset → ``bulk`` auto jab ``max_tokens >= LLM_BULK_TOKEN_THRESHOLD`` (default 180).
    ``agent_key`` / ``product``: Agent OS governance for OmniRoute bulk hook (ADR-108/109).

    Chain order:
      realtime — mistral → groq → cerebras → …
      bulk     — cerebras → groq → mistral → …  (high-throughput content gen)
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

    # Response cache — bulk/content profile DEFAULT cached (W1.10), realtime nahi.
    # Budget guard ke PEHLE: cached reply ka zero real LLM cost hai, isliye over-budget
    # hone par bhi cache-hit serve hona chahiye (review finding #5).
    prof = _resolve_llm_profile(profile, max_tokens)
    _ck = _llm_cache_key(system, msgs, max_tokens, temperature) if _llm_cache_on(prof) else ""
    if _ck:
        _hit = _llm_cache_get(_ck)
        try:
            # Cache hit-rate observability (W1.12 revisit-trigger prereq) — sirf jab
            # cache ON ho tab record; never-raise, file-append ultra-light.
            from app.platform import llm_metrics

            llm_metrics.record_cache(_hit is not None)
        except Exception:
            pass
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
                logger.warning(
                    "[free_ai] budget guard blocked scope=%s reason=%s", scope, _bi.get("reason")
                )
                return "", ""
    except Exception:
        pass  # guard error = proceed normally (fail-open)

    # PII masking — messages me customer data mask karo before any external provider call.
    # fail-OPEN: masking crash = message bhej do raw (keep agent alive), but log the error.
    _msgs_original = msgs
    try:
        from app.platform.safe_ai_payload import mask_customer_data

        msgs = mask_customer_data(msgs)
        if msgs is None:
            msgs = _msgs_original
    except Exception:
        msgs = _msgs_original

    # --- OmniRoute optional agent pre-hook (ADR-108, 2026-07-16) -------------
    # Double-gated (OMNIROUTE_ENABLED + OMNIROUTE_AGENTS, dono OFF default = INERT).
    # SIRF explicit bulk profile — realtime/default/other profiles NEVER enter
    # (ADR contract: bulk-only; `!= realtime` over-routed non-bulk). Fail-open.
    # Payload omniroute_client.generate() me dobara sanitize hota hai.
    _omni_agents_on = os.getenv("OMNIROUTE_AGENTS", "0").strip().lower() in ("1", "true", "yes")
    _omni_gate = prof == "bulk" and _omni_agents_on
    if _omni_gate:
        try:
            from app.platform.omniroute_client import try_agent_chat

            _omni_text = await try_agent_chat(msgs, agent_key=agent_key, product=product)
            if _omni_text:
                return _omni_text, "omniroute"
        except Exception as _omni_exc:  # defensive — hook kabhi chain nahi girayega
            logger.debug("[free_ai] omniroute agent hook bypass: %s", type(_omni_exc).__name__)

    chain = _build_llm_chain(prof)
    for provider, model in chain:
        if _provider_down(provider):
            continue  # circuit-breaker: provider abhi cooldown me hai

        # Vertex AI (subscription plan) — dynamic bearer token, fresh client per-call
        if provider == "gemini_vertex":
            if not _OPENAI_OK or not _vertex_available():
                continue
            if _blocked_for_provider(msgs, provider):
                continue
            _t0 = time.monotonic()
            try:
                token = await _vertex_bearer_token()
                if not token:
                    continue
                _vclient = AsyncOpenAI(
                    api_key=token,
                    base_url=_vertex_base_url(),
                    timeout=_CALL_TIMEOUT_S,
                )
                with _llm_span("chat", model=model, provider=provider) as _obs:
                    resp = await asyncio.wait_for(
                        _vclient.chat.completions.create(
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
                    try:
                        from app.platform import llm_metrics

                        llm_metrics.record(provider, True, (time.monotonic() - _t0) * 1000)
                    except Exception:
                        pass
                    if _ck:
                        _llm_cache_put(_ck, (text, provider))
                    return text, provider
            except Exception as e:
                _trip_cooldown(provider, _err_str(e))
                logger.warning(f"[free_ai] gemini_vertex chat failed: {e}")
            continue

        client = _client(provider)
        if client is None:
            continue
        if _blocked_for_provider(msgs, provider):
            continue
        _t0 = time.monotonic()
        # 2026-08-23 fix: reasoning-model token headroom (see chat_provider note).
        # gpt-oss* hidden reasoning tokens max_tokens khate hain -> content=''.
        _mt = int(max_tokens or 0)
        if "gpt-oss" in (model or "") and 0 < _mt < 512:
            _mt = 512
        try:
            with _llm_span("chat", model=model, provider=provider) as _obs:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model=model,
                        messages=msgs,
                        max_tokens=_mt,
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
            _es = _err_str(e)
            _trip_cooldown(provider, _es)
            try:
                from app.platform import llm_metrics

                llm_metrics.record(provider, False, (time.monotonic() - _t0) * 1000, _es)
            except Exception:
                pass
            logger.warning(f"[free_ai] {provider} chat failed: {e}")
            continue
    return "", ""


async def chat_stream(
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int = 90,
    temperature: float = 0.6,
    scope: str = "global",
    profile: str | None = None,
):
    """Async token deltas from the first working free provider (stream=True).

    Yields str fragments. Empty stream = no provider; caller falls back to chat().
    Never raises."""
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
        return

    try:
        from app.llm import budget_guard

        if budget_guard.active():
            _ok, _ = await budget_guard.allow(scope)
            if not _ok:
                return
    except Exception:
        pass

    # PII masking — chat_stream bhi external providers use karta hai.
    _msgs_original = msgs
    try:
        from app.platform.safe_ai_payload import mask_customer_data

        msgs = mask_customer_data(msgs)
        if msgs is None:
            msgs = _msgs_original
    except Exception:
        msgs = _msgs_original

    prof = _resolve_llm_profile(profile, max_tokens)

    chain = _build_llm_chain(prof)
    for provider, model in chain:
        if _provider_down(provider):
            continue
        client = _client(provider)
        if client is None:
            continue
        if _blocked_for_provider(msgs, provider):
            continue
        _t0 = time.monotonic()
        got = False
        stream = None
        try:
            stream = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=msgs,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    stream=True,
                ),
                timeout=_CALL_TIMEOUT_S,
            )
            # BOUNDED token loop (was an unbounded `async for` — see _STREAM_* notes).
            # Manual __anext__ so each token wait gets a deadline: a longer one for the
            # FIRST delta, a tight idle one after tokens start flowing, plus an overall
            # wall cap. A stalled stream now raises TimeoutError instead of hanging,
            # which trips the breaker and (only if nothing was streamed yet) falls
            # through to the next provider on the SAME call.
            _it = stream.__aiter__()
            while True:
                if (time.monotonic() - _t0) > _STREAM_TOTAL_S:
                    raise asyncio.TimeoutError("stream total budget exceeded")
                _per_wait = _STREAM_FIRST_TOKEN_S if not got else _STREAM_IDLE_S
                try:
                    chunk = await asyncio.wait_for(_it.__anext__(), timeout=_per_wait)
                except StopAsyncIteration:
                    break
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    got = True
                    yield delta
            if got:
                _reset_cooldown_streak(provider)
                try:
                    from app.platform import llm_metrics

                    llm_metrics.record(provider, True, (time.monotonic() - _t0) * 1000)
                except Exception:
                    pass
                return
        except Exception as e:
            _trip_cooldown(provider, _err_str(e))
            logger.debug("[free_ai] %s chat_stream failed/stalled: %s", provider, e)
            # Release the (possibly half-read) stream socket so it can't leak.
            if stream is not None:
                try:
                    await stream.aclose()
                except Exception:
                    pass
            # If we already streamed partial tokens to the caller, STOP — restarting on
            # another provider would duplicate/garble the spoken reply. Caller's own
            # non-stream fallback finishes the turn. Nothing streamed => try next provider.
            if got:
                return
            continue


def describe() -> dict[str, Any]:
    """/status diagnostics — kaunse free providers configured hain + chains."""
    chain = _build_llm_chain("realtime")
    llm_chain_desc = [f"{p}:{m}" for p, m in chain]
    return {
        "openai_sdk": _OPENAI_OK,
        "providers": _provider_flags(),
        "stt_chain": [f"groq:{_GROQ_STT_MODEL}", "gemini-audio", "local:faster-whisper"],
        "llm_chain": llm_chain_desc,
    }


__all__ = [
    "transcribe_audio",
    "chat",
    "chat_provider",
    "chat_stream",
    "describe",
    "PROVIDERS_AVAILABLE",
]
