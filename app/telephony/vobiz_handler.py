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
from typing import Any, Dict, Optional
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

    def _headers(self) -> Dict[str, str]:
        return {
            "X-Auth-ID": self.auth_id,
            "X-Auth-Token": self.auth_token,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _safe_body(resp: Any) -> Dict[str, Any]:
        try:
            body = resp.json()
            return body if isinstance(body, dict) else {"data": body}
        except Exception:
            return {"raw": (resp.text or "")[:500]}

    async def place_call(
        self,
        to: str,
        answer_url: str,
        from_: Optional[str] = None,
        **extra: Any,
    ) -> Dict[str, Any]:
        """POST {base}/Call/ — place an outbound call (capital C + trailing slash).

        ``from_`` defaults to vobiz_caller_id, then vobiz_sip_user. Extra
        kwargs are merged into the JSON body (future-proofing for field-name
        changes). Never raises.
        """
        payload: Dict[str, Any] = {
            "from": from_ or settings.vobiz_caller_id or settings.vobiz_sip_user,
            "to": to,
            "answer_url": answer_url,
        }
        payload.update(extra)
        try:
            import httpx  # lazy — keep module import light

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self.base_url}/Call/",
                    json=payload,
                    headers=self._headers(),
                )
            return {"status_code": resp.status_code, "body": self._safe_body(resp)}
        except Exception as e:
            logger.error(f"Vobiz place_call failed: {e}")
            return {"status_code": 0, "body": {"error": str(e)}}

    async def get_balance(self) -> Dict[str, Any]:
        """GET {base}/ — account details (incl. balance). Never raises."""
        try:
            import httpx  # lazy

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.base_url}/", headers=self._headers())
            return {"status_code": resp.status_code, "body": self._safe_body(resp)}
        except Exception as e:
            logger.error(f"Vobiz get_balance failed: {e}")
            return {"status_code": 0, "body": {"error": str(e)}}


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
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response>{speak}"
        '<Stream bidirectional="true" keepCallAlive="true" '
        'audioTrack="inbound" contentType="audio/x-l16;rate=16000">'
        f"{escape(ws_url or '')}</Stream></Response>"
    )
