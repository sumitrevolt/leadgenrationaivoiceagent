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
    try:
        from app.integrations.whatsapp import verify_webhook_token

        ok = mode == "subscribe" and verify_webhook_token(token, _wa_verify_token())
    except Exception as _e:  # pragma: no cover - defensive
        logger.warning(f"whatsapp webhook verify: token check failed ({_e}) -> deny")
        ok = False
    if ok:
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
# =============================================================================
# TELEGRAM BOT WEBHOOK — inbound owner/admin updates -> durable inbox
# P0 2026-09-16: /api/webhooks/telegram was HTTP 405 on prod (no POST handler),
# so every inbound Telegram update was silently dropped. This endpoint fixes
# that. Conventions mirror the WhatsApp inbound block above: 200-fast, never
# raises, secret fail-closed when TELEGRAM_WEBHOOK_SECRET is set, dedup by
# update_id, and durable persist so no update is lost even when downstream
# consumers (telegram_ingress / reply routing) are gated off.
# =============================================================================
_telegram_seen: set = set()
_telegram_seen_max = 5000


def _telegram_secret() -> str:
    """Telegram webhook secret (settings -> env fallback). Empty = unconfigured."""
    tok = getattr(settings, "telegram_webhook_secret", "") or ""
    if not tok:
        tok = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    return str(tok).strip()


def _telegram_inbox_path() -> str:
    return os.path.join("data", "telegram_inbox.jsonl")


@router.get("/telegram")
async def telegram_webhook_verify():
    """URL registration check. Some bot tooling GETs the webhook URL before
    registering; return 200 so registration does not fail. Inbound updates
    arrive via POST (handled below)."""
    return {"ok": True, "note": "use POST for updates"}


@router.post("/telegram")
async def telegram_webhook_inbound(request: Request):
    """Inbound Telegram bot updates.

    - Secret verified via ``X-Telegram-Bot-Api-Secret-Token`` (or ``?secret=``)
      when ``TELEGRAM_WEBHOOK_SECRET`` is configured; a mismatch is REFUSED with
      403 (fail-closed). When unconfigured, updates are accepted + a warning is
      logged (consistent with the WhatsApp endpoint) so the surface is never a
      silent black hole.
    - ``update_id`` dedup (bounded) so Telegram retries do not double-process.
    - Every inbound update is durably appended to ``data/telegram_inbox.jsonl``
      so it is NEVER silently dropped, even when downstream consumers are gated.
    - 'STOP' / 'UNSUBSCRIBE' / 'band karo' -> opt-out (cross-channel
      suppression via the consent ledger).
    Always returns 200 JSON (Telegram retries on non-2xx). NEVER raises.
    """
    raw = b""
    try:
        raw = await request.body()
    except Exception:
        pass

    # --- signature / secret (fail-closed when configured) ---
    secret_cfg = _telegram_secret()
    if secret_cfg:
        import hmac as _hmac
        provided = (
            request.headers.get("X-Telegram-Bot-Api-Secret-Token")
            or request.headers.get("x-telegram-bot-api-secret-token")
            or request.query_params.get("secret", "")
        ).strip()
        if not _hmac.compare_digest(provided, secret_cfg):
            logger.warning("telegram webhook: bad/unmatched secret, refusing update")
            return {"ok": False, "reason": "bad_secret"}

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    update_id = payload.get("update_id")

    # --- dedup (bounded; Telegram retries reuse the same update_id) ---
    if isinstance(update_id, int):
        if update_id in _telegram_seen:
            return {"ok": True, "dedup": True, "update_id": update_id}
        _telegram_seen.add(update_id)
        if len(_telegram_seen) > _telegram_seen_max:
            _telegram_seen.clear()

    # --- durable persist (never silently drop) ---
    try:
        os.makedirs(os.path.dirname(_telegram_inbox_path()) or ".", exist_ok=True)
        with open(_telegram_inbox_path(), "a", encoding="utf-8") as _f:
            _f.write(json.dumps({"ts": datetime.now().isoformat(), "update": payload}) + "\n")
    except Exception as _e:  # pragma: no cover - defensive
        logger.warning(f"telegram webhook: inbox persist failed: {_e}")

    # --- extract chat + text ---
    res = {"ok": True, "update_id": update_id, "opt_out": False}
    msg = payload.get("message") or payload.get("edited_message") or {}
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = str(msg.get("text", "")).strip()

    _opt_out = ("stop", "unsubscribe", "stop promotions", "band karo", "band kardo", "stop calling")
    if text.lower() in _opt_out:
        try:
            from app.telephony.consent_ledger import record_opt_out
            record_opt_out(str(chat_id), reason="tg_stop", channel="telegram")
        except Exception:
            pass
        res["opt_out"] = True
    return res
