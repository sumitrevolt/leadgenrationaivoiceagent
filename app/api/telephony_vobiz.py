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
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.config import settings
from app.models.user import User
from app.telephony.vobiz_handler import VobizClient, build_speak_xml
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/telephony/vobiz", tags=["Telephony"])

# In-memory message store: token -> Speak text. Single-process best-effort —
# fine for admin test calls (Vobiz fetches the answer_url within seconds).
_PENDING_MESSAGES: Dict[str, str] = {}
_MAX_PENDING = 200

_FALLBACK_GREETING = (
    "Namaste! Yeh LeadGen AI ki taraf se ek AI demo call hai. "
    "Hum aapke business ke liye AI voice agent se qualified leads laate hain. "
    "Dhanyavaad, aapka din shubh ho!"
)


class TestCallRequest(BaseModel):
    """Outbound test-call request."""
    to: str = Field(..., min_length=8, max_length=20, description="Destination number, E.164 (+91...)")
    niche: str = Field("general", max_length=100, description="Niche key for the LLM greeting")
    message: Optional[str] = Field(
        None, max_length=1000, description="Exact text to speak (skips LLM generation)"
    )


async def _generate_message(niche: str) -> str:
    """LLM-generated Hinglish demo greeting; static fallback on any failure."""
    try:
        from app.voice_agent.llm_brain import LLMBrain  # heavy — import lazily

        brain = LLMBrain()
        text = await brain.generate_response(
            conversation_history=[{
                "role": "user",
                "content": (
                    f"Give a 2-sentence Hinglish intro call greeting for a {niche} "
                    "business demo call. Mention this is an AI demo call from LeadGen AI."
                ),
            }],
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
) -> Dict[str, Any]:
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
    result = await client.place_call(to=request.to, answer_url=answer_url)
    placed = 200 <= int(result.get("status_code") or 0) < 300
    if not placed:
        logger.warning(f"Vobiz test-call not placed: {result}")

    return {
        "placed": placed,
        "vobiz_response": result,
        "answer_url": answer_url,
        "message_used": message,
    }


@router.api_route("/answer/{token}", methods=["GET", "POST"])
async def answer_xml(token: str) -> Response:
    """Answer-URL webhook — Vobiz fetches this (NO auth). Returns VobizXML.

    Unknown/expired tokens get a generic greeting (never an error — the call
    is already live when Vobiz hits this)."""
    text = _PENDING_MESSAGES.get(token) or _FALLBACK_GREETING
    return Response(content=build_speak_xml(text), media_type="application/xml")


@router.get("/status")
async def vobiz_status(user: User = Depends(require_admin)) -> Dict[str, Any]:
    """Vobiz config snapshot + best-effort balance (admin)."""
    client = VobizClient()
    out: Dict[str, Any] = {
        "available": client.available(),
        "trunk_id": settings.vobiz_trunk_id,
        "domain": settings.vobiz_trunk_domain,
        "caller_id_set": bool(settings.vobiz_caller_id),
        "balance": None,
    }
    if client.available():
        try:
            out["balance"] = await client.get_balance()
        except Exception as e:  # belt-and-braces; client already never raises
            out["balance"] = {"status_code": 0, "body": {"error": str(e)}}
    return out
