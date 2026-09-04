"""WhatsApp Cloud API admin + webhook routes (OFFICIAL Meta Cloud API only).

Mounted at ``/api`` -> all paths here live under ``/api/wa/*``.

  GET  /api/wa/status                 — auto-send readiness (flag + creds + allowlist) [admin]
  GET  /api/wa/templates              — list local template records                [admin]
  POST /api/wa/templates              — register/upsert a template record          [admin]
  POST /api/wa/templates/status       — track Meta approval status                 [admin]
  GET  /api/wa/suppression            — suppression list (opt-out/blocked)         [admin]
  POST /api/wa/suppression            — add/remove a suppressed number             [admin]
  GET  /api/wa/campaigns              — queued drip/reactivation campaigns          [admin]
  POST /api/wa/campaign/schedule      — queue a campaign for a date                 [admin]
  POST /api/wa/campaign/run           — run due campaigns now (manual trigger)      [admin]
  GET  /api/wa/drafts                 — pending would-send drafts (human queue)     [admin]
  POST /api/wa/drafts/{id}/sent       — mark a draft as sent by hand (idempotent)   [admin]
  POST /api/wa/drafts/{id}/dismiss    — drop a draft from the queue                 [admin]
  GET  /api/wa/webhook                — Meta verify challenge (hub.challenge)       [PUBLIC]
  POST /api/wa/webhook                — Meta inbound messages/statuses              [PUBLIC, signed]

SAFETY: ban-safety is enforced at the SENDER BOUNDARY
(``app/integrations/whatsapp.py::send_permitted``), not by the callers in this module —
that is deliberate, because the per-caller version of this rule is what let the hourly
onboarding job send ungated. A send needs WHATSAPP_AUTO_SEND=1 AND the recipient on
WHATSAPP_SEND_ALLOWLIST AND not opted-out/suppressed, all fail-CLOSED, plus official
creds and (for business-initiated Cloud sends) an approved template.
NOTE: this module's routes REPORT gate state; they do not enforce it.
Admin routes require an admin JWT. Webhook routes are public (Meta calls them) but the
POST is App-Secret signature-verified. Handlers never raise unhandled errors.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wa", tags=["WhatsApp"])


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
@router.get("/status")
async def wa_status(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.integrations import whatsapp as wa_int
    from app.marketing import whatsapp_campaign as wac

    prov = wac.provider()
    # Canary allowlist state. This endpoint used to say "Auto-send LIVE" purely from
    # flag+creds, which would now be a LIE: the boundary gate also requires the
    # recipient to be allowlisted. Reporting a gate's VALUE while it is not the thing
    # deciding is exactly the failure that let the ungated onboarding send hide.
    allow = wa_int.send_allowlist()
    graduated = allow == ["*"]
    # Count/graduation only — never echo the numbers back out of the .env.
    allow_count = 0 if graduated else len(allow)
    sends_possible = wac.auto_ready() and bool(allow)

    if sends_possible and graduated:
        note = f"Auto-send LIVE to ALL recipients via {('self-host (WAHA)' if prov == 'waha' else 'Meta Cloud API')} — allowlist graduated to '*'."
    elif sends_possible:
        note = f"Auto-send LIVE but CANARY-LIMITED to {allow_count} allowlisted number(s) via {('self-host (WAHA)' if prov == 'waha' else 'Meta Cloud API')}."
    elif wac.auto_ready():
        note = "WHATSAPP_AUTO_SEND is on and a backend is ready, but WHATSAPP_SEND_ALLOWLIST is EMPTY — every automated send is blocked (fail-closed canary). Add canary numbers, or '*' to graduate."
    elif prov == "waha":
        note = "Self-host (WAHA) selected — link the number (scan QR) + set WHATSAPP_AUTO_SEND=1 AND WHATSAPP_SEND_ALLOWLIST to auto-send."
    else:
        note = "Ban-safe mode: campaigns return 1-click links (set WHATSAPP_AUTO_SEND=1 + WHATSAPP_SEND_ALLOWLIST + a backend — Cloud API creds OR self-host WAHA — to auto-send)."
    return {
        "provider": prov,  # "cloud" | "waha" — which backend is actually live
        "auto_send_flag": wac.auto_send_enabled(),
        "creds_present": wac.creds_present(),  # any usable backend
        "cloud_creds_present": wac.cloud_creds_present(),  # Meta Cloud API specifically
        "selfhost_active": wac.selfhost_present(),  # WAHA selected + reachable-configured
        "auto_ready": wac.auto_ready(),  # flag + creds only — NOT the whole gate
        "allowlist_count": allow_count,  # numbers themselves stay in .env
        "allowlist_graduated": graduated,  # True only when the list is exactly '*'
        "sends_possible": sends_possible,  # the honest "can anything actually go out"
        "blocked_by_reason": wa_int.block_stats(),  # no PII — reason codes only
        "pending_drafts": wa_int.pending_drafts_count(),  # human-send backlog size
        "daily_cap": wac.daily_cap(),
        "sent_today": wac.sent_today_count(),
        "send_spacing_s": wac.send_spacing_s(),
        "note": note,
    }


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
@router.get("/templates")
async def list_templates(
    status: str = "", current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    return {"templates": runner.list_templates(status or None)}


class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    body: str = Field("", max_length=2000)
    language: str = Field("en", max_length=10)
    category: str = Field("MARKETING", max_length=20)
    status: str = Field("pending", max_length=20)
    example_params: list[str] = Field(default_factory=list)


@router.post("/templates")
async def register_template(
    req: TemplateIn, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    return runner.register_template(
        name=req.name,
        body=req.body,
        language=req.language,
        category=req.category,
        status=req.status,
        example_params=req.example_params,
    )


class TemplateStatusIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    status: str = Field(..., max_length=20)
    language: str = Field("en", max_length=10)


@router.post("/templates/status")
async def set_template_status(
    req: TemplateStatusIn, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    ok = runner.update_template_status(req.name, req.status, req.language)
    return {"ok": ok, "name": req.name, "status": req.status}


# --------------------------------------------------------------------------- #
# Suppression
# --------------------------------------------------------------------------- #
@router.get("/suppression")
async def list_suppression(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    return {"suppressed": runner.list_suppressed()}


class SuppressIn(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20)
    reason: str = Field("opt_out", max_length=60)
    remove: bool = False


@router.post("/suppression")
async def edit_suppression(
    req: SuppressIn, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    if req.remove:
        return {"removed": runner.unsuppress(req.phone), "phone": req.phone}
    return runner.suppress(req.phone, req.reason)


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
@router.get("/campaigns")
async def list_campaigns(
    status: str = "", current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    return {"campaigns": runner.list_campaigns(status or None)}


class RecipientIn(BaseModel):
    phone: str
    name: str = ""


class CampaignIn(BaseModel):
    kind: str = Field("drip", max_length=20)
    template_name: str = Field(..., min_length=1, max_length=120)
    business_name: str = Field("", max_length=120)
    client_id: str = Field("", max_length=80)
    language: str = Field("en", max_length=10)
    date_iso: str = Field("", max_length=10)
    recipients: list[RecipientIn] = Field(default_factory=list)
    params: list[str] = Field(default_factory=list)
    note: str = Field("", max_length=400)


@router.post("/campaign/schedule")
async def schedule_campaign(
    req: CampaignIn, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    return runner.schedule_campaign(
        kind=req.kind,
        template_name=req.template_name,
        business_name=req.business_name,
        client_id=req.client_id,
        language=req.language,
        date_iso=req.date_iso,
        recipients=[r.model_dump() for r in req.recipients],
        params=req.params,
        note=req.note,
    )


@router.post("/campaign/run")
async def run_campaigns(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    """Manual trigger of the due-campaign runner (same call the scheduler makes hourly)."""
    from app.marketing import wa_campaign_runner as runner

    return await runner.run_due()


# --------------------------------------------------------------------------- #
# Pending drafts — the human-send queue
# --------------------------------------------------------------------------- #
# Every gate-denied send already builds a ban-safe wa.me link; that would-send is now
# persisted instead of discarded, so there is a queue to work rather than only a
# counter. These routes are the inbox for it.
#
# They TRANSMIT NOTHING. A human taps the wa.me link in their own WhatsApp, which
# carries no ban risk — flipping WHATSAPP_AUTO_SEND is what carries the risk, and
# nothing in this module can do that.
@router.get("/drafts")
async def list_drafts(
    limit: int = 50, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Pending would-send drafts, newest first.

    Each draft carries the gate ``reason`` that blocked it. That field is not
    decorative — a draft blocked as ``opted_out``/``suppressed`` is a number that
    asked us not to message it, and must not be sent by hand either.
    """
    from app.integrations import whatsapp as wa_int

    safe_limit = max(1, min(limit, 500))
    drafts = wa_int.list_pending_drafts(safe_limit)
    return {
        "drafts": drafts,
        "returned": len(drafts),
        "total_pending": wa_int.pending_drafts_count(),
        "cap": wa_int.draft_cap(),
        "limit": safe_limit,
        "note": "Human-send queue: read each draft's `reason` before sending.",
    }


@router.post("/drafts/{draft_id}/sent")
async def mark_draft_sent(
    draft_id: str, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Mark a draft as sent by hand. Idempotent — a repeat call is a 200 no-op.

    Records only that the human sent it; nothing is transmitted from here.
    """
    from app.integrations import whatsapp as wa_int

    row = wa_int.mark_draft_sent(draft_id)
    if row is None:
        raise HTTPException(status_code=404, detail="draft_not_found")
    return {"ok": True, "id": draft_id, "sent": True, "already": bool(row.get("already"))}


@router.post("/drafts/{draft_id}/dismiss")
async def dismiss_draft(
    draft_id: str, current_user: User = Depends(require_admin)
) -> dict[str, Any]:
    """Drop a draft from the queue — the human judged it not worth sending.

    A repeat call 404s, because the row is genuinely gone by then.
    """
    from app.integrations import whatsapp as wa_int

    if not wa_int.dismiss_draft(draft_id):
        raise HTTPException(status_code=404, detail="draft_not_found")
    return {"ok": True, "id": draft_id, "dismissed": True}


# --------------------------------------------------------------------------- #
# Meta webhook (PUBLIC — Meta servers call these)
# --------------------------------------------------------------------------- #
def _verify_token() -> str:
    return (os.getenv("WHATSAPP_VERIFY_TOKEN", "") or "").strip()


@router.get("/webhook")
async def webhook_verify(request: Request):
    """Meta webhook verification handshake.

    Meta GETs with hub.mode=subscribe, hub.verify_token=<yours>, hub.challenge=<n>.
    Echo the challenge back (plain text) only if the verify token matches.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    expected = _verify_token()
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    return PlainTextResponse("verification_failed", status_code=403)


@router.post("/webhook")
async def webhook_inbound(request: Request) -> dict[str, Any]:
    """Inbound WhatsApp messages + delivery statuses from Meta.

    - App-Secret signature verified (X-Hub-Signature-256).
    - Inbound text -> stored as a reply draft (optionally fed to reply_agent flow).
    - Failed/blocked delivery status -> number auto-suppressed (bounce protection).
    - 'STOP'/'UNSUBSCRIBE' inbound -> opt-out (suppress).
    Always returns 200-ish JSON (Meta retries on non-2xx). Never raises.
    """
    raw = b""
    try:
        raw = await request.body()
    except Exception:
        pass
    # Verify signature (App Secret). Unconfigured -> allowed (loud warning expected).
    try:
        from app.integrations.whatsapp import verify_meta_signature

        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get(
            "x-hub-signature-256"
        )
        if not verify_meta_signature(raw, sig):
            logger.warning("wa webhook: bad signature, ignoring payload")
            return {"ok": False, "reason": "bad_signature"}
    except Exception:
        pass

    try:
        import json

        payload = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    res = {"ok": True, "messages": 0, "statuses": 0, "suppressed": 0}
    try:
        from app.marketing import wa_campaign_runner as runner

        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = (change or {}).get("value", {}) or {}
                # inbound messages
                for msg in value.get("messages", []) or []:
                    res["messages"] += 1
                    frm = str(msg.get("from", "")).strip()
                    text = ""
                    if msg.get("type") == "text":
                        text = str((msg.get("text") or {}).get("body", "")).strip()
                    _store_inbound(frm, text, msg.get("id", ""))
                    if text.lower() in ("stop", "unsubscribe", "stop promotions", "band karo"):
                        runner.suppress(frm, reason="opt_out_inbound")
                        res["suppressed"] += 1
                    elif text:
                        # Feed the message to the reply agent -> Hinglish draft (1-click send).
                        try:
                            from app.platform import reply_agent

                            await reply_agent.whatsapp_reply(frm, text, msg.get("id", ""))
                            res["drafted"] = res.get("drafted", 0) + 1
                        except Exception as _e:
                            logger.info("wa reply_agent err: %s", _e)
                # delivery statuses (sent/delivered/read/failed)
                for st in value.get("statuses", []) or []:
                    res["statuses"] += 1
                    if st.get("status") == "failed":
                        recipient = str(st.get("recipient_id", "")).strip()
                        errs = st.get("errors") or []
                        reason = (
                            errs[0].get("title") if errs else "delivery_failed"
                        ) or "delivery_failed"
                        runner.record_failure(recipient, str(reason))
    except Exception as e:
        logger.info("wa webhook parse err: %s", e)
    return res


# --------------------------------------------------------------------------- #
# Self-hosted stack (WAHA Core) — "apna khud ka" provider
#   GET  /api/wa/selfhost/status   — linked-session state (WORKING/SCAN_QR_CODE/…) [admin]
#   POST /api/wa/selfhost/start    — start/relink the session (then scan QR)       [admin]
#   GET  /api/wa/selfhost/qr       — QR image to scan on the business phone        [admin]
#   POST /api/wa/selfhost/webhook  — WAHA inbound messages (token-gated)           [PUBLIC]
# A number is EITHER on Cloud API OR on this Web session — never both at once.
# --------------------------------------------------------------------------- #
@router.get("/selfhost/status")
async def selfhost_status(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.integrations import whatsapp_selfhost as wahost

    st = await wahost.session_status()
    try:
        from app.config import settings as _s

        st["business_number"] = (getattr(_s, "whatsapp_business_number", "") or "").strip()
    except Exception:
        pass
    return st


@router.post("/selfhost/start")
async def selfhost_start(current_user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.integrations import whatsapp_selfhost as wahost

    return await wahost.start_session()


@router.get("/selfhost/qr")
async def selfhost_qr(current_user: User = Depends(require_admin)):
    """Return the link QR as an image (scan on the phone holding the business number)."""
    from app.integrations import whatsapp_selfhost as wahost

    data, ctype = await wahost.qr_image()
    if not data:
        return Response(
            content=b'{"error":"qr_unavailable"}',
            media_type="application/json",
            status_code=503,
        )
    return Response(content=data, media_type=ctype or "image/png")


def _webhook_token_ok(request: Request) -> bool:
    """Path/query token gate for the public WAHA webhook (the route IS internet-exposed).

    Configured URL = ``…/api/wa/selfhost/webhook?token=<WAHA_WEBHOOK_TOKEN>``.
    Token set -> must match. Token unset -> fail-CLOSED in production (dev allowed).
    """
    try:
        from app.config import settings as _s

        expected = (getattr(_s, "waha_webhook_token", "") or "").strip()
        if not expected:
            return not bool(getattr(_s, "is_production", False))
        got = (
            request.query_params.get("token")
            or request.headers.get("X-Webhook-Token")
            or request.headers.get("x-webhook-token")
            or ""
        ).strip()
        return bool(got) and got == expected
    except Exception:
        return False


_SEEN_FILE = os.path.join("data", "wa_selfhost_seen.json")


def _seen_message(message_id: str) -> bool:
    """Dedupe on message id (WAHA/Evolution redeliver). Bounded json. Never raises."""
    mid = (message_id or "").strip()
    if not mid:
        return False
    try:
        import json as _json

        ids: list[str] = []
        if os.path.exists(_SEEN_FILE):
            with open(_SEEN_FILE, encoding="utf-8") as f:
                ids = _json.load(f) or []
        if mid in ids:
            return True
        ids.append(mid)
        if len(ids) > 800:
            ids = ids[-800:]
        os.makedirs(os.path.dirname(_SEEN_FILE), exist_ok=True)
        with open(_SEEN_FILE, "w", encoding="utf-8") as f:
            _json.dump(ids, f)
    except Exception:
        pass
    return False


@router.post("/selfhost/webhook")
async def selfhost_webhook(request: Request) -> dict[str, Any]:
    """Inbound messages from the self-hosted WAHA stack.

    WAHA payload shape (NOT Meta's): ``{"event":"message","session":...,"payload":{"from":
    "918261…@c.us","body":"…","id":"…","fromMe":false}}``. Token-gated, deduped on id.
    Same downstream as the Meta path: store + opt-out/suppress + reply_agent draft.
    Always returns JSON, never raises.
    """
    if not _webhook_token_ok(request):
        logger.warning("wa selfhost webhook: bad/missing token, ignoring")
        return {"ok": False, "reason": "bad_token"}
    try:
        import json

        payload = json.loads((await request.body()).decode("utf-8") or "{}")
    except Exception:
        payload = {}

    res = {"ok": True, "messages": 0, "suppressed": 0, "drafted": 0, "dup": 0}
    try:
        from app.marketing import wa_campaign_runner as runner

        event = str(payload.get("event", "")).lower()
        body = payload.get("payload", {}) or {}
        if not event.startswith("message") or body.get("fromMe"):
            return res  # delivery acks / outbound echoes — ignore
        mid = str(body.get("id", "")).strip()
        if _seen_message(mid):
            res["dup"] += 1
            return res
        frm = str(body.get("from", "")).split("@")[0].strip()
        text = str(body.get("body", "")).strip()
        if not frm:
            return res
        res["messages"] += 1
        _store_inbound(frm, text, mid)
        if text.lower() in ("stop", "unsubscribe", "stop promotions", "band karo"):
            runner.suppress(frm, reason="opt_out_inbound")
            res["suppressed"] += 1
        elif text:
            # Delivered paid customer ka reply = acknowledgment (council: 'delivered =
            # acknowledged'). Read-side; message ko consume nahi karta.
            try:
                from app.marketing import customer_delivery

                customer_delivery.try_mark_acknowledged(frm)
            except Exception as _e:
                logger.debug("wa selfhost ack-mark err: %s", _e)
            handled = False
            try:
                from app.marketing.onboarding import try_capture_onboarding_reply

                handled = await try_capture_onboarding_reply(frm, text)
            except Exception as _e:
                logger.debug("wa selfhost onboarding-interview check err: %s", _e)
            if not handled:
                # Video Production Cell — customer review replies (flag-gated).
                try:
                    from app.marketing.video_production import review_whatsapp

                    vr = review_whatsapp.ingest_inbound(frm, text, mid)
                    if vr.get("handled"):
                        handled = True
                        res["video_review"] = vr.get("intent")
                        if vr.get("intent") == "ambiguous" and vr.get("clarification"):
                            try:
                                from app.integrations.whatsapp_selfhost import SelfHostWhatsApp

                                SelfHostWhatsApp().send_text_message(frm, vr["clarification"])
                            except Exception:
                                pass
                except Exception as _e:
                    logger.debug("wa selfhost video-review err: %s", _e)
            if not handled:
                try:
                    from app.platform import reply_agent

                    await reply_agent.whatsapp_reply(frm, text, mid)
                    res["drafted"] += 1
                except Exception as _e:
                    logger.info("wa selfhost reply_agent err: %s", _e)
    except Exception as e:
        logger.info("wa selfhost webhook parse err: %s", e)
    return res


def _store_inbound(from_number: str, text: str, message_id: str) -> None:
    """Persist an inbound WhatsApp message (1-click human reply / reply_agent fodder)."""
    try:
        import json
        from datetime import datetime, timezone

        path = os.path.join("data", "wa_inbound.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "from": from_number,
                        "text": text,
                        "message_id": message_id,
                        "at": datetime.now(timezone.utc).isoformat(),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    except Exception:
        pass
