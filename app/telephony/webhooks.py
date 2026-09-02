"""
Telephony Webhooks
FastAPI routes for handling telephony provider callbacks.

Vobiz answer/status callbacks are public, minimal handlers (no signed payload
from Vobiz). (Exotel removed 2026-06-18, Twilio removed 2026-07-07 — provider
is now Vobiz-only.)

Handlers + the shared CallManager are lazy-initialised so importing this module (to
mount the router) can never crash app startup — CallManager() raises on an unknown
provider, so it must not run at import time.
"""

from fastapi import APIRouter, Request
from fastapi.responses import Response

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Lazy singletons (no heavy work at import time)
# --------------------------------------------------------------------------- #
_call_manager = None


def _get_call_manager():
    global _call_manager
    if _call_manager is None:
        try:
            from app.telephony.call_manager import CallManager

            _call_manager = CallManager()
        except Exception as e:  # unknown provider / config — don't crash the webhook
            logger.error(f"CallManager init failed: {e}")
            return None
    return _call_manager


# --------------------------------------------------------------------------- #
# Vobiz callbacks (provider since 2026-06-18). Vobiz does not sign callbacks, so
# these are minimal public handlers. The live conversational path is the Vobiz
# stream WS (/api/telephony/vobiz/stream/{token}); call_manager points outbound
# answer_url/status at /api/webhooks/vobiz/answer + /vobiz/status.
# --------------------------------------------------------------------------- #
@router.post("/vobiz/status")
async def vobiz_status_webhook(request: Request):
    """Vobiz status callback — marks a completed call done (minute-metering +
    qualified-lead billing run via CallManager.handle_call_completed). Idempotent
    on call_id. Best-effort; never raises a 500.

    Security note: Vobiz does not sign this callback, and the status-callback URL
    is configured account-wide (not per-call), so it cannot carry a per-call HMAC
    token the way /vobiz/answer does. The real defenses are: (1) call_id is a
    random UUID (128-bit, unguessable) and handle_call_completed() no-ops if it
    isn't a call WE placed and is still tracked in active_calls; (2) the duration
    clamp below bounds how much a forged/replayed POST can inflate billed minutes
    even if an attacker did learn a live call_id.
    """
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    call_sid = (
        form_data.get("CallSid")
        or form_data.get("CallUUID")
        or form_data.get("call_uuid")
        or form_data.get("RequestUUID")
        or form_data.get("id")
    )
    status = (
        form_data.get("Status") or form_data.get("CallStatus") or form_data.get("call_status") or ""
    ).lower()
    hangup_cause = (
        form_data.get("HangupCause")
        or form_data.get("HangupCauseName")
        or form_data.get("hangup_cause")
        or ""
    )
    duration_raw = form_data.get("Duration") or form_data.get("duration")
    recording_url = form_data.get("RecordingUrl") or form_data.get("recording_url")
    call_id = form_data.get("CallbackData") or form_data.get("call_id") or call_sid

    # ENTERPRISE FIX (2026-07-10): pre-fix, CallbackData was NEVER sent to Vobiz
    # (call_manager.py:358), so this field was always empty and webhook resolved
    # to CallSid (Vobiz's own opaque ID) — handle_call_completed() NEVER found
    # a matching active_calls entry. Voice billing ran 0 times for ALL real calls.
    # Now: (1) CallbackData is sent with push, (2) sid→call_id Redis fallback.
    if not call_id or call_id == call_sid:
        try:
            from app.telephony.call_state import get_call_store

            mapped = await get_call_store()._sid_map_get(call_sid or "")
            if mapped:
                logger.info(f"Vobiz status: resolved CallSid {call_sid} → internal {mapped}")
                call_id = mapped
        except Exception:
            pass

    logger.info(
        f"Vobiz status webhook - SID: {call_sid}, Status: {status}, HangupCause: {hangup_cause}"
    )

    # Controlled-launch disposition tally (NUP/busy/failed/answered…) for admin
    # visibility + daily analytics. Best-effort, never blocks the webhook.
    # Prefer HangupCause when CallStatus is generic "completed" — otherwise
    # every hangup looks like ANSWERED and NUP/no_answer vanish from metrics.
    try:
        from app.telephony import voice_launch as _vl

        disp_token = (hangup_cause or status or "").strip()
        if disp_token:
            await _vl.record_disposition(disp_token, "campaign")
            # Session-scoped disposition tally (used/remaining ke saath visibility).
            # Best-effort; attribute current session (async completion late aaye to
            # current session pe count ho sakta hai — visibility, billing nahi).
            await _vl.record_session_disposition(None, disp_token)
    except Exception:
        pass

    try:
        if status in ("completed", "complete", "answered", "hangup"):
            # Idempotency: dedup on call_id so metering/billing run exactly once.
            try:
                from app.billing import idempotency as _idem

                if call_id and await _idem.seen_before(f"call_done:{call_id}"):
                    logger.info(f"Vobiz duplicate completion skipped: {call_id}")
                    return {"status": "duplicate_skipped"}
            except Exception:
                pass

            # Clamp an implausible/forged duration to the configured call-length
            # ceiling — bounds billing-inflation blast-radius from a guessed call_id.
            try:
                from app.config import settings

                duration = max(0, int(duration_raw)) if duration_raw else 0
                cap = int(getattr(settings, "max_call_duration_seconds", 300) or 300)
                if duration > cap:
                    logger.warning(
                        f"Vobiz status duration {duration}s exceeds cap {cap}s for "
                        f"call {call_id} — clamping."
                    )
                    duration = cap
            except Exception:
                duration = 0

            cm = _get_call_manager()
            result = None
            if cm is not None and call_id:
                result = await cm.handle_call_completed(
                    call_id=call_id,
                    duration=duration,
                    recording_url=recording_url,
                )
            if result:
                logger.info(f"Vobiz call completed - Outcome: {result.outcome}")

            # Clean up the sid→call_id reverse mapping (TTL: ~4h on the Redis key
            # would be better, but for now explicit delete is safe — once the call
            # is done we don't need to reverse-lookup again).
            try:
                from app.telephony.call_state import get_call_store

                _store2 = get_call_store()
                await _store2._sid_map_del(call_sid or "")
            except Exception:
                pass

        return {"status": "received"}
    except Exception as e:
        logger.error(f"Vobiz status webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/vobiz/answer")
async def vobiz_answer_webhook(request: Request):
    """Vobiz answer_url — returns VobizXML when a call connects.

    Default best-effort: AI-disclosure greeting then hang up (the full
    conversational loop runs over the Vobiz stream WS, not this answer_url).
    Press-9 opt-out is persisted cross-channel (TCCCPR) when Vobiz posts a digit.
    """
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    digits = str(form_data.get("digits") or form_data.get("Digits") or "").strip()
    call_sid = form_data.get("CallSid") or form_data.get("call_uuid") or ""

    if digits == "9":
        # SECURITY: suppress the number we SIGNED into the answer-url (call_manager),
        # NOT the request 'From' (attacker-controllable). A valid signature proves this
        # callback belongs to a call we placed; an unsigned/forged press-9 is ignored so
        # an anonymous POST can't add arbitrary numbers to the do-not-call list.
        from app.telephony.answer_token import verify as _verify_answer

        _q = request.query_params
        _signed_to = str(_q.get("to") or "").strip()
        if _signed_to and _verify_answer(_signed_to, _q.get("exp", ""), _q.get("sig", "")):
            try:
                from app.telephony.consent_ledger import record_opt_out

                record_opt_out(
                    _signed_to, reason="ivr_press9", channel="voice", call_id=str(call_sid or "")
                )
            except Exception as _oe:
                logger.error(f"press-9 opt-out persist failed: {_oe}")
        else:
            logger.warning(
                "press-9 opt-out IGNORED — unsigned/forged answer callback (no valid token)"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Speak>"
            "Aapka number hamare calling list se hata diya gaya hai. Dhanyavad."
            "</Speak><Hangup/></Response>"
        )
    else:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Speak>"
            "Namaste. Main ek AI assistant bol rahi hoon."
            "</Speak><Hangup/></Response>"
        )

    return Response(content=xml, media_type="application/xml")


@router.post("/vobiz/inbound")
async def vobiz_inbound_webhook(request: Request):
    """Inbound / no-answer / missed Vobiz call → lead capture (+ gated AI callback).

    Wire this as the Vobiz inbound-DID webhook (and/or the no-answer/hangup
    callback on an unanswered inbound call). It captures the caller as a lead
    ALWAYS, and — when MISSED_CALL_CALLBACK=1 + a Vobiz DID is configured —
    triggers a transactional AI callback (caller rang us first, so ban-safe).

    Lead capture works NOW (no DID needed); the callback leg is flag-gated and
    inert without a DID. Best-effort; never raises a 500. Public (Vobiz does not
    sign callbacks). Mirrors the existing admin test route
    POST /api/growth/missed-call → missed_call.handle_missed_call.
    """
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    # Vobiz inbound payloads vary; accept the common caller-number field names.
    from_number = str(
        form_data.get("From")
        or form_data.get("CallFrom")
        or form_data.get("from")
        or form_data.get("caller")
        or form_data.get("Caller")
        or ""
    ).strip()
    # Optional context (best-effort): niche/business may be passed as query/extra.
    niche = (
        str(form_data.get("niche") or request.query_params.get("niche") or "general").strip()
        or "general"
    )
    business = str(form_data.get("business") or request.query_params.get("business") or "").strip()
    status = str(form_data.get("Status") or form_data.get("call_status") or "").lower()

    logger.info(f"Vobiz inbound webhook - From: {from_number}, Status: {status}")

    if not from_number:
        logger.warning("Vobiz inbound webhook: caller number missing in payload")
        return {"status": "received", "captured": False, "reason": "no caller number"}

    try:
        from app.telephony.missed_call import handle_missed_call

        result = await handle_missed_call(from_number, niche, business)
        return {"status": "received", **(result if isinstance(result, dict) else {})}
    except Exception as e:
        logger.error(f"Vobiz inbound webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def telephony_health():
    """Health check for telephony system"""
    cm = _get_call_manager()
    if cm is None:
        return {"status": "degraded", "provider": None, "stats": {}}
    return {"status": "healthy", "provider": cm.provider.value, "stats": cm.get_stats()}
