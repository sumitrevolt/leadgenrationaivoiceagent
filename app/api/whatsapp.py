"""WhatsApp Cloud API admin + webhook routes (OFFICIAL Meta Cloud API only).

Mounted at ``/api`` -> all paths here live under ``/api/wa/*``.

  GET  /api/wa/status                 — auto-send readiness (flag + creds + cap)   [admin]
  GET  /api/wa/templates              — list local template records                [admin]
  POST /api/wa/templates              — register/upsert a template record          [admin]
  POST /api/wa/templates/status       — track Meta approval status                 [admin]
  GET  /api/wa/suppression            — suppression list (opt-out/blocked)         [admin]
  POST /api/wa/suppression            — add/remove a suppressed number             [admin]
  GET  /api/wa/campaigns              — queued drip/reactivation campaigns          [admin]
  POST /api/wa/campaign/schedule      — queue a campaign for a date                 [admin]
  POST /api/wa/campaign/run           — run due campaigns now (manual trigger)      [admin]
  GET  /api/wa/webhook                — Meta verify challenge (hub.challenge)       [PUBLIC]
  POST /api/wa/webhook                — Meta inbound messages/statuses              [PUBLIC, signed]

SAFETY: every send path is ban-safe — auto-send only when WHATSAPP_AUTO_SEND=1 AND
official creds are present AND template is approved AND number is opted-in/not-suppressed.
Admin routes require an admin JWT. Webhook routes are public (Meta calls them) but the
POST is App-Secret signature-verified. Handlers never raise unhandled errors.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse
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
    from app.marketing import whatsapp_campaign as wac

    return {
        "auto_send_flag": wac.auto_send_enabled(),
        "creds_present": wac.creds_present(),
        "auto_ready": wac.auto_ready(),
        "daily_cap": wac.daily_cap(),
        "sent_today": wac.sent_today_count(),
        "send_spacing_s": wac.send_spacing_s(),
        "note": (
            "Auto-send LIVE."
            if wac.auto_ready()
            else "Ban-safe mode: campaigns return 1-click links (set WHATSAPP_AUTO_SEND=1 + Cloud API creds to auto-send approved templates)."
        ),
    }


# --------------------------------------------------------------------------- #
# Templates
# --------------------------------------------------------------------------- #
@router.get("/templates")
async def list_templates(status: str = "", current_user: User = Depends(require_admin)) -> dict[str, Any]:
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
async def register_template(req: TemplateIn, current_user: User = Depends(require_admin)) -> dict[str, Any]:
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
async def edit_suppression(req: SuppressIn, current_user: User = Depends(require_admin)) -> dict[str, Any]:
    from app.marketing import wa_campaign_runner as runner

    if req.remove:
        return {"removed": runner.unsuppress(req.phone), "phone": req.phone}
    return runner.suppress(req.phone, req.reason)


# --------------------------------------------------------------------------- #
# Campaigns
# --------------------------------------------------------------------------- #
@router.get("/campaigns")
async def list_campaigns(status: str = "", current_user: User = Depends(require_admin)) -> dict[str, Any]:
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
async def schedule_campaign(req: CampaignIn, current_user: User = Depends(require_admin)) -> dict[str, Any]:
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

        sig = request.headers.get("X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")
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
                        reason = (errs[0].get("title") if errs else "delivery_failed") or "delivery_failed"
                        runner.record_failure(recipient, str(reason))
    except Exception as e:
        logger.info("wa webhook parse err: %s", e)
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
