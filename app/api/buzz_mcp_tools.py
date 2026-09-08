"""Buzz outbound MCP tools — voice / WhatsApp / email as safe /mcp-exposed tools.

fastapi-mcp mount (app/main.py) `include_tags=[\"Platform\", ..., \"Agents\"]`
se tools select hota hai, isliye routes tags={\"Platform\",\"Agents\"} rakhe
hain = Claude/Hermes/Buzz MCP clients inhe direct tools ki tarah call kar
sakte hain.

Safety rails (Enterprise Control Plane contract, t_97ecbdac):
- **dry_run MANDATORY param** — default True; True pe input validation +
  suppression check chalte hain par KOI real send nahi hota.
- **Deterministic idempotency** — ``AgentRuntimeIdempotency`` sha256(tool,
  target, payload) key se Redis SETNX lock (24h TTL) rakhta hai; retried
  call duplicate send produce NAHI karti, structured ``duplicate`` reply
  deti hai.
- **Per-channel rate limits** — voice 10/hour, WhatsApp 15/min, email
  25/day (outreach cap §7). Limit cross = structured 429-shape refusal.
- **DND/DPDP suppression fail-CLOSED** — ``email_unsub`` ledger se check;
  unresolvable authority = suppressed (outage is not consent).
- **Real sends INERT by default** — ``BUZZ_MCP_REAL_SEND=1`` env ke bina
  live send attempt refuse hota hai (dry-run-only posture). Ye compliance
  gates ko touch nahi karta — upar ki extra layer hai.

Auth double-layered: route-level ``require_admin`` + /mcp middleware ka
Bearer/IP gate (fail-closed prod) — ``ops_mcp_tools.py`` jaisa hi.

Rollback: main.py se is router ka include-block hatao (single line).

Added 2026-08-25 (CTRL-P0-D2 rework, t_574a3fbe).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/buzz",
    tags=["Platform", "Agents"],
)

# ---------------------------------------------------------------------------
# Per-channel rate limits (contract): (max_requests, window_seconds)
# ---------------------------------------------------------------------------
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "voice": (10, 3600),
    "whatsapp": (15, 60),
    "email": (25, 86400),
}


def _real_send_armed() -> bool:
    """True only when BUZZ_MCP_REAL_SEND=1. INERT-by-default posture."""
    import os

    return os.getenv("BUZZ_MCP_REAL_SEND", "").strip() == "1"


def _payload_fingerprint(channel: str, target: str, body: dict[str, Any]) -> str:
    """Stable sha256 of (channel, normalized target, sorted payload)."""
    blob = json.dumps(
        {"channel": channel, "target": target, "body": body}, sort_keys=True, default=str
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class AgentRuntimeIdempotency:
    """Redis SETNX-backed idempotency guard for agent-initiated outbound sends.

    Deterministic keys (sha256 of channel+target+payload) so a RETRIED call
    maps to the SAME key and cannot double-send. Redis unavailable →
    **fail-closed** for real sends (an outage must never cause duplicates),
    dry-run me guard skip hota hai kyunki wahan kuch bheja hi nahi ja raha.
    """

    TTL_SECONDS = 24 * 3600

    def __init__(self, channel: str) -> None:
        self.channel = channel

    async def _client(self):  # pragma: no cover - thin wrapper
        from app.cache import get_redis_client

        return await get_redis_client()

    @staticmethod
    def make_key(channel: str, fingerprint: str) -> str:
        return f"buzz:mcp:idem:{channel}:{fingerprint}"

    async def check_and_claim(self, fingerprint: str) -> tuple[bool, str]:
        """(acquired, reason). acquired=False ⇒ duplicate/in-flight."""
        try:
            client = await self._client()
            key = self.make_key(self.channel, fingerprint)
            ok = await client.set(key, "1", nx=True, ex=self.TTL_SECONDS)
            if not ok:
                return False, "duplicate_send_blocked"
            return True, ""
        except Exception as exc:
            logger.warning("[buzz_mcp] idempotency store unavailable: %s", exc)
            return False, "idempotency_store_unavailable"

    async def release(self, fingerprint: str) -> None:
        """Best-effort release on a failed pre-send gate so a legit retry can pass."""
        try:
            client = await self._client()
            await client.delete(self.make_key(self.channel, fingerprint))
        except Exception:  # pragma: no cover - best effort
            pass


async def _check_suppression(channel: str, *, email: str = "", phone: str = "") -> tuple[bool, str]:
    """(allowed, state_or_reason). Fail-CLOSED via email_unsub ledger."""
    from app.platform.email_unsub import STATE_NONE, suppression_state

    if channel == "email":
        state = suppression_state(email=email, channel="email")
    else:
        state = suppression_state(phone=phone, channel="whatsapp")
    if state == STATE_NONE:
        return True, ""
    return False, f"suppressed:{state}"


async def _check_rate_limit(channel: str) -> tuple[bool, str]:
    """Sliding-window counter per channel. Fail-CLOSED on store errors."""
    max_req, window = RATE_LIMITS[channel]
    try:
        from app.cache import get_redis_client

        client = await get_redis_client()
        key = f"buzz:mcp:rl:{channel}"
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window)
        if count > max_req:
            return False, f"rate_limited:{channel}:{max_req}/{window}s"
        return True, ""
    except Exception as exc:
        logger.warning("[buzz_mcp] rate-limit store unavailable: %s", exc)
        return False, "rate_limit_store_unavailable"


class BuzzToolResult(BaseModel):
    ok: bool
    dry_run: bool
    channel: str
    detail: str = ""
    idempotency_key: str = ""


# ---------------------------------------------------------------------------
# Shared pre-send pipeline: validate -> suppress -> rate-limit -> idempotency
# ---------------------------------------------------------------------------
async def _pre_send(
    channel: str,
    target: str,
    payload_body: dict[str, Any],
    *,
    dry_run: bool,
) -> BuzzToolResult | None:
    """None = all gates passed (proceed); BuzzToolResult = structured refusal."""
    # 1) Suppression (DND/DPDP) — fail-closed, cheapest identity check first.
    allowed, reason = await _check_suppression(
        channel, email=(target if channel == "email" else ""), phone=target
    )
    if not allowed:
        return BuzzToolResult(ok=False, dry_run=dry_run, channel=channel, detail=reason)

    # 2) Per-channel rate limit.
    allowed, reason = await _check_rate_limit(channel)
    if not allowed:
        return BuzzToolResult(ok=False, dry_run=dry_run, channel=channel, detail=reason)

    # 3) Idempotency claim (real sends only — dry-run sends nothing to claim).
    if not dry_run:
        fp = _payload_fingerprint(channel, target, payload_body)
        idem = AgentRuntimeIdempotency(channel)
        acquired, reason = await idem.check_and_claim(fp)
        if not acquired:
            return BuzzToolResult(
                ok=False,
                dry_run=False,
                channel=channel,
                detail=reason,
                idempotency_key=AgentRuntimeIdempotency.make_key(channel, fp),
            )
    return None


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------
class VoiceCallIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    call_type: str = Field(default="promotional", pattern="^(promotional|transactional)$")
    script_note: str = Field(default="", max_length=500)
    dry_run: bool = True


class WhatsAppIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20)
    message: str = Field(min_length=1, max_length=2000)
    dry_run: bool = True


class EmailIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    dry_run: bool = True


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@router.post("/voice-call", operation_id="buzz_voice_call")
async def buzz_voice_call(body: VoiceCallIn, _user=Depends(require_admin)) -> dict[str, Any]:
    """Place an outbound AI voice call through the unified telephony service."""
    fp = _payload_fingerprint("voice", body.phone, {"call_type": body.call_type})
    idem_key = AgentRuntimeIdempotency.make_key("voice", fp)

    refusal = await _pre_send(
        "voice", body.phone, {"call_type": body.call_type}, dry_run=body.dry_run
    )
    if refusal:
        return refusal.model_dump()

    if body.dry_run:
        return BuzzToolResult(
            ok=True,
            dry_run=True,
            channel="voice",
            detail="dry_run_ok",
            idempotency_key=idem_key,
        ).model_dump()

    if not _real_send_armed():
        return BuzzToolResult(
            ok=False, dry_run=False, channel="voice", detail="real_send_not_armed"
        ).model_dump()

    from app.telephony.telephony_service import get_telephony_service

    result = await get_telephony_service().place_call(
        to_number=body.phone, call_type=body.call_type
    )
    return {
        "ok": result.status in ("initiated", "connected"),
        "dry_run": False,
        "channel": "voice",
        "detail": f"call_id={result.call_id} status={result.status}",
        "idempotency_key": idem_key,
    }


@router.post("/whatsapp-message", operation_id="buzz_whatsapp_message")
async def buzz_whatsapp_message(body: WhatsAppIn, _user=Depends(require_admin)) -> dict[str, Any]:
    """Send a WhatsApp text via the self-hosted WAHA session (§5 ban-safety gated)."""
    fp = _payload_fingerprint("whatsapp", body.phone, {"message": body.message})
    idem_key = AgentRuntimeIdempotency.make_key("whatsapp", fp)

    refusal = await _pre_send(
        "whatsapp", body.phone, {"message": body.message}, dry_run=body.dry_run
    )
    if refusal:
        return refusal.model_dump()

    if body.dry_run:
        return BuzzToolResult(
            ok=True,
            dry_run=True,
            channel="whatsapp",
            detail="dry_run_ok",
            idempotency_key=idem_key,
        ).model_dump()

    if not _real_send_armed():
        return BuzzToolResult(
            ok=False, dry_run=False, channel="whatsapp", detail="real_send_not_armed"
        ).model_dump()

    from app.integrations.whatsapp_selfhost import SelfHostWhatsApp

    resp = await SelfHostWhatsApp().send_text_message(body.phone, body.message)
    err = resp.get("error")
    return {
        "ok": not err,
        "dry_run": False,
        "channel": "whatsapp",
        "detail": err or "sent",
        "idempotency_key": idem_key,
    }


@router.post("/email-send", operation_id="buzz_email_send")
async def buzz_email_send(body: EmailIn, _user=Depends(require_admin)) -> dict[str, Any]:
    """Send a transactional email via Resend/Brevo (email_unsub headers attached)."""
    fp = _payload_fingerprint("email", body.email, {"subject": body.subject})
    idem_key = AgentRuntimeIdempotency.make_key("email", fp)

    refusal = await _pre_send(
        "email", body.email, {"subject": body.subject}, dry_run=body.dry_run
    )
    if refusal:
        return refusal.model_dump()

    if body.dry_run:
        return BuzzToolResult(
            ok=True,
            dry_run=True,
            channel="email",
            detail="dry_run_ok",
            idempotency_key=idem_key,
        ).model_dump()

    if not _real_send_armed():
        return BuzzToolResult(
            ok=False, dry_run=False, channel="email", detail="real_send_not_armed"
        ).model_dump()

    from app.integrations import email_api

    ok, info = await email_api.send_email_api([body.email], body.subject, body.body)
    return {
        "ok": bool(ok),
        "dry_run": False,
        "channel": "email",
        "detail": info or ("sent" if ok else "send_failed"),
        "idempotency_key": idem_key,
    }
