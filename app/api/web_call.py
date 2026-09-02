"""
Web Call — Browser TEST MODE (Dograh-inspired)
==============================================

Lets you TALK/CHAT with the voice bot directly in the browser with NO telephony
(no real phone ring, no per-minute cost). This is a TEST MODE for trying flows
and prompts before going live on real calls — mirroring Dograh's "Web Call".

Endpoints (router mounted by main.py separately):
    WS  /api/web-call/ws      — bidirectional chat with the bot.
    GET /api/web-call/config  — whether the pipeline/providers are available.

WebSocket protocol
------------------
Client -> Server (JSON):
    {"type": "user",  "text": "Hello",  "niche": "solar", "flow": "qualify"}
    {"type": "audio", "audio_b64": "<base64>", "niche": "solar"}   # optional STT
    {"type": "start", "niche": "solar", "flow": "qualify"}          # optional init
    {"type": "ping"}

Server -> Client (JSON):
    {"type": "ready",  "test_mode": true, "pipeline": false, "providers": {...}}
    {"type": "bot",    "text": "...", "audio_b64": "<base64?>", "test_mode": true}
    {"type": "info",   "text": "..."}
    {"type": "error",  "text": "..."}
    {"type": "close_signal", "business_name": "...", "niche": "...", "phone": "..."}
        # WEBCALL_INLINE_SIGNUP=1 only -- caller wants to proceed and a phone is
        # known; browser shows the inline trial-signup overlay (see
        # frontend/web_call.html).
    {"type": "pong"}

Import-safe: degrades gracefully if the VoicePipeline or providers are missing —
falls back to a simple LLM responder, and if even that is unavailable, an echo.
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import (
    APIRouter,
    File,
    Form,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _CALL_RECORDINGS_DIR() -> str:
    """Web/phone call recordings root — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_recordings_dir

    return str(call_recordings_dir())


router = APIRouter(prefix="/web-call", tags=["Web Call (Test Mode)"])


# Per-IP abuse guard for the PUBLIC web-call WS — anyone can open this socket and
# burn free LLM/STT/TTS. Cap new sessions per IP. FAIL-OPEN: limiter error/unset
# never blocks legit traffic. (HTTP rate_limit() dep can't wrap a WebSocket, so we
# check inline at connect.)
try:
    from app.cache import RateLimiter

    _WS_LIMITER: Any = RateLimiter(prefix="rl:webcallws", max_requests=40, window_seconds=60)
except Exception:  # pragma: no cover - cache layer optional
    _WS_LIMITER = None


def _ws_client_ip(ws: WebSocket) -> str:
    """Real client IP behind Caddy (X-Forwarded-For/Real-IP) warna socket peer."""
    try:
        xff = ws.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        xri = ws.headers.get("x-real-ip")
        if xri:
            return xri.strip()
        return ws.client.host if ws.client else "unknown"
    except Exception:
        return "unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_lead_key(raw: str | None) -> str | None:
    try:
        from app.voice_agent.web_call_store import normalize_lead_key

        return normalize_lead_key(raw)
    except Exception:
        k = (raw or "").strip()
        return k if len(k) >= 8 else None


def _apply_memory_subject(tcb: Any, session: dict[str, Any]) -> None:
    """Cross-session recall — stable browser lead_key (web:{key}), phone parity."""
    lead = _normalize_lead_key(session.get("lead_key"))
    if not lead or tcb is None:
        return
    try:
        from app.voice_agent import agent_memory

        if agent_memory.is_enabled():
            tcb.set_memory_subject(f"web:{lead}")
            session["memory_subject"] = f"web:{lead}"
    except Exception:
        pass


def _memory_meta(session: dict[str, Any]) -> dict[str, Any]:
    lead = _normalize_lead_key(session.get("lead_key"))
    enabled = False
    try:
        from app.voice_agent import agent_memory

        enabled = agent_memory.is_enabled()
    except Exception:
        pass
    return {
        "lead_key": lead,
        "session_id": session.get("session_id"),
        "memory_enabled": enabled,
        "memory_active": bool(enabled and lead),
        "memory_subject": session.get("memory_subject") if enabled and lead else None,
    }


def _log_turn(
    session: dict[str, Any],
    role: str,
    text: str,
    meta: dict[str, Any] | None = None,
) -> None:
    t = (text or "").strip()
    if not t:
        return
    turns = session.setdefault("turns", [])
    turn: dict[str, Any] = {"ts": _now_iso(), "role": role, "text": t[:2000]}
    if meta:
        # Per-turn diagnostics (assistant turns): heard=STT text the bot replied
        # to, + stage latencies (stt_ms/llm_ms/tts_ms) and perceived total
        # latency_ms (user-msg-arrival -> bot-starts-speaking). Lets the admin
        # viewer show "kitni der me reply diya" + STT-fault vs brain-fault.
        for k in ("heard", "stt_ms", "llm_ms", "tts_ms", "latency_ms"):
            v = meta.get(k)
            if v is not None:
                turn[k] = v
    turns.append(turn)


def _turn_meta(timing: dict[str, Any], t_recv: float, heard: str) -> dict[str, Any]:
    """Assemble assistant-turn diagnostics from the stage clocks.

    latency_ms = PERCEIVED gap = user-message-arrival -> bot-starts-speaking
    (first audio chunk send). first_chunk_at missing (no audio sent) => fall back
    to elapsed-now. Pure arithmetic, never raises.
    """
    first = timing.get("first_chunk_at")
    try:
        total_ms = int(((first if first is not None else time.monotonic()) - t_recv) * 1000)
    except Exception:
        total_ms = None
    return {
        "heard": (heard or "").strip()[:300] or None,
        "stt_ms": timing.get("stt_ms"),
        "llm_ms": timing.get("llm_ms"),
        "tts_ms": timing.get("tts_ms"),
        "latency_ms": total_ms,
    }


def _is_booking_intent(text: str) -> bool:
    """Booking/appointment ACTION-intent — sirf TAB agentic tool-path (real
    calendar_booking) engage karo. Normal turns instrumented + streamed P1 reply
    pe rahein (no regression). Roman + Devanagari dono."""
    t = (text or "").lower()
    if any(
        w in t
        for w in (
            "book",
            "appointment",
            "appoint",
            "visit",
            "meeting",
            "slot",
            "schedule",
            "demo fix",
            "kab milen",
            "milne aa",
            "time de do",
            "reschedule",
            "postpone",
            "time badal",
            "din badal",
            "change kar",
            "aage badha",
        )
    ):
        return True
    return any(
        w in (text or "") for w in ("बुक", "अपॉइंटमेंट", "मीटिंग", "विजिट", "स्लॉट", "रीशेड्यूल", "टाइम बदल")
    )


def _history_from_session(
    session: dict[str, Any], *, exclude_last_user: str | None = None
) -> list[dict[str, str]]:
    """Turn log = source of truth — WS handler history desync se wrong jawab na aaye."""
    out: list[dict[str, str]] = []
    for t in session.get("turns") or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role") or "user")
        text = str(t.get("text") or t.get("content") or "").strip()
        if text:
            out.append({"role": role, "content": text})
    if (
        exclude_last_user
        and out
        and out[-1].get("role") == "user"
        and out[-1].get("content") == exclude_last_user.strip()
    ):
        out = out[:-1]
    return out


def _pitch_discovery_handoff(session: dict[str, Any], tcbrain: Any | None, pst: Any) -> None:
    """Interest gate khatam — ab TelecallerBrain customer ke hisaab se chale."""
    if pst is None or getattr(pst, "phase", "") != "discovery":
        return
    if tcbrain is not None and hasattr(tcbrain, "confirm_interest"):
        try:
            tcbrain.confirm_interest()
        except Exception:
            pass
    session.pop("pitch_state", None)


def _persist_session(session: dict[str, Any]) -> None:
    if session.get("saved"):
        return
    turns = session.get("turns") or []
    if not turns:
        return
    try:
        from app.voice_agent.web_call_store import append_session

        started = session.get("started_at") or _now_iso()
        ended = _now_iso()
        try:
            t0 = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(str(ended).replace("Z", "+00:00"))
            dur = max(0, int((t1 - t0).total_seconds()))
        except Exception:
            dur = 0
        ok = append_session(
            {
                "session_id": session.get("session_id"),
                "lead_key": session.get("lead_key"),
                "started_at": started,
                "ended_at": ended,
                "duration_s": dur,
                "niche": session.get("niche"),
                "flow": session.get("flow"),
                "client_name": session.get("client_name"),
                "memory_subject": session.get("memory_subject"),
                "turns": turns,
                "turn_count": len(turns),
            }
        )
        if ok:
            session["saved"] = True
    except Exception as e:
        logger.debug(f"web-call: persist session skip ({e})")


# ---------------------------------------------------------------------------- #
# Lazy, import-safe resolvers
# ---------------------------------------------------------------------------- #
def _get_pipeline() -> Any | None:
    """Lazily build app.voice_agent.pipeline.VoicePipeline (owned by another
    agent — may not exist). Returns None on any failure."""
    try:
        from app.voice_agent.pipeline import VoicePipeline  # type: ignore

        return VoicePipeline()
    except Exception as e:
        logger.debug(f"web-call: VoicePipeline unavailable ({e}).")
        return None


def _get_registry_describe() -> dict[str, Any] | None:
    """Call get_registry().describe() if such a provider registry exists."""
    try:
        from app.voice_agent.registry import get_registry  # type: ignore

        reg = get_registry()
        describe = getattr(reg, "describe", None)
        if callable(describe):
            return describe()
    except Exception as e:
        logger.debug(f"web-call: provider registry unavailable ({e}).")
    return None


def _get_llm_brain() -> Any | None:
    """Fallback responder — the LLM brain — if no full pipeline is present."""
    try:
        from app.voice_agent.llm_brain import LLMBrain  # type: ignore

        return LLMBrain()
    except Exception as e:
        logger.debug(f"web-call: LLMBrain unavailable ({e}).")
        return None


async def _run_blocking(fn, *args, timeout: float = 15.0, default=None):
    """
    Run a potentially heavy SYNC callable off the event loop with a hard
    timeout. Dialog/brain builders KB/fastembed load trigger kar sakte hain
    (missing model cache = HuggingFace runtime download = minutes ka hang) —
    yeh KABHI event loop par nahi chalna chahiye (2026-06-12 prod-down lesson:
    dono uvicorn workers isi se freeze hue the). Timeout/error par `default`
    return hota hai (caller gracefully degrade karta hai). Never raises.
    """
    import asyncio

    try:
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout)
    except Exception as e:
        logger.warning(f"web-call: blocking init '{getattr(fn, '__name__', fn)}' skipped ({e})")
        return default


def _get_natural_dialog(niche: str, client_name: str, client_service: str) -> Any | None:
    """
    Build the NaturalDialogManager — the human-like "listen -> understand ->
    answer" brain. THIS is what makes the bot reply like a person: short,
    Hinglish, acknowledges what the customer said, answers their QUESTION first,
    asks ONE thing at a time — instead of monologuing a sales script and never
    listening. It internally uses the LLM brain (Gemini) when a key is present,
    else clean rule-based replies. Returns None on any failure (caller degrades).
    """
    try:
        from app.voice_agent.natural_dialog import NaturalDialogManager  # type: ignore

        niche = niche or "general"
        return NaturalDialogManager(
            niche=niche,
            client_name=client_name or "Demo Co",
            client_service=client_service or niche.replace("_", " "),
        )
    except Exception as e:
        logger.debug(f"web-call: NaturalDialogManager unavailable ({e}).")
        return None


import re as _re

# Thinking fillers (played only on mic/audio turns while the LLM thinks).
# "Ji..." dropped (2026-07-17 owner feedback: habit-address fillers confuse the
# caller); only short neutral bridges kept — phone _FILLER_TEXTS parity.
_FILLER_LINES = ["Hmm...", "Achha...", "Ek second..."]
_filler_idx = 0


async def _filler_b64() -> str | None:
    """
    Short Hinglish filler phrase (mp3 b64) — sent INSTANTLY while LLM thinks so
    user doesn't hear dead silence. Rotates through _FILLER_LINES. Never raises.
    """
    global _filler_idx
    text = _FILLER_LINES[_filler_idx % len(_FILLER_LINES)]
    _filler_idx += 1
    return await _edge_tts_mp3_b64(text)


def _web_call_edge_enabled() -> bool:
    """FREE EdgeTTS Swara voice on test-call — default ON; WEB_CALL_EDGE_TTS=0 se band."""
    import os

    v = os.environ.get("WEB_CALL_EDGE_TTS", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _webcall_inline_signup_enabled() -> bool:
    """Browser-native trial-signup overlay on a voice close-signal (landing-page
    onboarding). Default OFF — new funnel-critical behavior, verify manually
    before enabling in prod. WEBCALL_INLINE_SIGNUP=1 to turn on."""
    import os

    v = os.environ.get("WEBCALL_INLINE_SIGNUP", "0").strip().lower()
    return v in ("1", "true", "yes")


def _close_signal_payload(tcbrain: Any) -> dict[str, Any] | None:
    """WS payload to tell the browser "show the inline trial-signup overlay
    now" -- only when the flag is on AND this exact reply() turn is the one
    that made _on_close_signal() fire for real (deal write + WhatsApp)."""
    if not _webcall_inline_signup_enabled():
        return None
    if not getattr(tcbrain, "close_signal_fired", False):
        return None
    return {
        "type": "close_signal",
        "business_name": getattr(tcbrain, "client_name", "") or "",
        "niche": getattr(tcbrain, "niche", "") or "",
        "phone": getattr(tcbrain, "caller_phone", "") or "",
    }


async def _bot_audio_b64(text: str) -> str | None:
    """EdgeTTS mp3 b64 with deadline — fail = browser TTS fallback."""
    if not _web_call_edge_enabled() or not (text or "").strip():
        return None
    import asyncio

    try:
        return await asyncio.wait_for(_edge_tts_mp3_b64(text), timeout=5.5)
    except Exception:
        return None


async def _send_bot_message(websocket: WebSocket, text: str, **extra: Any) -> None:
    """Unified bot turn — text + optional Swara mp3 (phone-parity, free)."""
    t = (text or "").strip()
    if not t:
        return
    # Callers that pre-synthesise a group of messages can pass the result here;
    # this keeps ordered WS delivery while avoiding serial EdgeTTS waits.
    audio_b64 = extra.pop("audio_b64", None) if "audio_b64" in extra else await _bot_audio_b64(t)
    payload: dict[str, Any] = {
        "type": "bot",
        "text": t,
        "audio_b64": audio_b64,
        "test_mode": True,
    }
    payload.update(extra)
    await websocket.send_json(payload)


def _split_sentences(text: str) -> list[str]:
    """
    Split bot reply into sentences for streaming TTS.
    Splits on '.' '।' '?' '!' followed by space/end.
    Preserves trailing punctuation. Short trailing fragment joins previous.
    """
    parts = _re.split(r"(?<=[.।?!])\s+", text.strip())
    sentences: list[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if sentences and len(p) <= 8:
            sentences[-1] = sentences[-1] + " " + p
        else:
            sentences.append(p)
    return sentences or [text]


async def _send_tcbrain_sentence_chunks(
    websocket: WebSocket,
    *,
    sentences: list[str],
    user_text: str,
    full_reply: str,
    llm_stream: bool = False,
    timing: dict[str, Any] | None = None,
) -> None:
    """EdgeTTS Swara + WS JSON — mp3 attached when synth succeeds (default ON).

    LATENCY FIX (2026-06-28): har sentence ka synth PARALLEL me chalta hai par
    chunk 0 uska audio ready hote hi SEEDHA bhej deta — pehle `gather()` SAARE
    sentences ka wait karta tha to first-word SABSE SLOW sentence ke synth pe atak
    jaata (5-6s "noob" gap ka ek bada root). Ab chunk 0 = sirf apne synth (~1.5s)
    ka wait; baaki sentences background me synth hote rehte (client unhe sequence
    me bajata, koi drop nahi). Per-synth `wait_for` cap intact (bounded await).
    """
    total = len(sentences)
    edge_on = _web_call_edge_enabled()

    async def _one(s: str) -> str | None:
        try:
            return await asyncio.wait_for(_edge_tts_mp3_b64(s), timeout=5.0)
        except Exception:
            return None

    # Launch ALL syntheses up-front so they run concurrently; await EACH in order
    # right before sending its chunk (chunk 0 no longer blocked on the slowest).
    tasks = [asyncio.create_task(_one(s)) for s in sentences] if edge_on else None

    try:
        for i, sentence in enumerate(sentences):
            audio_b64: str | None = None
            if edge_on and tasks is not None:
                try:
                    audio_b64 = await tasks[i]
                except Exception:
                    audio_b64 = None
            # Perceived "bot starts speaking" = first chunk's send (audio ready).
            if i == 0 and timing is not None and "first_chunk_at" not in timing:
                timing["first_chunk_at"] = time.monotonic()
            payload: dict[str, Any] = {
                "type": "bot",
                "text": sentence,
                "audio_b64": audio_b64,
                "heard": user_text if i == 0 else None,
                "chunk_index": i,
                "test_mode": True,
                "llm_stream": llm_stream,
            }
            if i == 0:
                payload["full_text"] = full_reply
            if total > 1:
                payload["chunk_total"] = total
            await websocket.send_json(payload)
    finally:
        # Client disconnect / outer-turn cancel mid-loop => cancel pending synth
        # tasks so no orphaned EdgeTTS connections leak (bounded already, but tidy).
        if tasks:
            for t in tasks:
                if not t.done():
                    t.cancel()


async def _edge_tts_mp3_b64(text: str) -> str | None:
    """
    Synthesize `text` to the SAME natural Hindi voice as the phone agent
    (EdgeTTS hi-IN-SwaraNeural, slightly brisk) and return a base64-encoded mp3
    string — or None on any failure / missing edge-tts. When None, the browser
    falls back to its own speechSynthesis (existing behavior). Time-capped (<6s)
    so a slow/blocked TTS never stalls the chat turn. Import-safe — never raises.
    """
    import asyncio
    import base64

    text = (text or "").strip()[:800]
    if not text:
        return None

    # PRO voice = Sarvam Bulbul v3 (India-native, Hinglish prosody + Indian name
    # pronunciation, sub-250ms streaming) — the professional India-market TTS. Tried
    # FIRST when TTS_PROVIDER=sarvam + SARVAM_API_KEY set. Returns WAV b64 (frontend
    # auto-detects). INERT without key (paid ~Rs2/min) → falls through to free floor.
    if (
        os.environ.get("TTS_PROVIDER", "").strip().lower() == "sarvam"
        and os.environ.get("SARVAM_API_KEY", "").strip()
    ):
        try:
            import base64 as _b64

            from app.voice_agent.indic_providers import SarvamTTS

            _wav = await asyncio.wait_for(SarvamTTS().synthesize(text), timeout=6.0)
            if _wav:
                return _b64.b64encode(_wav).decode("ascii")
        except Exception:
            pass

    # SELF-HOSTED voice (AI4Bharat IndicF5 on your own GPU) — FREE, no per-min cost.
    # Tried when TTS_PROVIDER=ai4bharat + AI4BHARAT_ENDPOINT (your voice_stack server).
    # INERT without the endpoint → free EdgeTTS floor. (voice_stack/README.md)
    if (
        os.environ.get("TTS_PROVIDER", "").strip().lower() == "ai4bharat"
        and os.environ.get("AI4BHARAT_ENDPOINT", "").strip()
    ):
        try:
            import base64 as _b64

            from app.voice_agent.indic_providers import Ai4BharatTTS

            _wav = await asyncio.wait_for(Ai4BharatTTS().synthesize(text), timeout=8.0)
            if _wav:
                return _b64.b64encode(_wav).decode("ascii")
        except Exception:
            pass

    # PREMIUM voice = Gemini native TTS (free, reuses existing GEMINI_API_KEY) tried
    # next when enabled; any miss (no key / GEMINI_TTS=0 / quota / error) falls
    # through to the free EdgeTTS floor below. Returns WAV b64 (frontend auto-detects
    # WAV vs mp3). INERT without key = behaviour unchanged.
    try:
        from app.voice_agent import gemini_tts

        if gemini_tts.is_enabled():
            _gv = await gemini_tts.synth_wav_b64(text)
            if _gv:
                return _gv
    except Exception:
        pass

    async def _synth() -> str | None:
        try:
            import edge_tts  # type: ignore
        except Exception:
            return None
        try:
            try:
                # Web-call is the enterprise TEST/proxy surface for the phone
                # agent, so its Swara pace/pitch must MATCH the phone defaults
                # (+32% rate, -8Hz pitch; 2026-08-23 owner tune). WEB_TTS_RATE /
                # WEB_TTS_PITCH still win per-env. Phone = VOBIZ_TTS_RATE/PITCH.
                _wrate = os.environ.get("WEB_TTS_RATE", "+32%").strip() or "+32%"
                _wpitch = os.environ.get("WEB_TTS_PITCH", "-8Hz").strip() or "-8Hz"
                _wkw = {"rate": _wrate}
                if _wpitch:
                    _wkw["pitch"] = _wpitch
                comm = edge_tts.Communicate(text, "hi-IN-SwaraNeural", **_wkw)
            except TypeError:
                # edge-tts build without the prosody kwargs — synth at defaults.
                comm = edge_tts.Communicate(text, "hi-IN-SwaraNeural")
            audio = bytearray()
            async for chunk in comm.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    audio.extend(chunk["data"])
            if not audio:
                return None
            return base64.b64encode(bytes(audio)).decode("ascii")
        except Exception as e:
            logger.debug(f"web-call: EdgeTTS synth failed ({e}).")
            return None

    try:
        return await asyncio.wait_for(_synth(), timeout=6.0)
    except Exception:
        return None


def _script_opening(niche: str, client_name: str = "Demo Co") -> str:
    """
    Professional niche-script opening (get_script(niche)["opening"]) with the
    [Company]/[Name]/[Project] placeholders filled so nothing leaks into speech.
    Falls back to a generic Hinglish greeting. Import-safe — never raises.
    """
    opening = ""
    try:
        from app.voice_agent.niche_scripts import get_script  # type: ignore

        opening = (get_script(niche) or {}).get("opening", "") or ""
    except Exception:
        opening = ""
    if opening:
        opening = (
            opening.replace("[Company]", client_name or "hamari company")
            .replace("[Name]", "Swara")
            .replace("[Project]", "hamare project")
        )
        return opening.strip()
    from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO

    return UNIVERSAL_AGENT_INTRO


async def _maybe_await(value: Any) -> Any:
    import asyncio

    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


def _pipeline_text_method(pipeline: Any) -> Any | None:
    """
    Return the pipeline's text-responder method, or None.
    VoicePipeline is built for live audio streaming and may expose NO text
    method at all — in that case the web-call demo must use the LLM brain,
    not claim "pipeline" and then silently fall through to echo.
    """
    if pipeline is None:
        return None
    for name in ("respond", "process_text", "handle_text", "chat"):
        fn = getattr(pipeline, name, None)
        if callable(fn):
            return fn
    return None


# ---------------------------------------------------------------------------- #
# Config endpoint
# ---------------------------------------------------------------------------- #
@router.get("/config")
async def web_call_config() -> dict[str, Any]:
    """
    Report whether the pipeline / providers are available + active provider
    names. Always returns 200 — degrades gracefully.
    """
    pipeline = _get_pipeline()
    pipeline_can_text = _pipeline_text_method(pipeline) is not None
    registry = _get_registry_describe()
    brain_available = _get_llm_brain() is not None
    natural_available = _get_natural_dialog("general", "Demo Co", "") is not None

    # Telephony providers (for the dashboard's awareness) — best-effort.
    telephony: dict[str, Any] = {}
    try:
        from app.telephony.telephony_service import get_telephony_service

        telephony = get_telephony_service().validate_config()
    except Exception as e:
        logger.debug(f"web-call: telephony info unavailable ({e}).")

    # Professional phone-agent brain availability (the SAME brain web-call uses).
    telecaller_available = False
    try:
        from app.voice_agent.telecaller_brain import TelecallerBrain  # type: ignore

        TelecallerBrain(niche="general", client_name="Demo Co")
        telecaller_available = True
    except Exception as e:
        logger.debug(f"web-call: TelecallerBrain unavailable ({e}).")

    # Natural Swara voice (EdgeTTS) availability — when True the bot returns mp3
    # audio_b64; else the browser uses its own speechSynthesis.
    try:
        import edge_tts  # type: ignore  # noqa: F401

        natural_voice_available = True
    except Exception:
        natural_voice_available = False

    try:
        from app.voice_agent.llm_stream_tts import stream_tts_enabled

        llm_stream_tts = stream_tts_enabled()
    except Exception:
        llm_stream_tts = False

    memory_enabled = False
    try:
        from app.voice_agent import agent_memory

        memory_enabled = agent_memory.is_enabled()
    except Exception:
        pass

    # Premium voice (Gemini native TTS) active? — True jab GEMINI_API_KEY set +
    # GEMINI_TTS!=0. Inert = EdgeTTS floor.
    premium_voice = False
    try:
        from app.voice_agent import gemini_tts

        premium_voice = gemini_tts.is_enabled()
    except Exception:
        pass

    return {
        "test_mode": True,
        "note": "Web Call is TEST MODE — talk to the bot in the browser, no real phone call is placed.",
        "llm_stream_tts": llm_stream_tts,
        "telecaller_available": telecaller_available,
        "memory_enabled": memory_enabled,
        "natural_voice_available": natural_voice_available,
        "premium_voice": premium_voice,
        "voice": (
            "gemini-tts"
            if premium_voice
            else ("hi-IN-SwaraNeural" if natural_voice_available else None)
        ),
        "natural_dialog_available": natural_available,
        "pipeline_available": pipeline is not None,
        "llm_fallback_available": brain_available,
        "providers": registry or {"detail": "No provider registry; using fallback responder."},
        "telephony": telephony or {"detail": "Telephony info unavailable."},
        "responder": (
            "telecaller"
            if telecaller_available
            else (
                "natural"
                if natural_available
                else ("pipeline" if pipeline_can_text else ("llm" if brain_available else "echo"))
            )
        ),
    }


@router.get("/history")
async def web_call_history(
    lead_key: str = Query(..., min_length=8, max_length=64),
    limit: int = Query(25, ge=1, le=50),
    include_turns: bool = Query(False, description="Full transcript per row (heavy)"),
) -> dict[str, Any]:
    """Past test-call transcripts for this browser lead_key (newest first)."""
    try:
        from app.voice_agent.web_call_store import list_sessions, normalize_lead_key

        lk = normalize_lead_key(lead_key)
        if not lk:
            return {"lead_key": None, "sessions": [], "total": 0}
        sessions = list_sessions(lk, limit=limit, include_turns=include_turns)
        return {"lead_key": lk, "sessions": sessions, "total": len(sessions)}
    except Exception as e:
        logger.debug(f"web-call: history list failed ({e})")
        return {"lead_key": lead_key, "sessions": [], "total": 0}


@router.get("/session/{session_id}")
async def web_call_session_detail(
    session_id: str,
    lead_key: str = Query(..., min_length=8, max_length=64),
) -> dict[str, Any]:
    """One saved test-call session + full transcript (lead_key must match)."""
    try:
        from app.voice_agent.web_call_store import (
            get_session,
            normalize_lead_key,
            normalize_session_id,
        )

        lk = normalize_lead_key(lead_key)
        sid = normalize_session_id(session_id)
        if not lk or not sid:
            return {"ok": False, "session": None}
        row = get_session(sid, lk)
        if not row:
            return {"ok": False, "session": None}
        return {
            "ok": True,
            "session": {
                "session_id": row.get("session_id"),
                "started_at": row.get("started_at"),
                "ended_at": row.get("ended_at"),
                "duration_s": row.get("duration_s"),
                "niche": row.get("niche"),
                "flow": row.get("flow"),
                "client_name": row.get("client_name"),
                "turn_count": row.get("turn_count") or len(row.get("turns") or []),
                "turns": row.get("turns") or [],
            },
        }
    except Exception as e:
        logger.debug(f"web-call: session detail failed ({e})")
        return {"ok": False, "session": None}


# Audio-recording upload guard (PUBLIC endpoint — same abuse surface as the WS).
try:
    from app.cache import RateLimiter as _RecRateLimiter

    _REC_LIMITER: Any = _RecRateLimiter(prefix="rl:webcallrec", max_requests=20, window_seconds=60)
except Exception:  # pragma: no cover
    _REC_LIMITER = None

_REC_MAX_BYTES = 12_000_000  # ~12MB — test calls are short; bigger = reject


def _rec_ext(blob: bytes) -> str:
    """Container ext from magic bytes (MediaRecorder = webm Chrome / mp4 Safari /
    ogg Firefox). Unknown => webm (Chrome default, our primary)."""
    if blob[:4] == b"\x1aE\xdf\xa3":
        return "webm"
    if len(blob) > 8 and blob[4:8] == b"ftyp":
        return "mp4"
    if blob[:4] == b"OggS":
        return "ogg"
    return "webm"


def _write_recording_sync(rec_dir: str, out_path: str, blob: bytes) -> None:
    """Blocking mkdir+write — MUST run via asyncio.to_thread (12MB write on the
    Docker overlay-fs can block a worker; project's #1 prod-down class)."""
    os.makedirs(rec_dir, exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(blob)


@router.post("/recording", summary="Upload a web test-call audio recording (mixed mic+bot)")
async def web_call_recording_upload(
    request: Request,
    file: UploadFile = File(...),
    session_id: str = Form(...),
    lead_key: str = Form(""),
) -> dict[str, Any]:
    """
    Browser ne poori test-call ka mixed audio (user mic + Swara TTS) record karke
    yahan upload kiya. data/call_recordings/YYYY-MM-DD/webcall_{sid}.<ext> me save —
    phone WAVs ki SAME jagah, taaki admin "Call Recordings" + Web Test Calls dono
    me dikhe. Strict-validated + size-capped + per-IP rate-limited (public surface).
    Never raises — failure pe {ok:false} (transcript abhi bhi safe hai).
    """
    # Per-IP abuse guard (FAIL-OPEN).
    if _REC_LIMITER is not None:
        try:
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else "unknown"
            )
            allowed, _ = await _REC_LIMITER.is_allowed(ip)
            if not allowed:
                return {"ok": False, "error": "rate_limited"}
        except Exception:
            pass

    sid = _normalize_session_id_safe(session_id)
    if not sid:
        return {"ok": False, "error": "bad_session_id"}

    try:
        blob = await file.read(_REC_MAX_BYTES + 1)
    except Exception:
        return {"ok": False, "error": "read_failed"}
    if not blob:
        return {"ok": False, "error": "empty"}
    if len(blob) > _REC_MAX_BYTES:
        return {"ok": False, "error": "too_large"}
    if len(blob) < 2000:  # < ~2KB = silence/no real audio
        return {"ok": False, "error": "too_small"}

    # Date dir = session's started_at (admin viewer isi se URL banata). PUBLIC
    # surface hardening: recording sirf ek REAL persisted session ke liye save hoti
    # (WS 'end' pe persist hota, upload uske baad) — random sid = disk-fill abuse block.
    day = _now_iso()[:10]
    try:
        from app.voice_agent.web_call_store import get_session_any

        row = get_session_any(sid)
    except Exception:
        row = None
    if not row:
        return {"ok": False, "error": "unknown_session"}
    if str(row.get("started_at") or "")[:10]:
        day = str(row["started_at"])[:10]

    try:
        ext = _rec_ext(blob)
        rec_dir = os.path.join(_CALL_RECORDINGS_DIR(), day)
        out = os.path.join(rec_dir, f"webcall_{sid}.{ext}")
        await asyncio.to_thread(_write_recording_sync, rec_dir, out, blob)
        return {"ok": True, "date": day, "file": f"webcall_{sid}.{ext}", "bytes": len(blob)}
    except Exception as e:
        logger.debug(f"web-call: recording save failed ({e}).")
        return {"ok": False, "error": "save_failed"}


def _normalize_session_id_safe(session_id: str | None) -> str | None:
    try:
        from app.voice_agent.web_call_store import normalize_session_id

        return normalize_session_id(session_id)
    except Exception:
        s = (session_id or "").strip()
        return s if 8 <= len(s) <= 64 and s.replace("-", "").replace("_", "").isalnum() else None


# ---------------------------------------------------------------------------- #
# WebSocket — browser chat with the bot
# ---------------------------------------------------------------------------- #
@router.websocket("/ws")
async def web_call_ws(websocket: WebSocket) -> None:
    """
    Browser test session. The browser sends user text (or audio chunks); the
    server runs the VoicePipeline (or LLM/echo fallback) and streams back bot
    replies. Clearly flagged as TEST MODE — no real phone call.
    """
    # Per-IP abuse guard (free LLM/STT cost) — reject over-cap before accept.
    if _WS_LIMITER is not None:
        try:
            _allowed, _ = await _WS_LIMITER.is_allowed(_ws_client_ip(websocket))
        except Exception:
            _allowed = True
        if not _allowed:
            await websocket.close(code=1013)  # Try Again Later
            return
    await websocket.accept()

    lead_from_qs = _normalize_lead_key(websocket.query_params.get("lead_key"))

    # Per-session conversation context. Defaults until the client tells us the
    # niche/flow (via 'start' or the first 'user' message).
    session: dict[str, Any] = {
        "niche": "ai_marketing",
        "flow": "qualify",
        "client_name": "Demo Co",
        "client_service": "",
        "lead_key": lead_from_qs,
        "session_id": str(uuid4()),
        "started_at": _now_iso(),
        "turns": [],
        "saved": False,
        "memory_subject": None,
    }

    # PRIMARY responder: the human-like NaturalDialogManager. It LISTENS,
    # understands, answers the customer's question, and keeps replies short —
    # the whole point of this fix. Built lazily once we know the niche; rebuilt
    # (with a fresh conversation) if the niche changes mid-session.
    dialog: Any = None
    dstate: Any = None
    dialog_niche: str | None = None

    # Fallbacks (used ONLY if the natural-dialog brain can't be built).
    pipeline = _get_pipeline()
    if _pipeline_text_method(pipeline) is None:
        pipeline = None
    brain: Any = None
    history: list = []

    def _ensure_dialog() -> None:
        """(Re)build the per-session dialog manager when the niche changes."""
        nonlocal dialog, dstate, dialog_niche
        niche = session.get("niche", "general")
        if dialog is not None and dialog_niche == niche:
            return
        mgr = _get_natural_dialog(
            niche,
            session.get("client_name", "Demo Co"),
            session.get("client_service", ""),
        )
        if mgr is not None:
            dialog = mgr
            dstate = mgr.new_conversation()
            dialog_niche = niche

    def _get_tcbrain(niche: str) -> Any | None:
        """
        Lazy, per-session TelecallerBrain — niche + voice_role (flow) aware.
        Cached so each (niche, role) builds once; failed build cached as None.
        """
        niche = niche or "general"
        flow = session.get("flow", "qualify")
        cache_key = f"{niche}:{flow}"
        cache = session.setdefault("tcbrains", {})
        if cache_key in cache:
            return cache[cache_key]
        tcb = None
        try:
            from app.voice_agent.telecaller_brain import TelecallerBrain  # type: ignore
            from app.voice_agent.voice_roles import normalize_role

            tcb = TelecallerBrain(
                niche=niche,
                client_name=session.get("client_name", "Demo Co"),
                voice_role=normalize_role(flow),
            )
            _apply_memory_subject(tcb, session)
        except Exception as e:
            logger.debug(f"web-call: TelecallerBrain unavailable for '{niche}' ({e}).")
            tcb = None
        cache[cache_key] = tcb
        return tcb

    # Decide the responder WITHOUT eagerly building the NaturalDialog manager.
    # Its FIRST (cold) build is ~23s (embedder/KB load) and it is only a FALLBACK
    # used when TelecallerBrain is unavailable. Building it here blocked the WS
    # `ready` ~23s on every fresh session, so the greeting/first reply felt dead.
    # TelecallerBrain is the primary path; the dialog is built lazily at its
    # fallback use-sites (_ensure_dialog is idempotent). Priority order unchanged:
    # telecaller > natural > pipeline > llm > echo.
    if await _run_blocking(_get_tcbrain, session.get("niche", "general")) is not None:
        responder = "telecaller"
    else:
        await _run_blocking(_ensure_dialog)  # only now pay the cold dialog build
        if dialog is not None:
            responder = "natural"
        elif pipeline is not None:
            responder = "pipeline"
        else:
            brain = _get_llm_brain()
            responder = "llm" if brain is not None else "echo"

    try:
        await websocket.send_json(
            {
                "type": "ready",
                "test_mode": True,
                "responder": responder,
                "voice_role": session.get("flow", "qualify"),
                "pipeline": pipeline is not None,
                "providers": _get_registry_describe() or {},
                "note": "TEST MODE — no real call. Say hello to talk to the bot.",
                **_memory_meta(session),
            }
        )
    except Exception:
        return

    # Pre-warm the realtime LLM chain in the background so the caller's FIRST
    # reply isn't a 10-13s cold-start (provider TLS + model cold). Fire-and-forget;
    # failure is harmless (first reply just pays the cold cost as before). The ref
    # is held in the session so the task isn't GC'd mid-flight. Kill: WEBCALL_LLM_WARMUP=0.
    if os.environ.get("WEBCALL_LLM_WARMUP", "1").strip().lower() not in ("0", "false", "no", "off"):

        async def _warm_llm() -> None:
            try:
                from app.voice_agent import free_ai

                await free_ai.chat(
                    system="",
                    messages=[{"role": "user", "content": "hi"}],
                    max_tokens=1,
                    profile="realtime",
                    scope="webcall_warm",
                )
            except Exception:
                pass

        try:
            session["_warm_task"] = asyncio.create_task(_warm_llm())
        except Exception:
            pass

    # Abuse cap (audit 2026-07-04): the per-IP limiter only throttles NEW
    # connections — one open socket could pump unlimited turns through the
    # free LLM/STT chain. One message ≈ one turn (audio arrives as a single
    # base64 blob per utterance), so 300 is generous for any real demo.
    try:
        _max_msgs = int(os.environ.get("WEBCALL_MAX_MSGS", "300") or 300)
    except Exception:
        _max_msgs = 300
    _msg_count = 0

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                logger.info("web-call: client disconnected.")
                break
            except Exception as e:
                # Non-JSON or transport hiccup — inform and continue.
                logger.debug(f"web-call: bad inbound message ({e}).")
                try:
                    await websocket.send_json(
                        {"type": "error", "text": "Invalid message (expected JSON)."}
                    )
                except Exception:
                    break
                continue

            if not isinstance(data, dict):
                continue

            mtype = data.get("type", "user")

            if mtype not in ("ping", "end"):
                _msg_count += 1
                if _msg_count > _max_msgs:
                    logger.warning(
                        "web-call: session message cap (%d) reached — closing.", _max_msgs
                    )
                    _persist_session(session)
                    try:
                        await websocket.send_json(
                            {
                                "type": "error",
                                "text": "Test session limit ho gayi — nayi session shuru karein.",
                            }
                        )
                    except Exception:
                        pass
                    break

            # Update session context from any message that carries it.
            if data.get("niche"):
                session["niche"] = str(data["niche"])
            if data.get("flow"):
                session["flow"] = str(data["flow"])
            if data.get("voice_role"):
                session["flow"] = str(data["voice_role"])
            # Business identity — agent ISI naam se baat karta hai (default
            # "Demo Co" tha jo demo-jaisa lagta tha). Change par cached brains
            # invalid: fresh build naye client_name ke saath hota hai.
            if data.get("client_name") and str(data["client_name"]).strip():
                _new_name = str(data["client_name"]).strip()[:80]
                if _new_name != session.get("client_name"):
                    session["client_name"] = _new_name
                    session["tcbrains"] = {}
                    dialog = None
            if data.get("client_service") and str(data["client_service"]).strip():
                session["client_service"] = str(data["client_service"]).strip()[:120]
            if data.get("lead_key"):
                lk = _normalize_lead_key(str(data.get("lead_key")))
                if lk and lk != session.get("lead_key"):
                    session["lead_key"] = lk
                    session["tcbrains"] = {}
            if data.get("session_id"):
                try:
                    from app.voice_agent.web_call_store import normalize_session_id

                    sid = normalize_session_id(str(data.get("session_id")))
                    if sid:
                        session["session_id"] = sid
                except Exception:
                    pass

            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if mtype == "end":
                _persist_session(session)
                try:
                    await websocket.send_json(
                        {
                            "type": "session_saved",
                            "session_id": session.get("session_id"),
                            "turn_count": len(session.get("turns") or []),
                        }
                    )
                except Exception:
                    pass
                break

            if mtype == "start":
                session["started_at"] = _now_iso()
                session["turns"] = []
                session["saved"] = False
                try:  # Team activity: voice agent web-demo session
                    from app.platform.team import log_event
                    from app.voice_agent.voice_roles import staff_for_role

                    staff_id = staff_for_role(session.get("flow", "qualify"))
                    log_event(
                        staff_id,
                        "web_demo",
                        f"Web-call demo started (niche: {session.get('niche', 'general')}, "
                        f"role: {session.get('flow', 'qualify')})",
                    )
                except Exception:
                    pass
                # Fresh conversation for the chosen niche + a natural opening
                # line so the bot greets FIRST (proves it's alive and human).
                dialog = None  # force rebuild with fresh state
                history = []
                session.pop("pitch_state", None)

                niche = session.get("niche", "general")
                # Platform pitch (ai_marketing): 3-segment opener — phone parity.
                try:
                    from app.voice_agent.platform_pitch import (
                        initial_state,
                        is_platform_pitch,
                        opening_segments,
                    )

                    if is_platform_pitch(niche):
                        session["pitch_state"] = {
                            "phase": initial_state().phase,
                            "convinced_once": False,
                        }
                        if niche == "ai_marketing":
                            session["client_name"] = "LeadGen AI"
                        segs = opening_segments()
                        # The three-part platform opener is static text. Synthesize
                        # all segments concurrently, then send them in order. The
                        # old serial path made the browser wait for 3 EdgeTTS
                        # round-trips before the opening felt complete.
                        audio_tasks = [asyncio.create_task(_bot_audio_b64(seg)) for seg in segs]
                        audio_results = await asyncio.gather(*audio_tasks, return_exceptions=True)
                        for i, seg in enumerate(segs):
                            history.append({"role": "assistant", "content": seg})
                            _log_turn(session, "assistant", seg)
                            extra: dict[str, Any] = {}
                            if len(segs) > 1:
                                extra["chunk_index"] = i
                                extra["chunk_total"] = len(segs)
                            audio = audio_results[i]
                            extra["audio_b64"] = audio if isinstance(audio, str) else None
                            await _send_bot_message(websocket, seg, **extra)
                        try:
                            await websocket.send_json(
                                {
                                    "type": "session",
                                    **_memory_meta(session),
                                    "recall_note": (
                                        "Isi browser pe pehli calls yaad rahengi — "
                                        "AGENT_MEMORY ON ho to Swara recall karegi."
                                    ),
                                }
                            )
                        except Exception:
                            pass
                        continue
                except Exception as e:
                    logger.debug(f"web-call: platform pitch start skip ({e}).")

                # PRIMARY: professional TelecallerBrain opener (same as the phone
                # agent), spoken in the natural Swara voice (EdgeTTS mp3 b64).
                tcbrain = await _run_blocking(_get_tcbrain, niche)
                if tcbrain is not None:
                    try:
                        opening = (tcbrain.opening_line() or "").strip()
                    except Exception:
                        opening = ""
                    if not opening:
                        opening = _script_opening(niche, session.get("client_name", "Demo Co"))
                    if opening:
                        # D-14/D-9 web-call parity: even the browser demo opener must
                        # disclose it is an AI (TRAI good-practice) + ask permission —
                        # phone wraps these; web-call did not. Idempotent + never-raise.
                        try:
                            from app.voice_agent.niche_scripts import (
                                ensure_ai_disclosure,
                                ensure_permission_ask,
                            )

                            opening = ensure_permission_ask(ensure_ai_disclosure(opening))
                        except Exception:
                            pass
                        history.append({"role": "assistant", "content": opening})
                        _log_turn(session, "assistant", opening)
                        await _send_bot_message(
                            websocket,
                            opening,
                        )
                        try:
                            await websocket.send_json({"type": "session", **_memory_meta(session)})
                        except Exception:
                            pass
                        continue

                # FALLBACK: natural-dialog opening (browser TTS), then info.
                await _run_blocking(_ensure_dialog)
                if dialog is not None and dstate is not None:
                    try:
                        opening = await dialog.opening_line(dstate)
                        await websocket.send_json(
                            {
                                "type": "bot",
                                "text": opening,
                                "audio_b64": None,
                                "test_mode": True,
                            }
                        )
                        continue
                    except Exception as e:
                        logger.debug(f"web-call: opening line skipped ({e}).")
                await websocket.send_json(
                    {
                        "type": "info",
                        "text": f"TEST MODE started — niche='{session['niche']}', flow='{session['flow']}'.",
                    }
                )
                continue

            # Per-turn latency clock — message-arrival se bot-bolna-shuru tak ka
            # PERCEIVED gap. Stages alag-alag bhi measure hote (stt/llm/tts) taaki
            # admin viewer me dikhe "kahan time gaya" + loop ko objective target mile.
            _t_recv = time.monotonic()
            _turn_timing: dict[str, Any] = {}

            # Extract user text. Audio (jab client ne bheja ho) PEHLE server
            # STT se transcribe hota hai — Groq whisper-large-v3 Hinglish me
            # browser Web Speech API se kahin behtar sunta hai (phone-parity).
            # STT fail/empty par browser ka text fallback hai (zero regression).
            browser_text = (data.get("text") or "").strip()
            user_text = ""
            stt_text = ""
            if data.get("audio_b64"):
                _t_stt = time.monotonic()
                stt_text = await _transcribe_audio(
                    pipeline, brain, data.get("audio_b64"), niche=session.get("niche", "")
                )
                _turn_timing["stt_ms"] = int((time.monotonic() - _t_stt) * 1000)
                # STT-source diagnostic (next-iteration decision: kya browser-text —
                # 0ms, free — Groq jitna accurate hai? Sirf divergence pe log = low noise).
                if (
                    browser_text
                    and stt_text
                    and stt_text.strip().lower() != browser_text.strip().lower()
                ):
                    logger.info(
                        f"[web-call STT compare] groq={stt_text[:80]!r} browser={browser_text[:80]!r} "
                        f"stt_ms={_turn_timing.get('stt_ms')}"
                    )
            user_text = stt_text or browser_text
            # Post-STT Hinglish correction (smart-fix Component 1b) — fix high-confidence
            # mis-hears on the FINAL user text (server-STT or browser fallback) before it
            # reaches the NLU gates + the LLM. Gated STT_CORRECT (default ON); fail-open.
            if user_text:
                try:
                    from app.voice_agent.hinglish_stt_fix import correct_stt as _correct_stt

                    user_text = _correct_stt(user_text, session.get("niche", "") or "")
                except Exception:
                    pass

            if not user_text:
                await websocket.send_json(
                    {"type": "error", "text": "Empty message — nothing to process."}
                )
                continue

            _log_turn(session, "user", user_text)
            history = _history_from_session(session, exclude_last_user=user_text)

            # POLITE-NO 2-strike de-escalation (orchestration guard — fires BEFORE
            # the pitch_state gate AND the brain). India-critical trust rule: a 2nd
            # soft refusal => stop pitching, graceful async-exit. telecaller_brain.reply()
            # already enforces this, but the pitch_state interest-gate below can answer
            # the turn first (a discovery question = "pushy after soft-no") and bypass
            # the brain entirely — so enforce the rule here, where every path converges.
            # Gated SOFTNO_DEESCALATE (default ON, checked inside should_deescalate);
            # deterministic (no LLM); fail-open (any error => normal flow continues).
            try:
                from app.voice_agent import intent_softno as _softno

                if _softno.should_deescalate(history, user_text):
                    _deesc = _softno.deescalation_reply(
                        session.get("niche", "") or "",
                        str(session.get("client_name", "") or ""),
                        history,
                        user_text,
                    )
                    if _deesc:
                        history.append({"role": "user", "content": user_text})
                        history.append({"role": "assistant", "content": _deesc})
                        _log_turn(session, "assistant", _deesc)
                        await _send_bot_message(websocket, _deesc, heard=user_text)
                        continue
            except Exception as e:
                logger.debug(f"web-call: softno de-escalation skip ({e}).")

            pitch_raw = session.get("pitch_state")
            if pitch_raw:
                try:
                    from app.voice_agent.platform_pitch import PlatformPitchState, next_reply

                    pst = PlatformPitchState(
                        phase=str(pitch_raw.get("phase") or "await_interest"),
                        convinced_once=bool(pitch_raw.get("convinced_once")),
                        clarify_count=int(pitch_raw.get("clarify_count") or 0),
                    )
                    gate_reply, pst = next_reply(pst, user_text)
                    session["pitch_state"] = {
                        "phase": pst.phase,
                        "convinced_once": pst.convinced_once,
                        "clarify_count": pst.clarify_count,
                    }
                    tcbrain = await _run_blocking(_get_tcbrain, session.get("niche", "general"))
                    if pst.phase == "discovery":
                        _pitch_discovery_handoff(session, tcbrain, pst)
                    if gate_reply:
                        history.append({"role": "user", "content": user_text})
                        history.append({"role": "assistant", "content": gate_reply})
                        _log_turn(session, "assistant", gate_reply)
                        await _send_bot_message(
                            websocket,
                            gate_reply,
                            heard=user_text,
                            should_end=pst.phase == "closed",
                        )
                        continue
                except Exception as e:
                    logger.debug(f"web-call: platform pitch gate skip ({e}).")

            history = _history_from_session(session, exclude_last_user=user_text)

            # PRIMARY: professional TelecallerBrain (the SAME brain as the phone
            # agent — researched niche scripts + free_ai/Gemini, KB-grounded),
            # spoken in the natural Swara voice (EdgeTTS mp3 b64). On empty/fail
            # we drop through to the existing natural-dialog/_respond chain.
            tcbrain = await _run_blocking(_get_tcbrain, session.get("niche", "general"))
            if tcbrain is not None:
                # VOICE_TOOLS (agentic in-call actions) — PARITY with the phone path.
                # Gated VOICE_TOOLS=1 (default OFF = skip entirely). When on, the brain
                # may take an action (book/capture/transfer/end) instead of just
                # talking; we speak the confirmation and end the turn. Uses the SAME
                # shared run_tool_turn as vobiz, so the agentic behaviour matches.
                try:
                    from app.voice_agent.voice_tools import (
                        build_registry_for,
                        run_tool_turn,
                        voice_tools_enabled,
                    )

                    # Sirf BOOKING-intent turns tool-path pe (real slot/persist) — baaki
                    # sab normal instrumented + streamed reply pe (P1 answer-first intact).
                    if voice_tools_enabled() and _is_booking_intent(user_text):
                        _reg = build_registry_for(
                            niche=session.get("niche", "general"),
                            client_id=session.get("client_id"),
                            lead_phone=str(session.get("lead_key") or ""),
                            history=history,
                        )
                        _decision = await run_tool_turn(tcbrain, history, user_text, _reg)
                        if _decision.get("spoken"):
                            tc_reply = _decision["spoken"]
                            _log_turn(
                                session,
                                "assistant",
                                tc_reply,
                                meta=_turn_meta(_turn_timing, _t_recv, user_text),
                            )
                            await _send_bot_message(
                                websocket,
                                tc_reply,
                                heard=user_text,
                                should_end=bool(_decision.get("should_end")),
                            )
                            continue
                except Exception as e:
                    logger.debug(f"web-call: voice-tools path skip ({e}).")

                # FILLER — sirf mic/audio turns pe; text test-call pe EdgeTTS filler
                # 6s block karta hai → WS tester timeout / dead air.
                if data.get("audio_b64"):
                    try:
                        filler_audio = await _filler_b64()
                        await websocket.send_json(
                            {
                                "type": "filler",
                                "audio_b64": filler_audio,
                                "heard": user_text,
                                "test_mode": True,
                            }
                        )
                    except Exception:
                        pass  # filler fail = ignore, LLM reply abhi bhi aayega

                tc_reply = ""
                # Web-call TEST MODE = text-first; LLM stream+TTS phone ke liye hai.
                # USE_LLM_STREAM_TTS=1 pe stream path fast_path skip + 14s hang (tune loop).
                use_llm_stream = False

                async def _brain_turn(
                    _history=history,
                    _user_text=user_text,
                    _tcbrain=tcbrain,
                    _use_stream=use_llm_stream,
                    _turn_timing=_turn_timing,
                    _websocket=websocket,
                ) -> str:
                    nonlocal tc_reply
                    if _use_stream:
                        return await _brain_turn_stream()
                    _t_llm = time.monotonic()
                    try:
                        tc_reply = await _tcbrain.reply(_history, _user_text)
                    except Exception as e:
                        tc_reply = ""
                        logger.warning(
                            f"web-call: TelecallerBrain reply failed, using fallback: {e}"
                        )
                    _turn_timing["llm_ms"] = int((time.monotonic() - _t_llm) * 1000)
                    if tc_reply:
                        _t_tts = time.monotonic()
                        await _send_tcbrain_sentence_chunks(
                            _websocket,
                            sentences=_split_sentences(tc_reply),
                            user_text=_user_text,
                            full_reply=tc_reply,
                            llm_stream=False,
                            timing=_turn_timing,
                        )
                        _turn_timing["tts_ms"] = int((time.monotonic() - _t_tts) * 1000)
                    signal_payload = _close_signal_payload(_tcbrain)
                    if signal_payload:
                        try:
                            await _websocket.send_json(signal_payload)
                        except Exception:
                            pass
                    return tc_reply

                async def _brain_turn_stream(
                    _websocket=websocket,
                    _history=history,
                    _user_text=user_text,
                    _tcbrain=tcbrain,
                    _turn_timing=_turn_timing,
                ) -> str:
                    nonlocal tc_reply
                    streamed: list[str] = []
                    try:
                        async for sentence in _tcbrain.reply_stream_sentences(_history, _user_text):
                            streamed.append(sentence)
                            await _send_tcbrain_sentence_chunks(
                                _websocket,
                                sentences=[sentence],
                                user_text=_user_text,
                                full_reply=" ".join(streamed).strip(),
                                llm_stream=True,
                                timing=_turn_timing,
                            )
                        tc_reply = " ".join(streamed).strip()
                    except Exception as e:
                        tc_reply = ""
                        logger.warning(
                            f"web-call: TelecallerBrain stream reply failed, using fallback: {e}"
                        )
                    return tc_reply

                try:
                    tc_reply = await asyncio.wait_for(_brain_turn(), timeout=18.0)
                except asyncio.TimeoutError:
                    tc_reply = ""
                    logger.warning("web-call: TelecallerBrain turn timed out (18s)")
                if not tc_reply:
                    try:
                        tc_reply = tcbrain._safe_fallback(history) or ""
                    except Exception:
                        tc_reply = ""
                    if tc_reply:
                        await _send_tcbrain_sentence_chunks(
                            websocket,
                            sentences=[tc_reply],
                            user_text=user_text,
                            full_reply=tc_reply,
                            llm_stream=False,
                            timing=_turn_timing,
                        )

                if tc_reply:
                    _log_turn(
                        session,
                        "assistant",
                        tc_reply,
                        meta=_turn_meta(_turn_timing, _t_recv, user_text),
                    )
                    continue

                # Never hang — customer ko hamesha kuch sunai de. (No "ji/sir"
                # habit-address filler — 2026-07-17 owner live-call feedback.)
                tc_reply = "Sun rahi hoon — thoda detail me bataye?"
                _log_turn(
                    session,
                    "assistant",
                    tc_reply,
                    meta=_turn_meta(_turn_timing, _t_recv, user_text),
                )
                await _send_bot_message(websocket, tc_reply, heard=user_text)
                continue

            # FALLBACK: human-like natural dialog (listen -> understand -> answer).
            await _run_blocking(_ensure_dialog)
            if dialog is not None and dstate is not None:
                try:
                    reply = await dialog.respond(user_text, dstate)
                    _log_turn(session, "assistant", reply.text)
                    await websocket.send_json(
                        {
                            "type": "bot",
                            "text": reply.text,
                            "audio_b64": None,  # browser TTS speaks it
                            "heard": user_text,
                            "test_mode": True,
                            "should_end": bool(getattr(reply, "should_end", False)),
                        }
                    )
                    continue
                except Exception as e:
                    logger.warning(f"web-call: natural dialog failed, using fallback: {e}")

            # FALLBACK: pipeline -> llm -> echo (only if natural dialog absent).
            history.append({"role": "user", "content": user_text})
            bot_text, audio_b64 = await _respond(pipeline, brain, history, session, user_text)
            history.append({"role": "assistant", "content": bot_text})
            _log_turn(session, "assistant", bot_text)
            await websocket.send_json(
                {
                    "type": "bot",
                    "text": bot_text,
                    "audio_b64": audio_b64,  # may be None — browser will use its own TTS/none
                    "heard": user_text,
                    "test_mode": True,
                }
            )
    except Exception as e:
        logger.error(f"web-call ws fatal (handled): {e}")
        try:
            await websocket.send_json({"type": "error", "text": "Server error — session ended."})
        except Exception:
            pass
    finally:
        _persist_session(session)
        try:
            if session.get("saved") and len(session.get("turns") or []) >= 4:
                from app.voice_agent.web_call_learn import analyze_web_session

                asyncio.create_task(analyze_web_session(dict(session)))
        except Exception:
            pass


# ---------------------------------------------------------------------------- #
# Responder helpers
# ---------------------------------------------------------------------------- #
def _sniff_audio_format(audio: bytes) -> tuple[str, str]:
    """Magic-bytes se (filename, mime) — MediaRecorder webm/opus default hai;
    Groq whisper extension/mime se format pehchanta hai."""
    if audio[:4] == b"\x1aE\xdf\xa3":
        return "audio.webm", "audio/webm"
    if audio[:4] == b"OggS":
        return "audio.ogg", "audio/ogg"
    if audio[:4] == b"RIFF":
        return "audio.wav", "audio/wav"
    if audio[:3] == b"ID3" or audio[:2] in (b"\xff\xfb", b"\xff\xf3"):
        return "audio.mp3", "audio/mpeg"
    if len(audio) > 8 and audio[4:8] == b"ftyp":
        return "audio.mp4", "audio/mp4"
    return "audio.webm", "audio/webm"


async def _local_whisper_transcribe(audio: bytes) -> str:
    """
    FREE self-host local STT fallback (Sarvam-Saaras ka alternative) — gated by
    HINGLISH_STT=1. Jab cloud STT (Groq/Gemini) down/quota'd ho, browser-text pe
    girne se pehle local Hinglish-finetuned Whisper (ya whisper-base) try karta
    hai → web-call kabhi deaf nahi. Phone path ka WAHI cached model reuse karta
    (vobiz_stream._get_stt) — koi extra memory nahi. Browser ka compressed audio
    (webm/ogg/wav) faster-whisper khud PyAV se decode+resample karta hai.

    Bounded + defensive: timeout / koi bhi error pe '' (caller fall-through).
    """
    if (os.environ.get("HINGLISH_STT", "0") or "0").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return ""

    def _run() -> str:
        try:
            from app.telephony import vobiz_stream as _vs  # type: ignore

            engine = _vs._get_stt()
            if not engine or engine[0] != "whisper":
                return ""
            import io as _io

            model = engine[1]
            lang = os.environ.get("FWHISPER_LANG", "hi")
            prompt = os.environ.get(
                "FWHISPER_PROMPT",
                "Hinglish sales call: solar, real estate, insurance, leads, business, appointment.",
            )
            segments, _ = model.transcribe(
                _io.BytesIO(audio),
                beam_size=1,
                language=lang,
                vad_filter=True,
                condition_on_previous_text=False,
                initial_prompt=(prompt or None),
            )
            return " ".join(seg.text for seg in segments).strip()
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"web-call: local whisper STT failed ({e}).")
            return ""

    try:
        timeout = float(os.environ.get("WEBCALL_LOCAL_STT_TIMEOUT_S", "12"))
        return await asyncio.wait_for(asyncio.to_thread(_run), timeout=timeout)
    except Exception:
        return ""


async def _transcribe_audio(
    pipeline: Any, brain: Any, audio_b64: str, niche: str = "", client_name: str = ""
) -> str:
    """
    Server-side STT. PRIMARY: free_ai Groq whisper-large-v3 (wahi chain jo
    phone agent use karta hai — Hinglish-strong). Fallback: local Hinglish
    whisper (HINGLISH_STT=1), phir pipeline transcribe method. '' return =
    caller browser-provided text use karega. Never raises.

    WEBCALL_STT_LOCAL_FIRST=1 (+ HINGLISH_STT=1) = local Hinglish model ko
    PRIMARY banao (cloud skip jab tak local '' na de) — zero-cloud / verify mode.
    """
    import base64

    try:
        audio = base64.b64decode(audio_b64)
    except Exception:
        return ""
    if not audio or len(audio) > 4_000_000:  # >4MB = kuch galat hai, skip
        return ""

    # PRO STT = Sarvam Saaras v3 (India-native, Hinglish code-switching, 25k hrs Indian
    # audio) — tried FIRST when STT_PROVIDER=sarvam + SARVAM_API_KEY. Real-call Hinglish
    # accuracy >> Groq/Whisper (no Devanagari-garble, no CPU-whisper slowness). INERT
    # without key (paid ~Rs2/min) → falls through to the free Groq path below.
    if (
        os.environ.get("STT_PROVIDER", "").strip().lower() == "sarvam"
        and os.environ.get("SARVAM_API_KEY", "").strip()
    ):
        try:
            from app.voice_agent.indic_providers import SarvamSTT

            _sx = await asyncio.wait_for(
                SarvamSTT().transcribe(audio, language=os.environ.get("DEFAULT_LANGUAGE", "hi-IN")),
                timeout=12.0,
            )
            if (_sx or "").strip():
                return _sx.strip()
        except Exception as e:
            logger.debug(f"web-call: Sarvam STT skip ({e}).")

    # SELF-HOSTED STT (AI4Bharat IndicConformer on your own GPU) — FREE, no per-min.
    # Tried when STT_PROVIDER=ai4bharat + AI4BHARAT_ENDPOINT (your voice_stack server).
    # INERT without the endpoint → free Groq path below. (voice_stack/README.md)
    if (
        os.environ.get("STT_PROVIDER", "").strip().lower() == "ai4bharat"
        and os.environ.get("AI4BHARAT_ENDPOINT", "").strip()
    ):
        try:
            from app.voice_agent.indic_providers import Ai4BharatSTT

            _ax = await asyncio.wait_for(
                Ai4BharatSTT().transcribe(
                    audio, language=os.environ.get("DEFAULT_LANGUAGE", "hi-IN")
                ),
                timeout=12.0,
            )
            if (_ax or "").strip():
                return _ax.strip()
        except Exception as e:
            logger.debug(f"web-call: AI4Bharat STT skip ({e}).")

    # 0) FORCE local Hinglish whisper FIRST (WEBCALL_STT_LOCAL_FIRST=1 + HINGLISH_STT=1)
    # — zero-cloud / verification mode: har web-call baked Hinglish model use kare
    # (roman output + latency judge karne ke liye). Khali return = cloud pe gir jao.
    # Default OFF = cloud-primary (latency-safe) behaviour unchanged.
    if (os.environ.get("WEBCALL_STT_LOCAL_FIRST", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        text = await _local_whisper_transcribe(audio)
        if text:
            return text

    # 1) Groq whisper-large-v3 via free_ai (phone-parity, GROQ_API_KEY needed).
    try:
        from app.voice_agent import free_ai  # type: ignore

        filename, mime = _sniff_audio_format(audio)
        # STT bias (D-11) — phone path passes this; web path was missing it, so
        # proper nouns + Hinglish register weren't biased. Parity fix.
        try:
            from app.voice_agent.niche_scripts import stt_keyterms

            _bias = stt_keyterms(
                niche or (getattr(brain, "niche", "") or ""),
                client_name or (getattr(brain, "client_name", "") or ""),
            )
        except Exception:
            _bias = ""
        text, _provider = await free_ai.transcribe_audio(
            audio, language="hi", filename=filename, mime=mime, prompt=_bias
        )
        if (text or "").strip():
            return text.strip()
    except Exception as e:
        logger.debug(f"web-call: free_ai STT failed ({e}).")

    # 1b) FREE self-host local Hinglish whisper (HINGLISH_STT=1) — cloud STT
    # down/quota'd hone par bhi web-call deaf na ho. Phone path ka same model.
    text = await _local_whisper_transcribe(audio)
    if text:
        return text

    # 2) Pipeline transcribe method (rarely present).
    for obj in (pipeline,):
        for name in ("transcribe", "stt", "speech_to_text"):
            fn = getattr(obj, name, None) if obj else None
            if callable(fn):
                try:
                    return (await _maybe_await(fn(audio))) or ""
                except Exception:
                    pass
    # No server-side STT available — caller falls back to the browser text.
    return ""


async def _respond(pipeline, brain, history, session, user_text):
    """
    Produce (bot_text, audio_b64) via the best available responder.
    Order: VoicePipeline -> LLMBrain -> echo. Never raises.
    """
    # 1) Full pipeline (preferred).
    fn = _pipeline_text_method(pipeline)
    if fn is not None:
        try:
            result = await _maybe_await(fn(user_text))
            return _unpack_pipeline_result(result)
        except Exception as e:
            logger.warning(f"web-call pipeline responder failed, trying LLM brain: {e}")

    # 2) LLM brain fallback (load lazily if the pipeline just failed).
    if brain is None:
        brain = _get_llm_brain()
    if brain is not None:
        fn = getattr(brain, "generate_response", None)
        if callable(fn):
            try:
                text = await _maybe_await(
                    fn(
                        conversation_history=history,
                        niche=session.get("niche", "general"),
                        client_name=session.get("client_name", "Demo Co"),
                        client_service=session.get("niche", "our service"),
                    )
                )
                if text:
                    # COMPLIANCE PARITY (2026-07-05): LLMBrain fallback ko bhi
                    # post-output safety+PII-redact se guzaaro (web↔vobiz parity —
                    # pipeline/TelecallerBrain path already guarded). Never-raise.
                    safe = str(text)
                    try:
                        from app.voice_agent.guardrails import get_guardrails

                        gout = get_guardrails().check_output(safe)
                        safe = gout.text or safe
                    except Exception:
                        pass
                    return safe, None
                logger.warning("web-call llm responder returned empty text — falling back to echo.")
            except Exception as e:
                logger.warning(
                    f"web-call llm responder failed — falling back to echo: {type(e).__name__}: {e}"
                )

    # 3) Echo fallback (always works).
    return (
        f'[echo / test-mode] You said: "{user_text}". '
        f"(No live LLM configured — this is a placeholder reply.)",
        None,
    )


def _unpack_pipeline_result(result: Any):
    """Normalize a pipeline result into (text, audio_b64)."""
    if result is None:
        return "(no response)", None
    if isinstance(result, str):
        return result, None
    if isinstance(result, dict):
        return result.get("text") or result.get("reply") or "(no response)", result.get("audio_b64")
    if isinstance(result, tuple | list) and result:
        text = str(result[0])
        audio = result[1] if len(result) > 1 else None
        return text, audio
    return str(result), None
