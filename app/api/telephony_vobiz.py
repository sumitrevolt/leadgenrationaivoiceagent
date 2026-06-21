"""
Vobiz Telephony API — outbound test calls via the Vobiz Direct Call REST API.

Endpoints (mounted by main.py under /api → /api/telephony/vobiz/*):
    POST /telephony/vobiz/test-call       (admin) — place a test call; speaks an
                                          LLM-generated (or supplied) Hinglish
                                          greeting, then hangs up.
    GET|POST /telephony/vobiz/answer/{token}  (NO auth — Vobiz fetches this)
                                          — returns VobizXML for the call.
    GET  /telephony/vobiz/status          (admin) — config + balance snapshot.

NOTE (DLT pending): test calls sirf own/known numbers pe (transactional);
promo cold-calls 140-DID + DLT ke baad hi.
"""

import json
import uuid
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.config import settings
from app.models.user import User
from app.telephony.vobiz_handler import VobizClient, build_speak_xml, build_stream_xml
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/telephony/vobiz", tags=["Telephony"])

# In-memory message store: token -> Speak text. Single-process best-effort —
# fine for admin test calls (Vobiz fetches the answer_url within seconds).
_PENDING_MESSAGES: dict[str, str] = {}
# Streaming calls: token -> {"niche", "client_id"} (answer-stream + WS read it).
# In-memory = same-process fallback; Redis = cross-process (docker exec fire_calls
# vs uvicorn worker — bina Redis niche hamesha general ho jati thi).
_PENDING_STREAMS: dict[str, dict[str, Any]] = {}
_MAX_PENDING = 200
_STREAM_REDIS_PREFIX = "vobiz:pending:"
_STREAM_REDIS_TTL_S = 600


def _answer_stream_qs(niche: str, client_id: str | None) -> str:
    """Query string embedded in answer_url — survives cross-process pending loss."""
    qs: dict[str, str] = {"niche": (niche or "general").strip() or "general"}
    if client_id:
        qs["client_id"] = str(client_id)
    return urlencode(qs)


async def _store_pending(token: str, data: dict[str, Any]) -> None:
    _PENDING_STREAMS[token] = data
    if len(_PENDING_STREAMS) > _MAX_PENDING:
        _PENDING_STREAMS.clear()
        _PENDING_STREAMS[token] = data
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        await r.setex(f"{_STREAM_REDIS_PREFIX}{token}", _STREAM_REDIS_TTL_S, json.dumps(data))
    except Exception as e:
        logger.debug("pending stream redis store skip: %s", e)


async def _peek_pending(token: str) -> dict[str, Any]:
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        raw = await r.get(f"{_STREAM_REDIS_PREFIX}{token}")
        if raw:
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            return json.loads(raw)
    except Exception:
        pass
    return _PENDING_STREAMS.get(token) or {}


async def _pop_pending(token: str) -> dict[str, Any] | None:
    pend = await _peek_pending(token)
    _PENDING_STREAMS.pop(token, None)
    try:
        from app.cache import get_redis_client

        r = await get_redis_client()
        await r.delete(f"{_STREAM_REDIS_PREFIX}{token}")
    except Exception:
        pass
    return pend or None

_FALLBACK_GREETING = (
    "Namaste! Yeh LeadGen AI ki taraf se ek AI demo call hai. "
    "Hum aapke business ke liye AI voice agent se qualified leads laate hain. "
    "Dhanyavaad, aapka din shubh ho!"
)


class TestCallRequest(BaseModel):
    """Outbound test-call request."""

    to: str = Field(
        ..., min_length=8, max_length=20, description="Destination number, E.164 (+91...)"
    )
    niche: str = Field("general", max_length=100, description="Niche key for the LLM greeting")
    message: str | None = Field(
        None, max_length=1000, description="Exact text to speak (skips LLM generation)"
    )
    call_type: str = Field(
        "transactional",
        description="'transactional' (consented/known, lenient) or 'promotional' "
        "(cold outreach — DND + 10-19 IST window + DLT/140 enforced)",
    )


async def _generate_message(niche: str) -> str:
    """LLM-generated Hinglish demo greeting; static fallback on any failure."""
    try:
        from app.voice_agent.llm_brain import LLMBrain  # heavy — import lazily

        brain = LLMBrain()
        text = await brain.generate_response(
            conversation_history=[
                {
                    "role": "user",
                    "content": (
                        f"Give a 2-sentence Hinglish intro call greeting for a {niche} "
                        "business demo call. Mention this is an AI demo call from LeadGen AI."
                    ),
                }
            ],
            niche=niche,
            client_name="LeadGen AI",
            client_service="AI voice agents",
        )
        if text and str(text).strip():
            return str(text).strip()
    except Exception as e:
        logger.warning(f"Vobiz test-call: LLM greeting failed, using fallback: {e}")
    return _FALLBACK_GREETING


@router.post("/test-call")
async def place_test_call(
    request: TestCallRequest,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Place an outbound Vobiz test call that speaks a greeting and hangs up."""
    client = VobizClient()
    if not client.available():
        raise HTTPException(
            status_code=503,
            detail="Vobiz not configured (VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN missing)",
        )

    message = (request.message or "").strip() or await _generate_message(request.niche)

    token = uuid.uuid4().hex[:10]
    if len(_PENDING_MESSAGES) >= _MAX_PENDING:  # bounded memory
        _PENDING_MESSAGES.clear()
    _PENDING_MESSAGES[token] = message

    answer_url = f"{settings.public_base_url}/api/telephony/vobiz/answer/{token}"
    result = await client.place_call(
        to=request.to, answer_url=answer_url, call_type=request.call_type
    )
    if result.get("blocked"):
        _PENDING_MESSAGES.pop(token, None)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Call blocked by compliance gate (TCCCPR/TRAI).",
                "compliance": result.get("compliance") or result.get("body"),
            },
        )
    placed = 200 <= int(result.get("status_code") or 0) < 300
    if not placed:
        logger.warning(f"Vobiz test-call not placed: {result}")

    return {
        "placed": placed,
        "vobiz_response": result,
        "answer_url": answer_url,
        "message_used": message,
    }


@router.api_route("/answer/{token}", methods=["GET", "POST"], include_in_schema=False)
async def answer_xml(token: str) -> Response:
    """Answer-URL webhook — Vobiz fetches this (NO auth). Returns VobizXML.

    Unknown/expired tokens get a generic greeting (never an error — the call
    is already live when Vobiz hits this)."""
    text = _PENDING_MESSAGES.get(token) or _FALLBACK_GREETING
    return Response(content=build_speak_xml(text), media_type="application/xml")


# --------------------------------------------------------------------------- #
# Conversational streaming (two-way WebSocket audio) — P3.
# --------------------------------------------------------------------------- #
class StreamCallRequest(BaseModel):
    """Outbound conversational (WebSocket-streamed) call request."""

    to: str = Field(..., min_length=8, max_length=20, description="Destination number, E.164")
    niche: str = Field("general", max_length=100, description="Niche key for the bot")
    client_id: str | None = Field(None, max_length=100, description="Client id for the bot")
    call_type: str = Field(
        "transactional",
        description="'transactional' (consented/known) or 'promotional' (cold — "
        "DND + 10-19 IST window + DLT/140 enforced)",
    )


def _wss_host() -> str:
    """Derive the wss host from public_base_url (fallback leadsgenai.in)."""
    base = (settings.public_base_url or "https://leadsgenai.in").strip()
    return base.split("://", 1)[-1].rstrip("/") or "leadsgenai.in"


async def start_stream_call(
    to: str,
    niche: str = "general",
    client_id: str | None = None,
    call_type: str = "transactional",
) -> dict[str, Any]:
    """INTERNAL helper — conversational stream call lagao (no HTTP/auth layer).

    Wahi token + _PENDING_STREAMS + answer-stream URL flow jo POST /stream-call
    use karta hai; auto-callback (inquiry → AI call) jaise internal callers ke
    liye. NEVER raises — fail pe {"placed": False, "error": ...} return.
    """
    try:
        client = VobizClient()
        if not client.available():
            return {"placed": False, "error": "vobiz_not_configured"}

        token = uuid.uuid4().hex[:10]
        niche_key = (niche or "general").strip() or "general"
        await _store_pending(token, {"niche": niche_key, "client_id": client_id})

        answer_url = (
            f"{settings.public_base_url}/api/telephony/vobiz/answer-stream/{token}"
            f"?{_answer_stream_qs(niche_key, client_id)}"
        )
        result = await client.place_call(to=to, answer_url=answer_url, call_type=call_type)
        if result.get("blocked"):
            await _pop_pending(token)
            return {"placed": False, "error": "compliance_blocked", "vobiz_response": result}
        placed = 200 <= int(result.get("status_code") or 0) < 300
        return {
            "placed": placed,
            "vobiz_response": result,
            "answer_url": answer_url,
            "stream_token": token,
        }
    except Exception as e:
        logger.warning(f"Vobiz start_stream_call failed: {e}")
        return {"placed": False, "error": str(e)}


@router.post("/stream-call")
async def place_stream_call(
    request: StreamCallRequest,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Place an outbound call that streams two-way audio to our WS for a full
    conversation (vs. /test-call which speaks one line and hangs up)."""
    client = VobizClient()
    if not client.available():
        raise HTTPException(
            status_code=503,
            detail="Vobiz not configured (VOBIZ_AUTH_ID / VOBIZ_AUTH_TOKEN missing)",
        )

    token = uuid.uuid4().hex[:10]
    niche_key = (request.niche or "general").strip() or "general"
    await _store_pending(token, {"niche": niche_key, "client_id": request.client_id})

    answer_url = (
        f"{settings.public_base_url}/api/telephony/vobiz/answer-stream/{token}"
        f"?{_answer_stream_qs(niche_key, request.client_id)}"
    )
    result = await client.place_call(
        to=request.to, answer_url=answer_url, call_type=request.call_type
    )
    if result.get("blocked"):
        await _pop_pending(token)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "Call blocked by compliance gate (TCCCPR/TRAI).",
                "compliance": result.get("compliance") or result.get("body"),
            },
        )
    placed = 200 <= int(result.get("status_code") or 0) < 300
    if not placed:
        logger.warning(f"Vobiz stream-call not placed: {result}")
    try:  # Team activity: Swara ne call lagayi
        from app.platform.team import log_event

        log_event(
            "swara",
            "call_placed",
            f"Conversational call → {request.to} (niche: {getattr(request, 'niche', '') or 'general'})",
            status="ok" if placed else "error",
        )
    except Exception:
        pass
    return {
        "placed": placed,
        "vobiz_response": result,
        "answer_url": answer_url,
        "stream_token": token,
    }


@router.api_route("/answer-stream/{token}", methods=["GET", "POST"], include_in_schema=False)
async def answer_stream_xml(token: str, request: Request) -> Response:
    """Answer-URL webhook for streamed calls (NO auth). Returns VobizXML that
    bridges the call to our WebSocket. Unknown tokens still get a valid stream
    (niche=general) — the call is already live when Vobiz fetches this."""
    pend = await _peek_pending(token)
    niche = (request.query_params.get("niche") or pend.get("niche") or "general").strip()
    client_id = request.query_params.get("client_id") or pend.get("client_id")
    qs: dict[str, str] = {"niche": niche or "general"}
    if client_id:
        qs["client_id"] = str(client_id)
    ws_url = f"wss://{_wss_host()}/api/telephony/vobiz/stream/{token}?{urlencode(qs)}"
    return Response(content=build_stream_xml(ws_url), media_type="application/xml")


@router.websocket("/stream/{token}")
async def vobiz_stream_ws(
    websocket: WebSocket,
    token: str,
    niche: str = "general",
    client_id: str | None = None,
) -> None:
    """Two-way media WebSocket Vobiz connects to. Runs a full STT->LLM->TTS
    conversation loop. niche/client come from query params or the pending
    store (filled by /stream-call); customParameters in the start event win."""
    from app.telephony.vobiz_stream import VobizStreamSession

    pend = await _pop_pending(token)
    if pend:
        niche = pend.get("niche") or niche
        client_id = pend.get("client_id") or client_id

    # Resolve real client name + niche from client_id so the INSTANT greeting
    # (played at WS-open) isn't generic "Demo Co" / niche=general. Never-raise.
    client_name = "LeadGen AI"
    if client_id:
        try:
            from app.marketing import clients_store

            _c = clients_store.get_client(client_id)
            if _c:
                client_name = (_c.get("business_name") or "").strip() or client_name
                if (not niche or niche == "general") and _c.get("niche"):
                    niche = _c["niche"]
        except Exception:
            pass

    session = VobizStreamSession(
        websocket, niche=niche, client_id=client_id, client_name=client_name
    )
    await session.handle()


@router.get("/status")
async def vobiz_status(user: User = Depends(require_admin)) -> dict[str, Any]:
    """Vobiz config snapshot + best-effort balance (admin)."""
    client = VobizClient()
    out: dict[str, Any] = {
        "available": client.available(),
        "trunk_id": settings.vobiz_trunk_id,
        "domain": settings.vobiz_trunk_domain,
        "caller_id_set": bool(settings.vobiz_caller_id),
        "balance": None,
    }
    # Streaming (conversational) capability snapshot — verify VPS deps are live.
    try:
        from app.telephony import vobiz_stream as _vs

        streaming: dict[str, Any] = {
            "stt_available": _vs.STT_AVAILABLE,
            "tts_available": _vs.TTS_AVAILABLE,
            "audioop": _vs._AUDIOOP_OK,
        }
        # STT provider chain this worker would try (groq -> gemini -> whisper).
        try:
            streaming["stt_chain"] = _vs._stt_chain()
        except Exception:
            pass
        # Free-AI resilience snapshot — confirm keys are picked up WITHOUT a
        # paid call: Gemini multi-key count + free LLM/STT provider availability.
        try:
            from app.voice_agent.gemini_keys import key_count

            streaming["gemini_keys"] = key_count()
        except Exception:
            pass
        try:
            from app.voice_agent import free_ai

            streaming["free_ai"] = free_ai.describe()
        except Exception:
            pass
        out["streaming"] = streaming
    except Exception as e:
        out["streaming"] = {"error": str(e)}
    if client.available():
        try:
            out["balance"] = await client.get_balance()
        except Exception as e:  # belt-and-braces; client already never raises
            out["balance"] = {"status_code": 0, "body": {"error": str(e)}}
    return out
