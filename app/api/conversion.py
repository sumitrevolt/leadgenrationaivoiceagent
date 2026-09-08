"""
Conversion API — live AI chat widget + generic inbound lead webhook + trial status
==================================================================================

CONVERSION funnel ke 4 gaps close karta hai (sab additive, free-stack, ban-safe):

PUBLIC (mount prefix="/api" ke saath final paths):
  POST /api/public/widget-chat   -> embed widget ka AI chat (chatbot.py brain reuse).
                                    Rate-limited 20/60s. Har turn data/widget_chats.jsonl
                                    me log. Message me 10-digit Indian phone mile to
                                    EXISTING inquiry path me lead bhi banta (in-chat
                                    lead capture — utm_source=widget_chat).
  POST /api/public/lead-in?key=  -> Zapier/Pabbly/FB-lead-ads/IndiaMART/JustDial catcher.
                                    Auth = EXISTING client_api_keys (lga_ key → client).
                                    Flexible JSON aliases + FB field_data format.
                                    Dedupe by phone. Rate-limited 30/60s.
  GET  /api/public/trial-status  -> client ka free-trial state (active/expired/days_left)
                                    — customer portal ke liye. Rate-limited.

ADMIN:
  GET/POST /api/conversion/widget-form/{slug} -> form-builder-lite: embed form ke
                                    custom fields (data/widget_forms.jsonl via
                                    embed_widget helpers).

Never-raise pattern: sab heavy imports lazy; store-write best-effort; module import
kabhi fail nahi hota. Koi naya env flag nahi (kuch SEND nahi karta — drafts/records).
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Do routers — public (/api/public/*) + admin (/api/conversion/*). Dono ko
# main.py me prefix="/api" ke saath mount karna hai.
public_router = APIRouter(prefix="/public", tags=["Conversion Public"])
admin_router = APIRouter(prefix="/conversion", tags=["Conversion Admin"])

# Chat-turn log (append-only; tests monkeypatch karte hain)
_CHATS_FILE = os.path.join("data", "widget_chats.jsonl")

# Indian mobile: optional +91/0 prefix, phir 10 digits starting 6-9 (word-boundary safe)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\d)")


# --------------------------------------------------------------------------- #
# Pure helpers (unit-testable, no network)
# --------------------------------------------------------------------------- #
def extract_phone(text: str) -> str | None:
    """Free-text me 10-digit Indian mobile dhundo → '+91XXXXXXXXXX' | None."""
    try:
        m = _PHONE_RE.search(text or "")
        if m:
            return "+91" + m.group(1)
    except Exception:
        pass
    return None


def _log_chat(slug: str, session_id: str, role: str, text: str, **extra: Any) -> None:
    """Ek chat turn jsonl me append (best-effort, kabhi raise nahi)."""
    try:
        rec = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "slug": (slug or "")[:80],
            "session_id": (session_id or "")[:64],
            "role": (role or "")[:12],
            "text": (text or "")[:1200],
        }
        rec.update({k: v for k, v in extra.items() if v is not None})
        os.makedirs(os.path.dirname(_CHATS_FILE) or ".", exist_ok=True)
        with open(_CHATS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.debug(f"[conversion] chat log skip: {e}")


# Field-alias map (lowercased key → canonical) — Zapier/Pabbly/IndiaMART/JustDial sab
# alag naam bhejte hain.
_ALIASES: dict[str, str] = {
    "name": "name",
    "full_name": "name",
    "fullname": "name",
    "contact_name": "name",
    "your name": "name",
    "lead_name": "name",
    "sender_name": "name",
    "phone": "phone",
    "mobile": "phone",
    "phone_number": "phone",
    "mobile_number": "phone",
    "contact": "phone",
    "contact_number": "phone",
    "whatsapp": "phone",
    "sender_mobile": "phone",
    "email": "email",
    "work_email": "email",
    "email_address": "email",
    "sender_email": "email",
    "city": "city",
    "location": "city",
    "sender_city": "city",
    "source": "source",
    "platform": "source",
    "lead_source": "source",
    "message": "message",
    "notes": "message",
    "note": "message",
    "comments": "message",
    "query": "message",
    "enquiry": "message",
    "inquiry": "message",
    "requirement": "message",
    "business": "business_name",
    "business_name": "business_name",
    "company": "business_name",
    "company_name": "business_name",
}


def map_lead_fields(payload: Any) -> dict[str, str]:
    """Flexible inbound JSON → canonical {name, phone, email, city, source, message,
    business_name}. FB leadgen `field_data: [{name, values:[...]}]` bhi handle.
    Unknown extra fields message me append hote (kuch lost nahi). Never raises."""
    out: dict[str, str] = {}
    extras: list[str] = []
    try:
        if not isinstance(payload, dict):
            return out

        flat: dict[str, Any] = dict(payload)

        # FB lead-ads nested format (entry/changes/value.field_data ya seedha field_data)
        fd = flat.pop("field_data", None)
        if fd is None:
            try:
                fd = payload["entry"][0]["changes"][0]["value"]["field_data"]
            except Exception:
                fd = None
        if isinstance(fd, list):
            for item in fd:
                try:
                    k = str(item.get("name") or "").strip()
                    vals = item.get("values") or []
                    v = str(vals[0] if isinstance(vals, list) and vals else item.get("value") or "")
                    if k and v:
                        flat[k] = v
                except Exception:
                    continue

        for k, v in flat.items():
            try:
                if v is None or isinstance(v, (dict, list)):
                    continue
                key = str(k).strip().lower().replace("-", "_")
                sval = str(v).strip()[:500]
                if not sval:
                    continue
                canon = _ALIASES.get(key) or _ALIASES.get(key.replace("_", " "))
                if canon:
                    if canon == "message" and out.get("message"):
                        extras.append(sval)  # do message-jaise fields — jodo, overwrite nahi
                    else:
                        out[canon] = sval
                elif key not in ("entry", "key", "api_key", "token", "website"):
                    extras.append(f"{k}: {sval}")
            except Exception:
                continue

        if extras:
            joined = " | ".join(extras)[:800]
            out["message"] = (
                out.get("message", "") + ("\n" if out.get("message") else "") + joined
            ).strip()
    except Exception as e:
        logger.debug(f"[conversion] map_lead_fields err: {e}")
    return out


def _inquiry_phone_exists(phone: str, limit: int = 1000) -> bool:
    """Dedupe: same phone already inquiries store me? (best-effort)."""
    try:
        from app.api.public_site import _read_jsonl

        for rec in _read_jsonl(limit=limit):
            if str(rec.get("phone") or "") == phone:
                return True
    except Exception:
        pass
    return False


async def _create_inquiry(rec: dict[str, Any]) -> str | None:
    """Inquiry store + full funnel hooks (shared with public_site.submit_inquiry)."""
    try:
        from app.api.public_site import _append_jsonl, _save_lead_db
        from app.platform.inquiry_hooks import run_after_inquiry

        rec.setdefault("id", str(uuid.uuid4()))
        rec.setdefault("at", datetime.utcnow().isoformat() + "Z")
        _append_jsonl(rec)
        lead_id = _save_lead_db(rec)
        if lead_id:
            rec["lead_id"] = lead_id
        await run_after_inquiry(
            rec,
            mini_client_id=str(rec.get("client_id") or "") or None,
            utm_source=str(rec.get("utm_source") or "") or None,
            lead_id=lead_id,
        )
        return lead_id or rec.get("id")
    except Exception as e:
        logger.warning(f"[conversion] inquiry create failed: {e}")
        return None


# --------------------------------------------------------------------------- #
# F1: Live AI chat widget — POST /api/public/widget-chat
# --------------------------------------------------------------------------- #
class WidgetChatIn(BaseModel):
    slug: str = ""
    message: str = ""
    session_id: str = ""


@public_router.post("/widget-chat", dependencies=[Depends(rate_limit("widget_chat", 20, 60))])
async def widget_chat(body: WidgetChatIn):
    """Embed widget ka AI chat — client-KB chatbot brain (app/marketing/chatbot.py)
    reuse karta. NO AUTH (end-customer use karta), rate-limited 20/60s.
    Message me phone number mile to in-chat lead capture (EXISTING inquiry path)."""
    slug = (body.slug or "").strip().lower()[:80]
    msg = (body.message or "").strip()[:500]
    sess = (body.session_id or "").strip()[:64] or "anon"
    if not slug:
        raise HTTPException(status_code=422, detail="slug required")
    if not msg:
        return {"ok": True, "reply": "Namaste! Boliye, main aapki kaise madad karu? 🙏"}

    # Resolve client (invalid slug = 404, LLM abuse mat hone do)
    client: dict[str, Any] | None = None
    try:
        from app.marketing.clients_store import get_by_slug

        client = get_by_slug(slug)
    except Exception as e:
        logger.debug(f"[widget-chat] slug resolve err: {e}")
    if not client:
        raise HTTPException(status_code=404, detail="Business nahi mila.")

    cid = str(client.get("id") or "")
    biz = str(client.get("business_name") or "")
    _log_chat(slug, sess, "user", msg)

    # In-chat lead capture — message me 10-digit phone mile to inquiry banao
    lead_captured = False
    phone = extract_phone(msg)
    if phone and not _inquiry_phone_exists(phone, limit=500):
        lead_id = await _create_inquiry(
            {
                "name": "Chat Visitor",
                "business_name": biz or slug.replace("-", " ").title(),
                "phone": phone,
                "niche": client.get("niche"),
                "city": client.get("city"),
                "message": f"[Widget chat] {msg}"[:1000],
                "source_slug": slug,
                "client_id": cid,
                "source": "widget_chat",
                "utm_source": "widget_chat",
            }
        )
        lead_captured = bool(lead_id)
    elif phone:
        lead_captured = True  # pehle se captured — user ko phir bhi confirm bolo

    # AI reply (chatbot brain — KB-grounded, never raises)
    reply_text = ""
    try:
        from app.marketing import chatbot

        res = await chatbot.reply(msg, client_id=cid, niche=str(client.get("niche") or "general"))
        reply_text = str((res or {}).get("answer") or "").strip()
    except Exception as e:
        logger.debug(f"[widget-chat] brain err: {e}")
    if not reply_text:
        reply_text = (
            "Iska jawab main team se confirm karke bata deta hoon — apna number chhod "
            "dijiye, hum turant call karenge. 🙏"
        )
    if lead_captured:
        reply_text += "\n\nDhanyawad! Aapka number mil gaya — team jald hi call karegi. 📞"

    _log_chat(slug, sess, "bot", reply_text, lead_captured=lead_captured or None)
    return {"ok": True, "reply": reply_text, "lead_captured": lead_captured}


# --------------------------------------------------------------------------- #
# F2: Generic inbound lead webhook — POST /api/public/lead-in?key=lga_...
# --------------------------------------------------------------------------- #
@public_router.post("/lead-in", dependencies=[Depends(rate_limit("lead_in", 30, 60))])
async def lead_in(request: Request, key: str = ""):
    """Zapier/Pabbly/FB-lead-ads/IndiaMART/JustDial → leads dashboard catcher.

    Auth = EXISTING client API key (lga_..., app/platform/client_api_keys.py).
    Body = koi bhi flexible JSON — aliases + FB field_data handle hote hain.
    Dedupe by phone. Lead EXISTING inquiry path me hi jata (source=webhook:<src>)."""
    # 1) Auth — key query param ya X-Api-Key header
    api_key = (key or request.headers.get("x-api-key") or "").strip()
    client_id: str | None = None
    try:
        from app.platform.client_api_keys import verify

        client_id = verify(api_key)
    except Exception as e:
        logger.debug(f"[lead-in] key verify err: {e}")
    if not client_id:
        raise HTTPException(status_code=401, detail="Invalid/missing API key (lga_...).")

    # 2) Body parse (defensive)
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="JSON body chahiye.")
    mapped = map_lead_fields(payload)

    # 3) Validate phone (Indian) — phone ke bina lead dial nahi ho sakta
    phone = None
    try:
        from app.api.public_site import _clean_phone

        phone = _clean_phone(mapped.get("phone") or "")
    except Exception:
        phone = extract_phone(mapped.get("phone") or "")
    if not phone:
        raise HTTPException(status_code=422, detail="Valid phone chahiye (10-digit Indian).")

    # 4) Dedupe by phone
    if _inquiry_phone_exists(phone):
        return {
            "ok": True,
            "deduped": True,
            "lead_id": None,
            "message": "Yeh phone already lead-list me hai (duplicate skip).",
        }

    # 5) Client resolve (business/niche/city auto-fill) + inquiry create
    client: dict[str, Any] = {}
    try:
        from app.marketing.clients_store import get_client

        client = get_client(client_id) or {}
    except Exception:
        client = {}
    src = (mapped.get("source") or "generic").strip().lower()[:40]
    lead_id = await _create_inquiry(
        {
            "name": (mapped.get("name") or "Webhook Lead")[:120],
            "business_name": (
                mapped.get("business_name") or client.get("business_name") or "Unknown"
            )[:200],
            "phone": phone,
            "email": (mapped.get("email") or None),
            "niche": client.get("niche"),
            "city": (mapped.get("city") or client.get("city") or None),
            "message": (mapped.get("message") or None),
            "source_slug": client.get("slug"),
            "client_id": client_id,
            "source": f"webhook:{src}",
            "utm_source": src,
        }
    )
    if not lead_id:
        raise HTTPException(status_code=500, detail="Lead save nahi hua — dobara try karo.")
    return {"ok": True, "lead_id": lead_id, "deduped": False}


# --------------------------------------------------------------------------- #
# F3: Trial status — GET /api/public/trial-status (customer portal ke liye)
# --------------------------------------------------------------------------- #
@public_router.get("/trial-status", dependencies=[Depends(rate_limit("trial_status", 30, 60))])
async def get_trial_status(client_id: str = "", slug: str = ""):
    """Free-trial state (active/expired/days_left) — koi sensitive data expose nahi
    hota (sirf trial flags). client_id YA slug se lookup."""
    client: dict[str, Any] | None = None
    try:
        from app.marketing.clients_store import get_by_slug, get_client

        if (client_id or "").strip():
            client = get_client(client_id.strip())
        elif (slug or "").strip():
            client = get_by_slug(slug.strip())
    except Exception as e:
        logger.debug(f"[trial-status] lookup err: {e}")
    if not client:
        raise HTTPException(status_code=404, detail="Client nahi mila.")
    try:
        from app.marketing.packages import trial_status

        st = trial_status(client)
    except Exception:
        st = {"trial": False, "active": False, "expired": False, "days_left": 0, "expires_at": None}
    return {"ok": True, "plan": client.get("plan"), **st}


# --------------------------------------------------------------------------- #
# F4: Form-builder-lite admin — GET/POST /api/conversion/widget-form/{slug}
# --------------------------------------------------------------------------- #
class WidgetFormIn(BaseModel):
    fields: list[dict] = []


@admin_router.get("/widget-form/{slug}")
async def widget_form_get(slug: str, _user=Depends(require_admin)):
    """Slug ka current embed-form config (custom ya default) — admin."""
    try:
        from app.marketing import embed_widget

        cfg = embed_widget.get_form_config(slug)
        return {
            "ok": True,
            "slug": (slug or "").strip().lower(),
            "configured": cfg is not None,
            "fields": cfg or embed_widget.default_fields(),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


@admin_router.post("/widget-form/{slug}")
async def widget_form_set(slug: str, body: WidgetFormIn, _user=Depends(require_admin)):
    """Custom fields save (max 10; type text|tel|email|select). name/phone embed
    render me auto-ensure hote (inquiry API inhe maangta hai) — admin."""
    try:
        from app.marketing import embed_widget

        res = embed_widget.save_form_config(slug, body.fields)
        if not res.get("ok"):
            raise HTTPException(status_code=422, detail=res.get("error") or "Invalid fields.")
        return res
    except HTTPException:
        raise
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


__all__ = ["public_router", "admin_router", "extract_phone", "map_lead_fields"]
