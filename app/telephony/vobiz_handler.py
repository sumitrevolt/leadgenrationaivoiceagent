"""
Vobiz Telephony Handler
=======================

Vobiz (vobiz.ai) — India-native SIP trunk + voice REST API (Plivo-style).
Used as the primary P3 trunk (₹0.45/min raw SIP; this module covers the
Direct Call REST API so calls can be tested without FreeSWITCH).

API notes (IMPORTANT — discovered the hard way):
- Base:    https://api.vobiz.ai/api/v1/Account/{auth_id}
- Casing:  capital-A ``Account`` AND a TRAILING SLASH on the resource
  (e.g. ``POST {base}/Call/``) — lowercase or missing slash returns 401.
- Headers: ``X-Auth-ID`` / ``X-Auth-Token``.
- Call body (Plivo-like): {"from": ..., "to": ..., "answer_url": ...};
  field names may evolve, so extra kwargs are forwarded as-is.
- answer_url must return VobizXML: <Response><Speak>...</Speak><Hangup/></Response>.

Import-safe: no network at import time; httpx is imported lazily inside methods.
"""

import os
from typing import Any
from xml.sax.saxutils import escape

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

VOBIZ_API_ROOT = "https://api.vobiz.ai/api/v1/Account"


class VobizClient:
    """Thin async client for the Vobiz voice REST API. Methods never raise —
    they always return ``{"status_code": int, "body": dict}`` (status_code 0
    on transport/local errors)."""

    def __init__(self) -> None:
        self.auth_id = settings.vobiz_auth_id
        self.auth_token = settings.vobiz_auth_token
        self.base_url = f"{VOBIZ_API_ROOT}/{self.auth_id}"

    def available(self) -> bool:
        """True when account credentials are configured."""
        return bool(self.auth_id and self.auth_token)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Auth-ID": self.auth_id,
            "X-Auth-Token": self.auth_token,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_body(resp: Any) -> dict[str, Any]:
        try:
            body = resp.json()
            return body if isinstance(body, dict) else {"data": body}
        except Exception:
            return {"raw": (resp.text or "")[:500]}

    async def place_call(
        self,
        to: str,
        answer_url: str,
        from_: str | None = None,
        call_type: str = "transactional",
        skip_compliance: bool = False,
        **extra: Any,
    ) -> dict[str, Any]:
        """POST {base}/Call/ — place an outbound call (capital C + trailing slash).

        COMPLIANCE: every call first passes the ComplianceGate (DND + calling
        hours + DLT/140 for promotional; lenient for transactional). A blocked
        call is NEVER dialled — it returns ``{"status_code": 0, "blocked": True,
        "compliance": {...}}`` so the caller can surface the reason. Pass
        ``skip_compliance=True`` only for internal/non-dialing flows.

        ``from_`` defaults to vobiz_caller_id, then vobiz_sip_user. Extra
        kwargs are merged into the JSON body (future-proofing for field-name
        changes). Never raises.
        """
        # Test-mode allowlist (USER-MANDATE 2026-07-05): promotional calls sirf
        # approved numbers pe jab tak owner test-mode off na kare. Compliance
        # gate se PEHLE — blocked dial pe DND-lookup/API cost bhi nahi lagti.
        # skip_compliance isse bypass NAHI karta (paisa-burn gate hai, compliance
        # convenience nahi).
        try:
            from app.telephony import dial_gate

            allowed, reason = dial_gate.check(to, call_type)
            if not allowed:
                logger.warning(f"Vobiz place_call blocked by dial_gate: {reason} (to={to[-4:]:>4})")
                return {
                    "status_code": 0,
                    "blocked": True,
                    "body": {"error": "blocked_by_dial_test_mode", "reason": reason},
                }
        except Exception as e:
            if (call_type or "").lower() == "promotional":
                logger.error(f"Vobiz place_call: dial_gate error on promo call ({e}) — blocking.")
                return {
                    "status_code": 0,
                    "blocked": True,
                    "body": {"error": "dial_gate_error", "detail": str(e)},
                }
        if not skip_compliance:
            try:
                from app.telephony.compliance import CallType, get_compliance_gate

                ct = (
                    CallType(call_type)
                    if call_type in (c.value for c in CallType)
                    else CallType.TRANSACTIONAL
                )
                decision = await get_compliance_gate().check(to, ct)
                if not decision.allowed:
                    logger.warning(f"Vobiz place_call blocked by compliance: {decision.reasons}")
                    return {
                        "status_code": 0,
                        "blocked": True,
                        "compliance": decision.as_dict(),
                        "body": {"error": "blocked_by_compliance", "reasons": decision.reasons},
                    }
            except Exception as e:
                # Gate failure must not silently allow promo dialing.
                if (call_type or "").lower() == "promotional":
                    logger.error(
                        f"Vobiz place_call: compliance gate error on promo call ({e}) — blocking."
                    )
                    return {
                        "status_code": 0,
                        "blocked": True,
                        "body": {"error": "compliance_gate_error", "detail": str(e)},
                    }
                logger.debug(f"Vobiz place_call: compliance gate skipped ({e}).")
        payload: dict[str, Any] = {
            "from": from_ or settings.vobiz_caller_id or settings.vobiz_sip_user,
            "to": to,
            "answer_url": answer_url,
        }
        payload.update(extra)
        try:
            import httpx  # lazy — keep module import light

            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.post(
                    f"{self.base_url}/Call/",
                    json=payload,
                    headers=self._headers(),
                )
            return {"status_code": resp.status_code, "body": self._safe_body(resp)}
        except Exception as e:
            # type(e).__name__ zaroori — kai httpx exceptions ka str() blank hota
            # (live: "Vobiz get_balance failed: " undiagnosable tha)
            _err = f"{type(e).__name__}: {e}".rstrip(": ")
            logger.error(f"Vobiz place_call failed: {_err}")
            return {"status_code": 0, "body": {"error": _err}}

    async def get_balance(self) -> dict[str, Any]:
        """GET {base}/ — account details (incl. balance). Never raises.

        2026-07-19: split timeout (connect=5s, read=10s) — pehle 15s total timeout
        se ConnectTimeout har hourly watchdog run pe noise + no balance evidence
        milta tha. Ab connect fail-fast hoga (5s) aur recurring transport errors
        warning level pe log hote hain (error spam kam, signal same).
        """
        try:
            import httpx  # lazy

            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0),
                follow_redirects=True,
            ) as client:
                resp = await client.get(f"{self.base_url}/", headers=self._headers())
            return {"status_code": resp.status_code, "body": self._safe_body(resp)}
        except Exception as e:
            _err = f"{type(e).__name__}: {e}".rstrip(": ")
            # Recurring ConnectTimeout/transport errors = warning (not error).
            # Known Vobiz API reachability issue — operator-action, not a code bug.
            _is_transport = any(
                t in type(e).__name__
                for t in ("Timeout", "ConnectError", "ConnectTimeout", "NetworkError")
            )
            if _is_transport:
                logger.warning(f"Vobiz get_balance transport error (recurring?): {_err}")
            else:
                logger.error(f"Vobiz get_balance failed: {_err}")
            return {"status_code": 0, "body": {"error": _err}}


def build_speak_xml(text: str, voice: str = "female", language: str = "en-IN") -> str:
    """
    Minimal VobizXML: speak the text, then hang up.
    NOTE (live-call debug 2026-06-07): voice/language ATTRIBUTES hatane pade —
    unsupported attribute values par Vobiz Speak silently skip karke Hangup
    chala deta tha ("call aayi aur turant kat gayi"). Docs ka minimal format:
    <Response><Speak>text</Speak><Hangup/></Response>
    """
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response><Speak>"
        f"{escape(text or '')}"
        "</Speak><Hangup/></Response>"
    )


def build_stream_xml(ws_url: str, greeting: str = "") -> str:
    """
    VobizXML that bridges the live call to a WebSocket for two-way streaming
    (conversational AI). Vobiz opens ``ws_url``, streams the caller's audio to
    us and plays back the audio we stream over the same socket.

    Format (per docs.vobiz.ai/xml/stream + /xml/stream/play-audio):
        <Response>[<Speak>greeting</Speak>]<Stream bidirectional="true"
            keepCallAlive="true" audioTrack="inbound"
            contentType="audio/x-l16;rate=16000">wss://...</Stream></Response>

    CRITICAL <Stream> attributes (root cause of the old "call connects then
    instantly hangs up" bug — a bare <Stream> defaults to keepCallAlive=false
    and bidirectional=false):
      * keepCallAlive="true"  — KEEPS THE CALL ALIVE while we stream. Without
        it Vobiz tears the PSTN call down the moment the verb is set up
        (this is the instant-hangup fix).
      * bidirectional="true"  — lets us send audio BACK (playAudio) over the WS.
      * audioTrack="inbound"   — stream the caller's audio to us.
      * contentType="audio/x-l16;rate=16000" — Linear PCM 16-bit LE @16 kHz,
        chosen so NO µ-law conversion is needed on EITHER leg (STT already
        wants 16 kHz, and we send L16 straight back).

    The optional leading <Speak> plays a one-shot greeting BEFORE the stream
    opens; normally left empty because the bot greets over the socket itself.
    """
    speak = f"<Speak>{escape(greeting.strip())}</Speak>" if (greeting and greeting.strip()) else ""
    # audioTrack env-overridable (VOBIZ_AUDIO_TRACK): "inbound" = caller's audio only
    # (correct per docs, default).
    #
    # 2026-06-22: observed inbound_frames=0 on a 54s answered call despite Vobiz
    # ACKing tracks:['inbound'] in the start event (bot connects + speaks fine,
    # never hears the caller).
    # 2026-07-02 REAL-CALL TEST (do not retry): audioTrack="both" was tried live
    # against 8261030181 — made it STRICTLY WORSE. Vobiz's own call-detail API
    # (GET {base}/Call/{uuid}/) showed answer_time == end_time, bill_duration=0,
    # hangup_source="Vobiz" — Vobiz answers the call then immediately hangs up
    # itself, i.e. it does not accept/like audioTrack="both" at all (2 calls in a
    # row, 100% reproduction). Reverted to "inbound" same session (restores the
    # "connects but deaf" baseline). DO NOT set VOBIZ_AUDIO_TRACK=both again
    # without confirming with Vobiz support first — it is confirmed harmful, not
    # just untested. The inbound-deaf root cause is still OPEN; next diagnostic
    # step is inspecting raw WS frames on a live call for non-JSON/malformed
    # media frames (see _on_event's "non-JSON frame" warning), or escalating to
    # Vobiz support with the start-event tracks:['inbound'] ACK + zero-frames
    # evidence — not further guessing at XML attribute values (costs a real call
    # each time).
    track = (os.environ.get("VOBIZ_AUDIO_TRACK", "inbound") or "inbound").strip() or "inbound"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{speak}"
        '<Stream bidirectional="true" keepCallAlive="true" '
        f'audioTrack="{escape(track)}" contentType="audio/x-l16;rate=16000">'
        f"{escape(ws_url or '')}</Stream></Response>"
    )
