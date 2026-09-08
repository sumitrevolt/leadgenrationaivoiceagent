"""
Webhooks API
(Stripe deleted 2026-07-10, Exotel+Razorpay removed 2026-06-18, Twilio removed 2026-07-07 —
payments via manual UPI; voice via Vobiz telephony/webhooks.py)
"""

import json
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


def _provision_minutes(
    client_id: str | None,
    plan_id: str | None = None,
    period_end: datetime | None = None,
    subscription_id: str | None = None,
    reset: bool = True,
) -> None:
    """Best-effort: refresh a client's plan calling-minutes after a paid pay/renew.

    Sets the client's plan (so the PLAN_MINUTES cap is right) and drops a usage
    watermark (mid-period renewal zeroes metered usage). NEVER raises — a billing
    hiccup must not 500 a provider webhook (Stripe would just retry).
    """
    try:
        if not client_id:
            return
        from app.billing import usage as _usage

        if plan_id:
            _usage.activate_plan(
                client_id, plan_id, subscription_id=subscription_id, period_end=period_end
            )
        if reset:
            _usage.reset_usage_period(client_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"webhook usage provisioning skipped for {client_id}: {e}")


# NOTE: Exotel webhooks removed 2026-06-18, Twilio webhooks removed 2026-07-07
# (provider is now Vobiz). The Vobiz answer/status callbacks live in
# app/telephony/webhooks.py (/vobiz/*).


# =============================================================================
# STRIPE WEBHOOKS — deleted 2026-07-10 (project me Stripe use nahi hota; payments
# via manual UPI only). The /stripe route, all handle_stripe_* handlers, and the
# Stripe Gateway class were removed. Reference: git history before this commit.
# =============================================================================


# =============================================================================
# RAZORPAY WEBHOOKS — removed 2026-06-18 (no online gateway; manual UPI only).
# The /razorpay route + all handle_razorpay_* handlers were deleted. The unified
# /billing/webhook now rejects X-Razorpay-Signature with 400.
# =============================================================================


# =============================================================================
# WHATSAPP CLOUD API WEBHOOK (Meta) — inbound replies -> reply_agent drafts
# =============================================================================
def _wa_verify_token() -> str:
    """Meta webhook GET-handshake token (settings -> env fallback)."""
    tok = ""
    try:
        tok = (settings.whatsapp_verify_token or "").strip()
    except Exception:
        tok = ""
    return tok or os.environ.get("WHATSAPP_VERIFY_TOKEN", "").strip()


@router.get("/whatsapp")
async def whatsapp_webhook_verify(request: Request):
    """Meta webhook verification handshake (echo hub.challenge if verify token matches).

    PUBLIC — Meta GETs this with hub.mode=subscribe&hub.verify_token=..&hub.challenge=..
    """
    from fastapi.responses import PlainTextResponse

    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    expected = _wa_verify_token()
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    return PlainTextResponse("verification_failed", status_code=403)


@router.post("/whatsapp")
async def whatsapp_webhook_inbound(request: Request):
    """Inbound WhatsApp messages from the official Meta Cloud API.

    - App-Secret signature verified (X-Hub-Signature-256); unconfigured -> allowed (warn).
    - Each inbound TEXT -> ``reply_agent.whatsapp_reply()`` => intent classify + Hinglish
      draft saved to ``data/reply_drafts.jsonl`` (1-click human send).
    - 'STOP' / 'UNSUBSCRIBE' / 'band karo' -> opt-out (suppress), no draft.
    - 'failed' delivery status -> recipient auto-suppressed (bounce protection).
    Always returns 200 JSON (Meta retries on non-2xx). NEVER raises.
    """
    raw = b""
    try:
        raw = await request.body()
    except Exception:
        pass

    try:
        from app.integrations.whatsapp import verify_meta_signature

        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get(
            "x-hub-signature-256"
        )
        verified = verify_meta_signature(raw, sig)
    except Exception as _ve:
        logger.error(f"whatsapp webhook: signature verification error: {_ve}")
        verified = False
    if not verified:
        logger.warning("whatsapp webhook: bad/unverified signature, ignoring payload")
        return {"ok": False, "reason": "bad_signature"}

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    res = {"ok": True, "messages": 0, "drafted": 0, "suppressed": 0, "statuses": 0}
    _opt_out = ("stop", "unsubscribe", "stop promotions", "band karo", "band kardo")
    try:
        from app.platform import reply_agent

        try:
            from app.marketing import wa_campaign_runner as _runner
        except Exception:
            _runner = None

        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = (change or {}).get("value", {}) or {}
                for msg in value.get("messages", []) or []:
                    res["messages"] += 1
                    frm = str(msg.get("from", "")).strip()
                    text = ""
                    if msg.get("type") == "text":
                        text = str((msg.get("text") or {}).get("body", "")).strip()
                    if text.lower() in _opt_out:
                        if _runner is not None:
                            try:
                                _runner.suppress(frm, reason="opt_out_inbound")
                            except Exception:
                                pass
                        # TCCCPR: revocation sab commercial comms pe — voice ledger bhi.
                        try:
                            from app.telephony.consent_ledger import record_opt_out

                            record_opt_out(frm, reason="wa_stop", channel="whatsapp")
                        except Exception:
                            pass
                        res["suppressed"] += 1
                        continue
                    # WhatsApp Flow response (nfm_reply type) -> lead capture
                    if msg.get("type") == "interactive":
                        interactive = msg.get("interactive") or {}
                        if interactive.get("type") == "nfm_reply":
                            try:
                                import json as _json

                                from app.marketing.whatsapp_flows import handle_flow_response

                                nfm = interactive.get("nfm_reply") or {}
                                resp_json = nfm.get("response_json") or "{}"
                                flow_data = (
                                    _json.loads(resp_json)
                                    if isinstance(resp_json, str)
                                    else resp_json
                                )
                                await handle_flow_response(flow_data, from_number=frm)
                            except Exception as e:
                                logger.info("wa flow response err: %s", e)

                    if text:
                        # Delivered paid customer ka reply = acknowledgment (council:
                        # 'delivered = acknowledged'). Read-side, message consume nahi karta.
                        try:
                            from app.marketing import customer_delivery

                            customer_delivery.try_mark_acknowledged(frm)
                        except Exception as e:
                            logger.debug("whatsapp ack-mark err: %s", e)
                        handled = False
                        try:
                            from app.marketing.onboarding import try_capture_onboarding_reply

                            handled = await try_capture_onboarding_reply(frm, text)
                        except Exception as e:
                            logger.debug("whatsapp onboarding-interview check err: %s", e)
                        if not handled:
                            try:
                                rec = await reply_agent.whatsapp_reply(frm, text, msg.get("id", ""))
                                if rec:
                                    res["drafted"] += 1
                            except Exception as e:
                                logger.info("whatsapp reply_agent err: %s", e)
                for st in value.get("statuses", []) or []:
                    res["statuses"] += 1
                    if st.get("status") == "failed" and _runner is not None:
                        recipient = str(st.get("recipient_id", "")).strip()
                        errs = st.get("errors") or []
                        reason = (
                            errs[0].get("title") if errs else "delivery_failed"
                        ) or "delivery_failed"
                        try:
                            _runner.record_failure(recipient, str(reason))
                        except Exception:
                            pass
    except Exception as e:
        logger.info("whatsapp webhook parse err: %s", e)
    return res
