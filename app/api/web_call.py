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


def _get_natural_dialog(niche: str, client_name: str, client_service: str) -> Optional[Any]:
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


async def _edge_tts_mp3_b64(text: str) -> Optional[str]:
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

    async def _synth() -> Optional[str]:
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
        opening = (opening
                   .replace("[Company]", client_name or "hamari company")
                   .replace("[Name]", "Swara")
                   .replace("[Project]", "hamare project"))
        return opening.strip()
    return (f"Namaste! Main Swara bol rahi hoon {client_name or 'hamari company'} ki taraf se — "
            "bas ek minute baat kar sakti hoon?")


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
    natural_available = _get_natural_dialog("general", "Demo Co", "") is not None

    # Telephony providers (for the dashboard's awareness) — best-effort.
    telephony: Dict[str, Any] = {}
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

    return {
        "test_mode": True,
        "note": "Web Call is TEST MODE — talk to the bot in the browser, no real phone call is placed.",
        "telecaller_available": telecaller_available,
        "natural_voice_available": natural_voice_available,
        "voice": "hi-IN-SwaraNeural" if natural_voice_available else None,
        "natural_dialog_available": natural_available,
        "pipeline_available": pipeline is not None,
        "llm_fallback_available": brain_available,
        "providers": registry or {"detail": "No provider registry; using fallback responder."},
        "telephony": telephony or {"detail": "Telephony info unavailable."},
        "responder": (
            "telecaller" if telecaller_available
            else ("natural" if natural_available
                  else ("pipeline" if pipeline_can_text
                        else ("llm" if brain_available else "echo")))
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

    # Per-session conversation context. Defaults until the client tells us the
    # niche/flow (via 'start' or the first 'user' message).
    session: Dict[str, Any] = {
        "niche": "general", "flow": "qualify",
        "client_name": "Demo Co", "client_service": "",
    }

    # PRIMARY responder: the human-like NaturalDialogManager. It LISTENS,
    # understands, answers the customer's question, and keeps replies short —
    # the whole point of this fix. Built lazily once we know the niche; rebuilt
    # (with a fresh conversation) if the niche changes mid-session.
    dialog: Any = None
    dstate: Any = None
    dialog_niche: Optional[str] = None

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
            niche, session.get("client_name", "Demo Co"),
            session.get("client_service", ""),
        )
        if mgr is not None:
            dialog = mgr
            dstate = mgr.new_conversation()
            dialog_niche = niche

    def _get_tcbrain(niche: str) -> Optional[Any]:
        """
        Lazy, per-session TelecallerBrain — the SAME professional brain the phone
        agent uses (researched niche scripts + free_ai Cerebras/Groq/Gemini,
        KB-grounded). Cached per niche on the session so each niche builds once;
        a failed build is cached as None (no AI key / import error) so the caller
        degrades to the natural-dialog/_respond chain without retrying. Never raises.
        """
        niche = niche or "general"
        cache = session.setdefault("tcbrains", {})
        if niche in cache:
            return cache[niche]
        tcb = None
        try:
            from app.voice_agent.telecaller_brain import TelecallerBrain  # type: ignore
            tcb = TelecallerBrain(
                niche=niche,
                client_name=session.get("client_name", "Demo Co"),
            )
        except Exception as e:
            logger.debug(f"web-call: TelecallerBrain unavailable for '{niche}' ({e}).")
            tcb = None
        cache[niche] = tcb
        return tcb

    _ensure_dialog()
    if _get_tcbrain(session.get("niche", "general")) is not None:
        responder = "telecaller"
    elif dialog is not None:
        responder = "natural"
    elif pipeline is not None:
        responder = "pipeline"
    else:
        brain = _get_llm_brain()
        responder = "llm" if brain is not None else "echo"

    try:
        await websocket.send_json({
            "type": "ready",
            "test_mode": True,
            "responder": responder,
            "pipeline": pipeline is not None,
            "providers": _get_registry_describe() or {},
            "note": "TEST MODE — no real call. Say hello to talk to the bot.",
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
                # Fresh conversation for the chosen niche + a natural opening
                # line so the bot greets FIRST (proves it's alive and human).
                dialog = None            # force rebuild with fresh state
                history = []

                # PRIMARY: professional TelecallerBrain opener (same as the phone
                # agent), spoken in the natural Swara voice (EdgeTTS mp3 b64).
                niche = session.get("niche", "general")
                tcbrain = _get_tcbrain(niche)
                if tcbrain is not None:
                    try:
                        opening = (tcbrain.opening_line() or "").strip()
                    except Exception:
                        opening = ""
                    if not opening:
                        opening = _script_opening(niche, session.get("client_name", "Demo Co"))
                    if opening:
                        history.append({"role": "assistant", "content": opening})
                        audio_b64 = await _edge_tts_mp3_b64(opening)
                        await websocket.send_json({
                            "type": "bot", "text": opening,
                            "audio_b64": audio_b64, "test_mode": True,
                        })
                        continue

                # FALLBACK: natural-dialog opening (browser TTS), then info.
                _ensure_dialog()
                if dialog is not None and dstate is not None:
                    try:
                        opening = await dialog.opening_line(dstate)
                        await websocket.send_json({
                            "type": "bot", "text": opening,
                            "audio_b64": None, "test_mode": True,
                        })
                        continue
                    except Exception as e:
                        logger.debug(f"web-call: opening line skipped ({e}).")
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

            # PRIMARY: professional TelecallerBrain (the SAME brain as the phone
            # agent — researched niche scripts + free_ai/Gemini, KB-grounded),
            # spoken in the natural Swara voice (EdgeTTS mp3 b64). On empty/fail
            # we drop through to the existing natural-dialog/_respond chain.
            tcbrain = _get_tcbrain(session.get("niche", "general"))
            if tcbrain is not None:
                try:
                    tc_reply = await tcbrain.reply(history, user_text)
                except Exception as e:
                    tc_reply = ""
                    logger.warning(f"web-call: TelecallerBrain reply failed, using fallback: {e}")
                if tc_reply:
                    history.append({"role": "user", "content": user_text})
                    history.append({"role": "assistant", "content": tc_reply})
                    audio_b64 = await _edge_tts_mp3_b64(tc_reply)
                    await websocket.send_json({
                        "type": "bot",
                        "text": tc_reply,
                        "audio_b64": audio_b64,  # mp3 (Swara) or None -> browser TTS
                        "test_mode": True,
                    })
                    continue

            # FALLBACK: human-like natural dialog (listen -> understand -> answer).
            _ensure_dialog()
            if dialog is not None and dstate is not None:
                try:
                    reply = await dialog.respond(user_text, dstate)
                    await websocket.send_json({
                        "type": "bot",
                        "text": reply.text,
                        "audio_b64": None,  # browser TTS speaks it
                        "test_mode": True,
                        "should_end": bool(getattr(reply, "should_end", False)),
                    })
                    continue
                except Exception as e:
                    logger.warning(f"web-call: natural dialog failed, using fallback: {e}")

            # FALLBACK: pipeline -> llm -> echo (only if natural dialog absent).
            history.append({"role": "user", "content": user_text})
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
                logger.warning("web-call llm responder returned empty text — falling back to echo.")
            except Exception as e:
                logger.warning(f"web-call llm responder failed — falling back to echo: {type(e).__name__}: {e}")

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
