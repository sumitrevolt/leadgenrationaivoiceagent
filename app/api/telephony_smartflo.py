"""
Tata Tele Smartflo Voice Streaming API
=======================================

Endpoints (mounted by main.py under /api → /api/telephony/smartflo/*):

  GET|POST /telephony/smartflo/endpoint   (Dynamic Endpoint resolver)
    Smartflo calls this to get the wss:// URL for each call.
    Returns: {"success": true, "wss_url": "wss://leadsgenai.in/api/telephony/smartflo/stream?..."}

  GET|POST /telephony/smartflo/stream     (WebSocket — Smartflo connects here)
    Receives bidirectional mulaw 8kHz audio. Runs STT→LLM→TTS conversation loop.

  GET  /telephony/smartflo/status         (admin) — config + capability snapshot

Setup in Smartflo portal (Settings → Channels → Voice Bot):
  Option A (Static): set wss://leadsgenai.in/api/telephony/smartflo/stream
  Option B (Dynamic): POST to https://leadsgenai.in/api/telephony/smartflo/endpoint
                      with $callId, $fromNumber, $toNumber mapped to body
"""

import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.config import settings
from app.models.user import User
from app.telephony.tata_smartflo_handler import TataSmartfloClient
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/telephony/smartflo", tags=["Telephony"])


def _wss_host() -> str:
    """Derive the wss:// host from env or settings."""
    host = (
        os.environ.get("SMARTFLO_WS_HOST")
        or os.environ.get("PUBLIC_HOSTNAME")
        or getattr(settings, "public_hostname", "")
        or ""
    ).strip()
    if not host:
        # Fallback: construct from PUBLIC_BASE_URL
        base = (
            os.environ.get("PUBLIC_BASE_URL")
            or os.environ.get("SITE_BASE")
            or getattr(settings, "public_base_url", "")
            or ""
        ).strip()
        if base:
            host = base.replace("https://", "").replace("http://", "").rstrip("/")
    return host or "leadsgenai.in"


# ---------------------------------------------------------------------------
# Dynamic Endpoint resolver
# ---------------------------------------------------------------------------
@router.post("/endpoint")
async def smartflo_dynamic_endpoint(request: Request) -> JSONResponse:
    """Smartflo Dynamic Endpoint: receives call metadata, returns wss:// URL.

    Smartflo sends: {"callId":"...", "fromNumber":"...", "toNumber":"...", "status":"..."}
    We return:       {"success": true, "wss_url": "wss://leadsgenai.in/api/telephony/smartflo/stream?..."}

    Response deadline: 2000ms (Smartflo enforced).
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    call_id = body.get("callId", "")
    from_number = body.get("fromNumber", "")
    to_number = body.get("toNumber", "")

    # Build wss:// URL with call metadata as query params
    host = _wss_host()
    params = f"call_id={call_id}&from={from_number}&to={to_number}"
    # Optional: add niche/client routing
    niche = body.get("niche", "")
    client_id = body.get("clientId", "")
    if niche:
        params += f"&niche={niche}"
    if client_id:
        params += f"&client_id={client_id}"

    wss_url = f"wss://{host}/api/telephony/smartflo/stream?{params}"

    logger.info(
        f"[smartflo-endpoint] resolved call_id={call_id} "
        f"from={from_number} to={to_number} → wss://{host}/..."
    )

    return JSONResponse(
        content={"success": True, "wss_url": wss_url},
        status_code=200,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint (Smartflo connects here)
# ---------------------------------------------------------------------------
@router.websocket("/stream")
async def smartflo_stream_ws(websocket: WebSocket) -> None:
    """Bidirectional audio WebSocket for Smartflo Voice Streaming.

    Smartflo connects here and sends/receives mulaw 8kHz audio events.
    Query params (from dynamic endpoint or static config):
      call_id, from, to, niche, client_id, lead_phone, opening_line
    """
    from app.telephony.smartflo_stream import SmartfloStreamSession

    # Check if Smartflo voice streaming is enabled
    enabled = (
        os.environ.get("SMARTFLO_VOICE_STREAM_ENABLED", "0").strip().lower()
        in ("1", "true", "yes", "on")
    )
    if not enabled:
        logger.warning("[smartflo-stream] rejected: SMARTFLO_VOICE_STREAM_ENABLED=0")
        try:
            await websocket.close(code=1008)
        except Exception:
            pass
        return

    # Optional: HMAC secret verification
    secret = os.environ.get("SMARTFLO_WS_SECRET", "").strip()
    require_secret = os.environ.get("SMARTFLO_WS_REQUIRE_SECRET", "0").strip().lower() in (
        "1", "true", "yes",
    )
    if require_secret and secret:
        # Verify from query param or header
        token = websocket.query_params.get("token", "")
        if not token:
            # Check Sec-WebSocket-Protocol header
            protocols = websocket.headers.get("sec-websocket-protocol", "")
            if protocols:
                token = protocols.split(",")[0].strip()
        if not _verify_hmac(token, secret):
            logger.warning("[smartflo-stream] rejected: invalid HMAC token")
            try:
                await websocket.close(code=1008)
            except Exception:
                pass
            return

    # Optional provider-IP allowlist — INERT by design: unset = current behaviour.
    # Armed = fail-CLOSED (see _client_ip_allowed). Data-file/env driven so the
    # owner can pin Tata's egress without a code deploy.
    _allow_ips = os.environ.get("SMARTFLO_WS_ALLOW_IPS", "").strip()
    if _allow_ips and not _client_ip_allowed(websocket, _allow_ips):
        logger.warning(
            "[smartflo-stream] rejected: client IP not in SMARTFLO_WS_ALLOW_IPS"
        )
        try:
            await websocket.close(code=1008)
        except Exception:
            pass
        return

    # Extract call metadata from query params
    call_id = websocket.query_params.get("call_id", "")
    from_number = websocket.query_params.get("from", "")
    to_number = websocket.query_params.get("to", "")
    niche = websocket.query_params.get("niche", "general")
    client_id = websocket.query_params.get("client_id", "")
    lead_phone = websocket.query_params.get("lead_phone", from_number)
    opening_line = websocket.query_params.get("opening_line", "")

    # Override niche from env if not specified
    if not niche or niche == "general":
        niche = os.environ.get("SMARTFLO_DEFAULT_NICHE", "general")

    session = SmartfloStreamSession(
        websocket=websocket,
        niche=niche,
        client_id=client_id or None,
        lead_phone=lead_phone or from_number or None,
        crm_lead_id=websocket.query_params.get("crm_lead_id"),
        opening_line=opening_line,
    )
    session.call_sid = call_id
    session.from_number = from_number
    session.to_number = to_number

    await session.handle()


# ---------------------------------------------------------------------------
# Test call (admin) — place a one-shot outbound call via Smartflo C2C
# ---------------------------------------------------------------------------


async def _smartflo_dial_block_reason(to: str) -> str | None:
    """Return a block reason for ``to``, or ``None`` when the dial may proceed.

    Mirrors the pre-dial gate sequence of ``TataSmartfloClient.place_call`` /
    ``VobizClient.place_call``: dial_gate -> ComplianceGate -> admin kill switch.
    FAILS CLOSED — an error inside any gate is returned as a block reason, so a
    gate outage never translates into an ungated dial.
    """
    try:
        from app.telephony.dial_gate import check as dial_gate_check

        ok, reason = dial_gate_check(to, call_type="transactional")
        if not ok:
            return f"dial_gate: {reason}"
    except Exception as e:
        return f"dial_gate_error: {e}"

    try:
        from app.telephony.compliance import CallType, get_compliance_gate

        decision = await get_compliance_gate().check(to, CallType.TRANSACTIONAL)
        if not decision.allowed:
            return "; ".join(decision.reasons) or "compliance_gate_blocked"
    except Exception as e:
        return f"gate_error: {e}"

    try:
        from app.telephony.voice_launch import admin_kill_engaged

        if admin_kill_engaged():
            return "admin_kill_engaged"
    except Exception as e:
        return f"kill_switch_error: {e}"

    return None


@router.post("/test-call")
async def smartflo_test_call(
    request: Request,
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Place an outbound test call through Tata Smartflo Click-to-Call Support.

    Body (JSON):
        to (str, required):     Destination number (10-12 digit Indian number)
        caller_id (str, optional): DID to show to customer (defaults to TATA_SMARTFLO_DID)
        call_timeout (int, optional): Max call duration in seconds (default 300)
        niche (str, optional):  Niche key for voice bot (default from env SMARTFLO_DEFAULT_NICHE)

    The call uses Smartflo's Click-to-Call Support API:
      1. Smartflo dials the customer (first leg)
      2. Once customer answers, Smartflo bridges to the configured destination

    Requires: TATA_SMARTFLO_API_TOKEN + TATA_SMARTFLO_API_KEY in env.
    """
    client = TataSmartfloClient()
    if not client.available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Tata Smartflo not configured. "
                "Set TATA_SMARTFLO_API_TOKEN + TATA_SMARTFLO_API_KEY in .env."
            ),
        )

    # Parse body
    try:
        body = await request.json()
    except Exception:
        body = {}
    to_number = (body.get("to") or "").strip()
    if not to_number or len(to_number) < 8:
        raise HTTPException(status_code=422, detail="'to' is required (8-20 digit number)")

    caller_id = (body.get("caller_id") or "").strip() or None
    try:
        call_timeout = int(body.get("call_timeout") or 300)
    except (TypeError, ValueError):
        call_timeout = 300
    if call_timeout < 30 or call_timeout > 3600:
        call_timeout = 300
    niche = (body.get("niche") or "").strip() or os.environ.get(
        "SMARTFLO_DEFAULT_NICHE", "general"
    )

    # COMPLIANCE PRE-FLIGHT (TRAI/TCCCPR) — same gate sequence as
    # VobizClient.place_call (cf. app/api/telephony_vobiz.py:224). This endpoint
    # used to dial with no gate at all. Fail closed: block => no dial.
    block_reason = await _smartflo_dial_block_reason(to_number)
    if block_reason:
        logger.warning(
            f"Smartflo test-call blocked by compliance gate: {block_reason}"
        )
        return {
            "placed": False,
            "ref_id": None,
            "to": to_number,
            "caller_id": caller_id or client.did,
            "call_timeout": call_timeout,
            "smartflo_response": {"error": f"compliance_blocked: {block_reason}"},
            "status_code": 0,
            "next_steps": [
                "Call blocked by compliance gate (TCCCPR/TRAI) — not dialled.",
                f"Reason: {block_reason}",
                "Transactional calls are only allowed 09:00-21:00 IST.",
                "Check VOICE_LAUNCH_KILL / DIAL_TEST_MODE / COMPLIANCE_ALLOWLIST.",
            ],
        }

    # Place the call
    result = await client.place_call(
        to=to_number,
        caller_id=caller_id,
        call_timeout=min(max(call_timeout, 30), 3600),
        custom_identifier={
            "source": "admin_test",
            "niche": niche,
            "operator": user.email if hasattr(user, "email") else "admin",
        },
    )

    placed = (
        result.get("status_code") == 200
        and (result.get("body") or {}).get("success") is True
    )
    ref_id = (result.get("body") or {}).get("ref_id") if placed else None

    if not placed:
        logger.warning(f"Smartflo test-call not placed: {result}")

    return {
        "placed": placed,
        "ref_id": ref_id,
        "to": to_number,
        "caller_id": caller_id or client.did,
        "call_timeout": call_timeout,
        "smartflo_response": result.get("body"),
        "status_code": result.get("status_code"),
        "next_steps": (
            [
                "Call accepted by Smartflo.",
                f"Track via ref_id: {ref_id}" if ref_id else None,
                "Configure webhooks in Smartflo portal for call status updates.",
                "For conversational AI: set SMARTFLO_VOICE_STREAM_ENABLED=1",
                "and configure Voice Bot endpoint in Smartflo portal.",
            ]
            if placed
            else [
                "Check TATA_SMARTFLO_API_TOKEN / API_KEY are valid.",
                "Verify DID is active in Smartflo portal.",
                "Check Smartflo account balance/plan status.",
            ]
        ),
    }


# ---------------------------------------------------------------------------
# Status endpoint (admin)
# ---------------------------------------------------------------------------
@router.get("/status")
async def smartflo_status(user: User = Depends(require_admin)) -> dict[str, Any]:
    """Smartflo Voice Streaming config + capability snapshot."""
    try:
        from app.telephony import smartflo_stream as _ss

        streaming: dict[str, Any] = {
            "enabled": os.environ.get("SMARTFLO_VOICE_STREAM_ENABLED", "0") == "1",
            "stt_available": _ss.STT_AVAILABLE,
            "tts_available": _ss.TTS_AVAILABLE,
            "audioop": _ss._AUDIOOP_OK,
        }
    except Exception as e:
        streaming = {"error": str(e)}

    return {
        "provider": "tata_smartflo",
        "plan": "Smartflo Voice Streaming ₹1,100/concurrency/month",
        "wss_host": _wss_host(),
        "streaming": streaming,
        "env": {
            "SMARTFLO_VOICE_STREAM_ENABLED": os.environ.get(
                "SMARTFLO_VOICE_STREAM_ENABLED", "0"
            ),
            "SMARTFLO_WS_HOST": os.environ.get("SMARTFLO_WS_HOST", ""),
            "SMARTFLO_DEFAULT_NICHE": os.environ.get("SMARTFLO_DEFAULT_NICHE", "general"),
        },
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _client_ip_allowed(websocket: WebSocket, spec: str) -> bool:
    """True when the connecting peer falls inside ``spec`` (comma-separated IP/CIDR).

    Why (2026-09-11 audit): with ``SMARTFLO_WS_SECRET`` / ``SMARTFLO_WS_REQUIRE_SECRET``
    unset in production, the voice-stream endpoint accepted ANY internet client —
    and a single ``start`` frame drives real EdgeTTS/LLM spend plus a metered
    record. Tata's Voice Bot config only accepts a WSS URL, so there is no token
    to require; pinning the provider's egress is the practical control.

    Trust model: the app sits behind Caddy, so the transport peer is the proxy.
    We therefore read the **last** X-Forwarded-For hop — the one Caddy appends,
    which a client cannot forge. Earlier hops ARE attacker-controlled and are
    deliberately ignored, so ``X-Forwarded-For: <allowed>`` cannot smuggle a
    connection in.

    Fail-CLOSED: any parse/lookup error returns False, so a malformed allowlist
    can never silently degrade into an open door.
    """
    import ipaddress

    try:
        fwd = (websocket.headers.get("x-forwarded-for") or "").split(",")
        hops = [h.strip() for h in fwd if h.strip()]
        peer = ""
        try:
            peer = (websocket.client.host if websocket.client else "") or ""
        except Exception:
            peer = ""
        candidate = hops[-1] if hops else peer
        if not candidate:
            return False
        nets = [
            ipaddress.ip_network(p.strip(), strict=False)
            for p in spec.split(",")
            if p.strip()
        ]
        if not nets:
            return False
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return False
        return any(ip in n for n in nets)
    except Exception:
        return False


def _verify_hmac(token: str, secret: str) -> bool:
    """Verify an HMAC-SHA256 token. Format: <data>.<hex_signature>."""
    if not token or "." not in token:
        return False
    try:
        data, sig = token.rsplit(".", 1)
        expected = hmac.new(
            secret.encode(), data.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False


# Needed for _verify_hmac
import hashlib
import hmac
