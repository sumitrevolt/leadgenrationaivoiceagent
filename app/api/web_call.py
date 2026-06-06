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
from typing import Any, Dict, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/web-call", tags=["Web Call (Test Mode)"])


# ---------------------------------------------------------------------------- #
# Lazy, import-safe resolvers
# ---------------------------------------------------------------------------- #
def _get_pipeline() -> Optional[Any]:
    """Lazily build app.voice_agent.pipeline.VoicePipeline (owned by another
    agent — may not exist). Returns None on any failure."""
    try:
        from app.voice_agent.pipeline import VoicePipeline  # type: ignore
        return VoicePipeline()
    except Exception as e:
        logger.debug(f"web-call: VoicePipeline unavailable ({e}).")
        return None


def _get_registry_describe() -> Optional[Dict[str, Any]]:
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


def _get_llm_brain() -> Optional[Any]:
    """Fallback responder — the LLM brain — if no full pipeline is present."""
    try:
        from app.voice_agent.llm_brain import LLMBrain  # type: ignore
        return LLMBrain()
    except Exception as e:
        logger.debug(f"web-call: LLMBrain unavailable ({e}).")
        return None


async def _maybe_await(value: Any) -> Any:
    import asyncio
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


def _pipeline_text_method(pipeline: Any) -> Optional[Any]:
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
async def web_call_config() -> Dict[str, Any]:
    """
    Report whether the pipeline / providers are available + active provider
    names. Always returns 200 — degrades gracefully.
    """
    pipeline = _get_pipeline()
    pipeline_can_text = _pipeline_text_method(pipeline) is not None
    registry = _get_registry_describe()
    brain_available = _get_llm_brain() is not None

    # Telephony providers (for the dashboard's awareness) — best-effort.
    telephony: Dict[str, Any] = {}
    try:
        from app.telephony.telephony_service import get_telephony_service
        telephony = get_telephony_service().validate_config()
    except Exception as e:
        logger.debug(f"web-call: telephony info unavailable ({e}).")

    return {
        "test_mode": True,
        "note": "Web Call is TEST MODE — talk to the bot in the browser, no real phone call is placed.",
        "pipeline_available": pipeline is not None,
        "llm_fallback_available": brain_available,
        "providers": registry or {"detail": "No provider registry; using fallback responder."},
        "telephony": telephony or {"detail": "Telephony info unavailable."},
        "responder": (
            "pipeline" if pipeline_can_text
            else ("llm" if brain_available else "echo")
        ),
    }


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
    await websocket.accept()

    pipeline = _get_pipeline()
    # Only treat the pipeline as the responder when it can actually answer
    # text. Otherwise load the LLM brain right away.
    if _pipeline_text_method(pipeline) is None:
        pipeline = None
    brain = _get_llm_brain() if pipeline is None else None

    responder = "pipeline" if pipeline is not None else ("llm" if brain else "echo")

    # Per-session conversation state (used by the LLM fallback).
    history: list = []
    session: Dict[str, Any] = {"niche": "general", "flow": "qualify", "client_name": "Demo Co"}

    try:
        await websocket.send_json({
            "type": "ready",
            "test_mode": True,
            "responder": responder,
            "pipeline": pipeline is not None,
            "providers": _get_registry_describe() or {},
            "note": "TEST MODE — no real call. Type a message to talk to the bot.",
        })
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
                    await websocket.send_json({"type": "error", "text": "Invalid message (expected JSON)."})
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

            if mtype == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if mtype == "start":
                await websocket.send_json({
                    "type": "info",
                    "text": f"TEST MODE started — niche='{session['niche']}', flow='{session['flow']}'.",
                })
                continue

            # Extract user text (direct text, or transcribe audio if supported).
            user_text = (data.get("text") or "").strip()
            if not user_text and data.get("audio_b64"):
                user_text = await _transcribe_audio(pipeline, brain, data.get("audio_b64"))

            if not user_text:
                await websocket.send_json({"type": "error", "text": "Empty message — nothing to process."})
                continue

            history.append({"role": "user", "content": user_text})

            # Generate the bot reply via pipeline -> llm -> echo.
            bot_text, audio_b64 = await _respond(pipeline, brain, history, session, user_text)
            history.append({"role": "assistant", "content": bot_text})

            await websocket.send_json({
                "type": "bot",
                "text": bot_text,
                "audio_b64": audio_b64,  # may be None — browser will use its own TTS/none
                "test_mode": True,
            })
    except Exception as e:
        logger.error(f"web-call ws fatal (handled): {e}")
        try:
            await websocket.send_json({"type": "error", "text": "Server error — session ended."})
        except Exception:
            pass


# ---------------------------------------------------------------------------- #
# Responder helpers
# ---------------------------------------------------------------------------- #
async def _transcribe_audio(pipeline: Any, brain: Any, audio_b64: str) -> str:
    """Best-effort STT for audio chunks. Returns '' if not supported."""
    import base64
    try:
        audio = base64.b64decode(audio_b64)
    except Exception:
        return ""

    # Try a pipeline transcribe method.
    for obj in (pipeline,):
        for name in ("transcribe", "stt", "speech_to_text"):
            fn = getattr(obj, name, None) if obj else None
            if callable(fn):
                try:
                    return (await _maybe_await(fn(audio))) or ""
                except Exception:
                    pass
    # No server-side STT available — the browser's Web Speech API is the
    # intended path, so just return empty and let the client handle it.
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
                text = await _maybe_await(fn(
                    conversation_history=history,
                    niche=session.get("niche", "general"),
                    client_name=session.get("client_name", "Demo Co"),
                    client_service=session.get("niche", "our service"),
                ))
                if text:
                    return str(text), None
            except Exception as e:
                logger.debug(f"web-call llm responder error ({e}).")

    # 3) Echo fallback (always works).
    return (
        f"[echo / test-mode] You said: \"{user_text}\". "
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
