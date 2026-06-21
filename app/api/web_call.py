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
    {"type": "pong"}

Import-safe: degrades gracefully if the VoicePipeline or providers are missing —
falls back to a simple LLM responder, and if even that is unavailable, an echo.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import asyncio

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

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


def _log_turn(session: dict[str, Any], role: str, text: str) -> None:
    t = (text or "").strip()
    if not t:
        return
    turns = session.setdefault("turns", [])
    turns.append({"ts": _now_iso(), "role": role, "text": t[:2000]})


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

_FILLER_LINES = ["Hmm...", "Achha...", "Ji...", "Haan..."]
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
        # Very short fragment (<= 8 chars) — append to previous sentence
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
) -> None:
    """EdgeTTS + WS JSON for one or more spoken sentences (import-safe).

    TEXT FIRST: pehle turant text bhejo (audio_b64=None) taaki test-call / WS
    tester 14s TTS wait pe hang na ho; browser speechSynthesis fallback instant.
    Edge TTS optional background (WEB_CALL_EDGE_TTS=1) — quality mode, non-blocking.
    """
    import os

    use_edge = os.environ.get("WEB_CALL_EDGE_TTS", "0").strip().lower() in ("1", "true", "yes")
    total = len(sentences)
    for i, sentence in enumerate(sentences):
        payload: dict[str, Any] = {
            "type": "bot",
            "text": sentence,
            "audio_b64": None,
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
        if use_edge and sentence.strip():
            async def _bg_tts(txt: str = sentence) -> None:
                try:
                    await _edge_tts_mp3_b64(txt)
                except Exception:
                    pass

            asyncio.create_task(_bg_tts())


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

    async def _synth() -> str | None:
        try:
            import edge_tts  # type: ignore
        except Exception:
            return None
        try:
            try:
                comm = edge_tts.Communicate(text, "hi-IN-SwaraNeural", rate="+8%")
            except TypeError:
                # edge-tts build without the `rate` kwarg — synth at default rate.
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
    return (
        f"Namaste! Main Swara bol rahi hoon {client_name or 'hamari company'} ki taraf se — "
        "bas ek minute baat kar sakti hoon?"
    )


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

    return {
        "test_mode": True,
        "note": "Web Call is TEST MODE — talk to the bot in the browser, no real phone call is placed.",
        "llm_stream_tts": llm_stream_tts,
        "telecaller_available": telecaller_available,
        "memory_enabled": memory_enabled,
        "natural_voice_available": natural_voice_available,
        "voice": "hi-IN-SwaraNeural" if natural_voice_available else None,
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
        from app.voice_agent.web_call_store import get_session, normalize_lead_key, normalize_session_id

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
        "niche": "general",
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

    await _run_blocking(_ensure_dialog)
    if await _run_blocking(_get_tcbrain, session.get("niche", "general")) is not None:
        responder = "telecaller"
    elif dialog is not None:
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
                        for seg in opening_segments():
                            history.append({"role": "assistant", "content": seg})
                            _log_turn(session, "assistant", seg)
                            await websocket.send_json(
                                {
                                    "type": "bot",
                                    "text": seg,
                                    "audio_b64": None,
                                    "test_mode": True,
                                }
                            )
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
                        history.append({"role": "assistant", "content": opening})
                        _log_turn(session, "assistant", opening)
                        await websocket.send_json(
                            {
                                "type": "bot",
                                "text": opening,
                                "audio_b64": None,
                                "test_mode": True,
                            }
                        )
                        try:
                            await websocket.send_json(
                                {"type": "session", **_memory_meta(session)}
                            )
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

            # Extract user text. Audio (jab client ne bheja ho) PEHLE server
            # STT se transcribe hota hai — Groq whisper-large-v3 Hinglish me
            # browser Web Speech API se kahin behtar sunta hai (phone-parity).
            # STT fail/empty par browser ka text fallback hai (zero regression).
            browser_text = (data.get("text") or "").strip()
            user_text = ""
            if data.get("audio_b64"):
                user_text = await _transcribe_audio(pipeline, brain, data.get("audio_b64"))
            if not user_text:
                user_text = browser_text

            if not user_text:
                await websocket.send_json(
                    {"type": "error", "text": "Empty message — nothing to process."}
                )
                continue

            _log_turn(session, "user", user_text)
            pitch_raw = session.get("pitch_state")
            if pitch_raw:
                try:
                    from app.voice_agent.platform_pitch import PlatformPitchState, next_reply

                    pst = PlatformPitchState(
                        phase=str(pitch_raw.get("phase") or "await_interest"),
                        convinced_once=bool(pitch_raw.get("convinced_once")),
                    )
                    gate_reply, pst = next_reply(pst, user_text)
                    session["pitch_state"] = {
                        "phase": pst.phase,
                        "convinced_once": pst.convinced_once,
                    }
                    if gate_reply:
                        history.append({"role": "user", "content": user_text})
                        history.append({"role": "assistant", "content": gate_reply})
                        _log_turn(session, "assistant", gate_reply)
                        tcbrain = await _run_blocking(_get_tcbrain, session.get("niche", "general"))
                        if pst.phase == "discovery" and tcbrain is not None:
                            if hasattr(tcbrain, "confirm_interest"):
                                tcbrain.confirm_interest()
                        await websocket.send_json(
                            {
                                "type": "bot",
                                "text": gate_reply,
                                "audio_b64": None,
                                "heard": user_text,
                                "test_mode": True,
                                "should_end": pst.phase == "closed",
                            }
                        )
                        continue
                except Exception as e:
                    logger.debug(f"web-call: platform pitch gate skip ({e}).")

            # PRIMARY: professional TelecallerBrain (the SAME brain as the phone
            # agent — researched niche scripts + free_ai/Gemini, KB-grounded),
            # spoken in the natural Swara voice (EdgeTTS mp3 b64). On empty/fail
            # we drop through to the existing natural-dialog/_respond chain.
            tcbrain = await _run_blocking(_get_tcbrain, session.get("niche", "general"))
            if tcbrain is not None:
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

                async def _brain_turn() -> str:
                    nonlocal tc_reply
                    if use_llm_stream:
                        return await _brain_turn_stream()
                    try:
                        tc_reply = await tcbrain.reply(history, user_text)
                    except Exception as e:
                        tc_reply = ""
                        logger.warning(
                            f"web-call: TelecallerBrain reply failed, using fallback: {e}"
                        )
                    if tc_reply:
                        await _send_tcbrain_sentence_chunks(
                            websocket,
                            sentences=_split_sentences(tc_reply),
                            user_text=user_text,
                            full_reply=tc_reply,
                            llm_stream=False,
                        )
                    return tc_reply

                async def _brain_turn_stream() -> str:
                    nonlocal tc_reply
                    streamed: list[str] = []
                    try:
                        async for sentence in tcbrain.reply_stream_sentences(history, user_text):
                            streamed.append(sentence)
                            await _send_tcbrain_sentence_chunks(
                                websocket,
                                sentences=[sentence],
                                user_text=user_text,
                                full_reply=" ".join(streamed).strip(),
                                llm_stream=True,
                            )
                        tc_reply = " ".join(streamed).strip()
                    except Exception as e:
                        tc_reply = ""
                        logger.warning(
                            f"web-call: TelecallerBrain stream reply failed, using fallback: {e}"
                        )
                    return tc_reply

                try:
                    tc_reply = await asyncio.wait_for(_brain_turn(), timeout=8.0)
                except asyncio.TimeoutError:
                    tc_reply = ""
                    logger.warning("web-call: TelecallerBrain turn timed out (8s)")
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
                        )

                if tc_reply:
                    history.append({"role": "user", "content": user_text})
                    history.append({"role": "assistant", "content": tc_reply})
                    _log_turn(session, "assistant", tc_reply)
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


async def _transcribe_audio(pipeline: Any, brain: Any, audio_b64: str) -> str:
    """
    Server-side STT. PRIMARY: free_ai Groq whisper-large-v3 (wahi chain jo
    phone agent use karta hai — Hinglish-strong). Fallback: pipeline transcribe
    method. '' return = caller browser-provided text use karega. Never raises.
    """
    import base64

    try:
        audio = base64.b64decode(audio_b64)
    except Exception:
        return ""
    if not audio or len(audio) > 4_000_000:  # >4MB = kuch galat hai, skip
        return ""

    # 1) Groq whisper-large-v3 via free_ai (phone-parity, GROQ_API_KEY needed).
    try:
        from app.voice_agent import free_ai  # type: ignore

        filename, mime = _sniff_audio_format(audio)
        text, _provider = await free_ai.transcribe_audio(
            audio, language="hi", filename=filename, mime=mime
        )
        if (text or "").strip():
            return text.strip()
    except Exception as e:
        logger.debug(f"web-call: free_ai STT failed ({e}).")

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
                    return str(text), None
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
    if isinstance(result, (tuple, list)) and result:
        text = str(result[0])
        audio = result[1] if len(result) > 1 else None
        return text, audio
    return str(result), None
