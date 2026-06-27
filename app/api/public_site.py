"""
Public Site API — website inquiry form (lead capture) + admin inquiries view.
==============================================================================

Final paths (main.py prefix="/api" ke saath):
  POST /api/public/inquiry    -> NO AUTH — landing page YA mini-site ka form.
                                 Honeypot + per-IP rate limit + phone validation.
                                 source_slug (mini-site /b/{slug}) + preferred_time
                                 optional — slug se client resolve hota (business/
                                 niche/city auto-fill), record me bhi store hote.
                                 DB Lead save best-effort; data/inquiries.jsonl
                                 me HAMESHA append (koi inquiry kabhi lost nahi).
                                 NOTIFY_EMAIL + SMTP set ho to owner ko email.
  GET  /api/public/inquiries  -> ADMIN — last 100 inquiries (jsonl + DB merged).
  GET  /api/public/pay-info   -> NO AUTH — UPI payment info (QR + VPA + plans)
                                 for the landing "Shuru karo" modal. UPI_VPA
                                 env empty ho to {"enabled": false}.
  GET  /api/public/audit/questions -> NO AUTH — GBP self-audit ke 16 sawaal
                                 (gbp_audit.AUDIT_QUESTIONS — safe static).
  POST /api/public/audit/score -> NO AUTH — {answers} → TEASER result only:
                                 score/grade/top-3 fixes/impact. Full
                                 breakdown sirf paid/admin ke liye (lead-magnet).

Import-safe: DB/team modules lazy-import hote hain; kuch bhi missing ho to
form submit phir bhi jsonl me save hota hai aur user ko ok milta hai.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.models.user import User
from app.security.turnstile import site_key as _turnstile_site_key
from app.security.turnstile import verify_turnstile
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/public", tags=["Public"])

# Append-only file backup — DB down ho tab bhi inquiry kabhi nahi khoti.
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")

_OK_MESSAGE = "Dhanyawad! 24 ghante me call aayega."

# --------------------------------------------------------------------------- #
# In-memory rate limit — max 5 inquiries / minute / IP (simple timestamp list)
# --------------------------------------------------------------------------- #
_RL: dict[str, list[float]] = {}
_RL_AUDIT: dict[str, list[float]] = {}  # /audit/score ka alag bucket — inquiry quota nahi khaata
_RL_MAX = 5
_RL_WINDOW_S = 60.0


def _client_ip(request: Request | None) -> str:
    """Real client IP nikalo — nginx ke peeche X-Forwarded-For pehle."""
    try:
        if request is not None:
            fwd = request.headers.get("x-forwarded-for")
            if fwd:
                ip = fwd.split(",")[0].strip()
                if ip:
                    return ip
            if request.client and request.client.host:
                return request.client.host
    except Exception:
        pass
    return "unknown"


def _rate_limited(ip: str, store: dict[str, list[float]] | None = None) -> bool:
    """True = is IP ne 1 min me 5+ requests bheji (block karo).

    `store` se alag bucket de sakte ho (audit vs inquiry) — default _RL.
    """
    rl = _RL if store is None else store
    now = time.time()
    fresh = [t for t in rl.get(ip, []) if now - t < _RL_WINDOW_S]
    if len(fresh) >= _RL_MAX:
        rl[ip] = fresh
        return True
    fresh.append(now)
    rl[ip] = fresh
    # Opportunistic cleanup taaki dict unbounded na badhe.
    if len(rl) > 5000:
        for k in list(rl.keys()):
            if not any(now - t < _RL_WINDOW_S for t in rl[k]):
                rl.pop(k, None)
    return False


def _clean_phone(raw: str) -> str | None:
    """+91/0/spaces strip karke 10-12 digit number lautao (warna None).

    10-digit Indian number ko "+91XXXXXXXXXX" format me store karte hain
    (dialable). 11-12 digit (landline w/ STD etc.) as-is digits.
    """
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if not (10 <= len(digits) <= 12):
        return None
    if len(digits) == 10:
        return "+91" + digits
    return digits


# --------------------------------------------------------------------------- #
# Persistence helpers (sync session pattern — app/platform/team.py jaisa)
# --------------------------------------------------------------------------- #
def _db():
    """Sync Session banao (ya None) — base ke lazy engine/_SessionLocal se."""
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return None
        return _b._SessionLocal()
    except Exception:
        return None


def _append_jsonl(rec: dict[str, Any]) -> bool:
    """data/inquiries.jsonl me ek line append — yahi guarantee hai ki koi
    inquiry kabhi lost na ho (DB fail ho tab bhi)."""
    try:
        os.makedirs(os.path.dirname(_INQUIRIES_FILE) or ".", exist_ok=True)
        with open(_INQUIRIES_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[public] inquiries.jsonl write failed: {e}")
        return False


def _save_lead_db(rec: dict[str, Any]) -> str | None:
    """Lead model me best-effort save. Fail ho to None (jsonl me data hai hi)."""
    try:
        from app.models.lead import Lead, LeadSource, LeadStatus

        db = _db()
        if db is None:
            return None
        try:
            notes_parts: list[str] = []
            if rec.get("message"):
                notes_parts.append(f"Message: {rec['message']}")
            if rec.get("preferred_time"):
                notes_parts.append(f"Preferred time: {rec['preferred_time']}")
            if rec.get("city"):
                notes_parts.append(f"City: {rec['city']}")
            if rec.get("niche"):
                notes_parts.append(f"Niche: {rec['niche']}")
            if rec.get("package"):
                notes_parts.append(f"Package: {rec['package']}")
            if rec.get("source_slug"):
                notes_parts.append(f"[Mini-site: /b/{rec['source_slug']}]")
            else:
                notes_parts.append("[Website inquiry form]")

            lead = Lead(
                id=str(uuid.uuid4()),
                company_name=(rec.get("business_name") or "Unknown")[:255],
                contact_name=(rec.get("name") or "")[:255] or None,
                phone=rec["phone"],
                niche=(rec.get("niche") or None),
                city=(rec.get("city") or None),
                source=LeadSource.WEBSITE,
                status=LeadStatus.NEW,
                notes="\n".join(notes_parts),
            )
            db.add(lead)
            db.commit()
            return lead.id
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[public] DB lead save failed (jsonl me saved hai): {e}")
        return None


def _read_jsonl(limit: int = 300) -> list[dict[str, Any]]:
    """jsonl ki aakhri `limit` lines (parse-safe, corrupt lines skip)."""
    out: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return out
        with open(_INQUIRIES_FILE, encoding="utf-8") as f:
            lines = f.readlines()[-max(1, limit) :]
        for ln in lines:
            try:
                rec = json.loads(ln)
                if isinstance(rec, dict):
                    out.append(rec)
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"[public] inquiries.jsonl read failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Auto-callback — inquiry aate hi AI (Swara) us number pe call kare.
# Env AUTO_CALLBACK_INQUIRY=0 se off. Telephony unfunded ho to bhi sirf
# error log hota hai — inquiry flow kabhi affect nahi hota.
# --------------------------------------------------------------------------- #
# Fire-and-forget tasks ka strong reference (warna GC pending task gira sakta).
_BG_TASKS: set = set()


async def _auto_callback(phone: str, niche: str, business: str) -> None:
    """Fire-and-forget: inquiry phone pe conversational AI call try karo."""
    try:
        from app.api.telephony_vobiz import start_stream_call

        result = await start_stream_call(to=phone, niche=niche or "general")
        placed = bool(result.get("placed"))
        try:
            from app.platform.team import log_event

            log_event(
                "swara",
                "auto_callback",
                f"Inquiry callback → {phone} ({business})"
                + ("" if placed else f" — fail: {result.get('error') or 'not placed'}"),
                status="ok" if placed else "error",
                meta={
                    "niche": niche,
                    "placed": placed,
                    "error": result.get("error"),
                    "stream_token": result.get("stream_token"),
                },
            )
        except Exception:
            pass
        if not placed:
            logger.info(f"[public] auto-callback not placed for {phone}: {result.get('error')}")
        else:
            try:
                from app.platform.speed_to_lead import log_callback_touch

                log_callback_touch(phone, placed=True)
            except Exception:
                pass
    except Exception as e:  # absolute guard — task me unhandled exception nahi
        logger.warning(f"[public] auto-callback failed for {phone}: {e}")
        try:
            from app.platform.team import log_event

            log_event(
                "swara", "auto_callback", f"Inquiry callback → {phone} — crash: {e}", status="error"
            )
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Owner email notification — best-effort, fire-and-forget.
# NOTIFY_EMAIL + SMTP_USER/SMTP_PASSWORD .env me ho tabhi bhejta hai; kuch bhi
# missing/fail ho to silent skip (inquiry flow kabhi affect nahi hota).
# --------------------------------------------------------------------------- #
async def _notify_inquiry_email(rec: dict[str, Any]) -> None:
    try:
        from app.config import settings

        to = (getattr(settings, "notify_email", "") or "").strip()
        if not to or not settings.smtp_user or not settings.smtp_password:
            return  # not configured — silent skip
        from app.integrations.email_sender import EmailSender

        body = (
            f"Nayi inquiry: {rec.get('business_name') or 'Unknown'} "
            f"({rec.get('niche') or 'unknown'}) {rec.get('phone') or '-'}"
            f" — {rec.get('message') or 'no message'}"
        )
        if rec.get("package"):
            body += f"\nPackage: {rec['package']}"
        if rec.get("city"):
            body += f"\nCity: {rec['city']}"
        await EmailSender().send_email([to], "🔔 LeadGen AI inquiry", body)
    except Exception as e:  # absolute guard — notification kabhi flow nahi todti
        logger.debug(f"[public] inquiry email notify skipped: {e}")


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class InquiryIn(BaseModel):
    name: str = Field("", max_length=120)
    business_name: str = Field("", max_length=200)
    phone: str = Field("", max_length=20)
    niche: str | None = Field(None, max_length=60)
    city: str | None = Field(None, max_length=100)
    message: str | None = Field(None, max_length=1000)
    package: str | None = Field(None, max_length=40)  # Starter/Growth/Advanced (pricing card se)
    source_slug: str | None = Field(None, max_length=80)  # mini-site /b/{slug} se aayi inquiry
    preferred_time: str | None = Field(None, max_length=80)  # booking form ka "pasand ka time"
    utm_source: str | None = Field(None, max_length=80)  # channel attribution (quora/reddit/seo/...) — bandit seekhta
    website: str | None = Field("", max_length=200)  # honeypot — insaan ise kabhi nahi bharta


class AuditIn(BaseModel):
    """GBP self-audit answers — {question_id: option_index}. Missing = worst case."""

    answers: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Routes
class AiDemoIn(BaseModel):
    """Public AI-marketing demo input (lead magnet)."""

    business_name: str = Field(..., min_length=2, max_length=200)
    niche: str | None = Field("general", max_length=60)
    city: str | None = Field("", max_length=100)


@router.post(
    "/ai-demo",
    dependencies=[Depends(rate_limit("ai_demo", 8, 60)), Depends(verify_turnstile)],
)
async def ai_demo(body: AiDemoIn):
    """PUBLIC lead-magnet: business naam → REAL AI marketing pack preview (3 posts +
    hashtags + offer + CTA). Powered by niche_pack/post_generator (agent tools).
    No auth, rate-limited (LLM cost), free-stack, never-raise."""
    biz = (body.business_name or "").strip()
    if len(biz) < 2:
        raise HTTPException(status_code=422, detail="Business ka naam likho (min 2 akshar).")
    try:
        from app.marketing import niche_pack

        # Hard deadline: this is an unauthenticated public endpoint that fans out to
        # several free-LLM calls. Without a cap a single request can hold an HTTP worker
        # for tens of seconds during provider degradation (WEB_CONCURRENCY=2 -> worker
        # starvation, the prior outage class). Cap it; fall back to a static pack.
        pack = await asyncio.wait_for(
            niche_pack.build_pack(
                (body.niche or "general").strip().lower() or "general",
                biz,
                (body.city or "").strip(),
                count=3,
            ),
            timeout=20.0,
        )
    except Exception as e:
        logger.warning(f"[ai-demo] pack failed/timeout: {e}")
        pack = {"ok": False, "posts": [], "hashtags": [], "offer": "", "cta": ""}
    return {
        "ok": True,
        "business": biz,
        "pack": pack,
        "cta": {"pricing": "/pricing", "audit": "/audit", "whatsapp": "https://wa.me/918459012607"},
    }


# --------------------------------------------------------------------------- #
@router.post(
    "/inquiry",
    dependencies=[Depends(rate_limit("inquiry", 15, 60)), Depends(verify_turnstile)],
)
async def submit_inquiry(body: InquiryIn, request: Request):
    """Landing page ka lead form — NO AUTH. Validate → file+DB save → team log."""
    # 1) Honeypot: bots hidden "website" field bhar dete hain — ok bolo, ignore karo.
    if (body.website or "").strip():
        return {"ok": True, "message": _OK_MESSAGE}

    # 2) Rate limit (5/min/IP)
    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Thoda ruk ke dobara try karo.")

    # 3) Validation
    name = (body.name or "").strip()
    business = (body.business_name or "").strip()
    source_slug = (body.source_slug or "").strip()[:80] or None

    # Mini-site (/b/{slug}) se aayi inquiry: business/niche/city us client se
    # resolve karo (end-customer ko ye fields fill nahi karne padte).
    mini_client_id: str | None = None
    if source_slug:
        try:
            from app.marketing.clients_store import get_by_slug

            mc = get_by_slug(source_slug)
            if mc:
                mini_client_id = str(mc.get("id") or "") or None
                if not business:
                    business = str(mc.get("business_name") or "").strip()
                if not (body.niche or "").strip() and mc.get("niche"):
                    body.niche = str(mc.get("niche"))
                if not (body.city or "").strip() and mc.get("city"):
                    body.city = str(mc.get("city"))
        except Exception as e:
            logger.debug(f"[public] source_slug resolve skipped: {e}")
        # Mini-site form sirf naam+phone maangta hai — business na ho to slug-base hi rakho.
        if not business:
            business = source_slug.replace("-", " ").title()

    if not name or not business:
        raise HTTPException(status_code=422, detail="Naam aur business ka naam dono zaroori hain.")
    phone = _clean_phone(body.phone or "")
    if not phone:
        raise HTTPException(
            status_code=422, detail="Phone number sahi nahi lag raha (10 digit chahiye)."
        )

    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "at": datetime.utcnow().isoformat() + "Z",
        "name": name[:120],
        "business_name": business[:200],
        "phone": phone,
        "niche": ((body.niche or "").strip()[:50] or None),
        "city": ((body.city or "").strip()[:100] or None),
        "message": ((body.message or "").strip()[:1000] or None),
        "package": ((body.package or "").strip()[:40] or None),
        "preferred_time": ((body.preferred_time or "").strip()[:80] or None),
        "source_slug": source_slug,
        "client_id": mini_client_id,
        "source": "mini_site" if source_slug else "website",
        "ip": ip,
    }

    # 4) File FIRST (never-lose guarantee), phir DB best-effort.
    stored_file = _append_jsonl(rec)
    lead_id = _save_lead_db(rec)
    if lead_id:
        rec["lead_id"] = lead_id
    if not stored_file and not lead_id:
        # Dono fail — even then log line to bachao (last resort).
        logger.error(f"[public] INQUIRY STORE FAILED — raw: {json.dumps(rec, ensure_ascii=False)}")
    try:
        from app.platform.inquiry_hooks import run_after_inquiry

        await run_after_inquiry(
            rec,
            mini_client_id=mini_client_id,
            utm_source=(body.utm_source or "").strip().lower() or None,
            lead_id=lead_id,
        )
    except Exception as e:
        logger.debug(f"[public] inquiry funnel hooks skip: {e}")

    return {"ok": True, "message": _OK_MESSAGE}


class SignupIn(BaseModel):
    """Self-serve signup payload — pricing.html se. Account (client + login) banata."""

    business_name: str = Field(..., min_length=2, max_length=200)
    email: str = Field(..., min_length=5, max_length=254)  # RFC 5321 max email length
    password: str = Field(..., min_length=6, max_length=128)
    phone: str | None = Field("", max_length=20)
    niche: str | None = Field("general", max_length=60)
    city: str | None = Field("", max_length=100)
    plan: str | None = Field("starter", max_length=40)
    ref_code: str | None = Field("", max_length=80)  # affiliate referral code (optional, from ?ref= URL param)
    website: str | None = Field("", max_length=200)  # honeypot — insaan kabhi nahi bharta


@router.post("/signup", dependencies=[Depends(rate_limit("signup", 10, 60)), Depends(verify_turnstile)])
async def public_signup(body: SignupIn, request: Request):
    """NO AUTH self-serve signup: client + customer-login banao -> client_id + JWT.

    pricing.html isko call karta, phir /api/billing/checkout se payment open hota.
    ADDITIVE + abuse-safe: honeypot + rate-limit + email dedupe + ANTI-HIJACK
    (existing client jiska login pehle se hai, uspe naya login attach nahi hota).
    Existing inquiry/lead flow ko bilkul touch nahi karta.
    """
    # 0) Honeypot
    if (body.website or "").strip():
        raise HTTPException(status_code=400, detail="Invalid request.")

    # 1) Rate limit (5/min/IP — same store as inquiry)
    ip = _client_ip(request)
    if _rate_limited(ip):
        raise HTTPException(status_code=429, detail="Thoda ruk ke dobara try karo.")

    # 2) Validate
    biz = (body.business_name or "").strip()
    email = (body.email or "").strip().lower()
    pw = body.password or ""
    if len(biz) < 2:
        raise HTTPException(status_code=422, detail="Business ka naam chahiye.")
    if "@" not in email or "." not in email.split("@")[-1] or len(email) < 5:
        raise HTTPException(status_code=422, detail="Valid email do.")
    if len(pw) < 6:
        raise HTTPException(status_code=422, detail="Password kam se kam 6 characters.")

    # 3) Email already registered? -> login karo
    try:
        from app.api.customer_auth import client_has_login, login_exists, register_login

        if login_exists(email):
            raise HTTPException(
                status_code=409, detail="Yeh email already registered hai — login karo."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[signup] auth-store check failed: {e}")
        raise HTTPException(status_code=500, detail="Signup abhi possible nahi, baad me try karo.")

    # 4) Client banao (add_client phone/naam pe dedupe karta — kabhi raise nahi)
    try:
        from app.marketing.clients_store import add_client

        client = add_client(
            business_name=biz,
            niche=(body.niche or "general"),
            city=(body.city or ""),
            phone=(body.phone or ""),
            plan=(body.plan or "starter"),
        )
        cid = str((client or {}).get("id") or "")
    except Exception as e:
        logger.error(f"[signup] add_client failed: {e}")
        raise HTTPException(status_code=500, detail="Account banane me dikkat, baad me try karo.")
    if not cid:
        raise HTTPException(status_code=500, detail="Account id missing — support se contact karo.")

    # 5) ANTI-HIJACK: agar yeh client pehle se kisi ka owned hai (login attached), reject
    if client_has_login(cid):
        raise HTTPException(
            status_code=409,
            detail="Yeh business already registered lag raha — login karo ya alag naam/phone do.",
        )

    # 5.5) FREE TRIAL plan — payment ke BINA account (₹0, 7 din, marketing-lite).
    #      Sirf plan="trial" pe client record me trial fields set hote; paid flow
    #      (starter/growth/advanced) bilkul untouched. Best-effort, kabhi raise nahi.
    is_trial = (body.plan or "").strip().lower() == "trial"
    trial_expires = None
    if is_trial:
        try:
            from app.marketing.clients_store import update_client
            from app.marketing.packages import trial_expiry_iso

            trial_expires = trial_expiry_iso()
            update_client(cid, trial=True, trial_expires=trial_expires, plan="trial")
        except Exception as e:
            logger.warning(f"[signup] trial fields set failed (account still ok): {e}")

    # 6) Login banao + auto-login JWT
    register_login(email, pw, cid)
    token = None
    try:
        from app.api.admin import create_access_token

        token = create_access_token(cid, email, "customer")
    except Exception as e:
        logger.debug(f"[signup] token issue (login still works): {e}")

    # 7) Team activity (best-effort) — Rohan ko self-signup dikhe
    try:
        from app.platform.team import log_event

        log_event(
            "rohan",
            "self_signup",
            f"{biz} ({body.plan or 'starter'}) — {email}",
            meta={"client_id": cid, "plan": body.plan, "via": "pricing_page"},
        )
    except Exception:
        pass

    # Lifecycle nurture — signup ko trial->paid sequence me enroll (record-only;
    # emails sirf LIFECYCLE_NURTURE=1 pe scheduler se). Best-effort, kabhi raise nahi.
    try:
        from app.marketing import lifecycle_nurture

        lifecycle_nurture.enroll(email, biz, cid, body.plan or "starter")
    except Exception as e:
        logger.debug(f"[signup] lifecycle enroll skip: {e}")

    # Affiliate referral — ref_code se signup aaya to record karo (commission track)
    try:
        ref = (body.ref_code or "").strip()
        if ref:
            from app.marketing.affiliate import record_referral

            record_referral(ref, {"business_name": biz, "email": email, "phone": body.phone or ""})
    except Exception as e:
        logger.debug(f"[signup] referral record skip: {e}")

    # Journey engine — fire 'signup' (gated JOURNEY_ENGINE=1; default off).
    try:
        from app.marketing import journeys

        st = asyncio.create_task(
            journeys.emit_event(
                "signup",
                {"business_name": biz, "name": biz, "phone": body.phone, "plan": body.plan},
            )
        )
        _BG_TASKS.add(st)
        st.add_done_callback(_BG_TASKS.discard)
    except Exception as e:
        logger.debug(f"[signup] journey emit spawn failed: {e}")

    # Outbound webhook: signup event (Zapier/n8n integration ke liye).
    try:
        from app.platform import outbound_webhooks as _ow

        _ow_t = asyncio.create_task(
            _ow.emit(
                "signup",
                {
                    "business_name": biz,
                    "phone": body.phone or "",
                    "plan": body.plan or "starter",
                    "client_id": cid,
                },
            )
        )
        _BG_TASKS.add(_ow_t)
        _ow_t.add_done_callback(_BG_TASKS.discard)
    except Exception as e:
        logger.debug(f"[signup] outbound_webhook skip: {e}")

    out: dict[str, Any] = {
        "ok": True,
        "client_id": cid,
        "access_token": token,
        "token_type": "bearer",
        "business_name": (client or {}).get("business_name"),
        "slug": (client or {}).get("slug"),
    }
    if is_trial:
        out["trial"] = True
        out["trial_expires"] = trial_expires
        out["message"] = "7-din FREE trial shuru — koi payment nahi chahiye. 🎉"
    return out


@router.get("/pay-info")
async def pay_info():
    """Landing page ka payment modal — NO AUTH. UPI VPA set ho tabhi
    enabled; QR upi_kit (pure-python encoder) se banta hai, packages
    app.marketing.packages se (key/name/price only). Kabhi raise nahi karta."""
    vpa = ""
    try:
        from app.platform import upi_config

        vpa = upi_config.get_vpa()
    except Exception:
        try:
            from app.config import settings

            vpa = (getattr(settings, "upi_vpa", "") or "").strip()
        except Exception:
            vpa = ""
    if not vpa:
        return {"enabled": False}

    out: dict[str, Any] = {"enabled": True, "vpa": vpa}
    wa = (os.environ.get("UPI_VERIFY_WA") or "918459012607").strip().lstrip("+")
    out["wa_phone"] = wa
    try:
        from app.marketing.upi_kit import payment_kit

        kit = payment_kit("LeadGen AI", vpa)
        out["upi_link"] = kit.get("upi_link") or ""
        out["qr_svg"] = kit.get("qr_svg") or ""
    except Exception as e:
        logger.debug(f"[public] pay-info QR build failed: {e}")
        out["upi_link"] = ""
        out["qr_svg"] = ""
    try:
        from app.marketing.packages import get_public_packages

        # PUBLIC pay modal — sirf 2 public plans (main ₹1,999 + advanced ₹5,999).
        # Legacy Growth (public:False) filtered out — get_public_packages() honors it.
        out["packages"] = [
            {
                "key": p.get("key"),
                "name": p.get("name"),
                "price_inr_month": p.get("price_inr_month"),
            }
            for p in (get_public_packages() or [])
        ]
    except Exception:
        out["packages"] = []
    return out


# --------------------------------------------------------------------------- #
# FREE public GBP audit — lead-magnet funnel (/audit page isi par chalta hai)
# --------------------------------------------------------------------------- #
@router.get("/turnstile/config")
async def turnstile_config():
    """Public Turnstile config for client-side widget render.

    Returns `{enabled, site_key}`. INERT (enabled=False) when site-key unset —
    HTML pages skip the widget injection entirely, zero change for today's flow.
    """
    sk = _turnstile_site_key()
    return {"enabled": bool(sk), "site_key": sk}


@router.get("/audit/questions")
async def audit_questions():
    """GBP self-audit ke 16 sawaal — NO AUTH (safe static data, koi secret nahi)."""
    from app.marketing.gbp_audit import AUDIT_QUESTIONS

    return {"questions": AUDIT_QUESTIONS}


@router.post("/audit/score", dependencies=[Depends(verify_turnstile)])
async def audit_score(body: AuditIn, request: Request):
    """Audit answers → TEASER result — NO AUTH.

    Sirf {score, grade, top_fixes[:3], locked_fixes, impact} return hota hai —
    full breakdown + saare fixes paid/admin flow me milte hain (yahi hook hai).
    Rate-limit alag bucket me taaki audit ke baad inquiry block na ho.
    """
    ip = _client_ip(request)
    if _rate_limited(ip, _RL_AUDIT):
        raise HTTPException(status_code=429, detail="Thoda ruk ke dobara try karo.")

    answers = body.answers if isinstance(body.answers, dict) else {}
    # Guard: max 32 answer keys (audit has 16 questions; 2x headroom for future)
    if len(answers) > 32:
        raise HTTPException(status_code=422, detail="Bahut zyada answers — max 32 allowed.")

    from app.marketing.gbp_audit import score_audit

    result = score_audit(answers)

    # Team activity (Isha — Marketing) — kabhi raise nahi karta.
    try:
        from app.platform.team import log_event

        log_event("isha", "public_audit", f"score {result.get('score')}")
    except Exception:
        pass

    all_fixes = result.get("top_fixes") or []
    return {
        "score": result.get("score", 0),
        "grade": result.get("grade", "D"),
        "top_fixes": all_fixes[:3],
        "locked_fixes": max(0, len(all_fixes) - 3),  # teaser count — content locked
        "impact": result.get("impact", ""),
    }


@router.get("/inquiries")
async def list_inquiries(current_user: User = Depends(require_admin)):
    """Admin view — last 100 inquiries, jsonl + DB (source=website) merged."""
    records: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}  # phone|business -> record (dedupe DB vs file)

    for rec in _read_jsonl(limit=300):
        r = dict(rec)
        r["stored_in"] = ["file"]
        records.append(r)
        key = f"{r.get('phone', '')}|{str(r.get('business_name') or '').strip().lower()}"
        seen[key] = r

    try:
        from app.models.lead import Lead, LeadSource

        db = _db()
        if db is not None:
            try:
                rows = (
                    db.query(Lead)
                    .filter(Lead.source == LeadSource.WEBSITE)
                    .order_by(Lead.created_at.desc())
                    .limit(150)
                    .all()
                )
                for row in rows:
                    key = f"{getattr(row, 'phone', '')}|{str(getattr(row, 'company_name', '') or '').strip().lower()}"
                    if key in seen:
                        seen[key].setdefault("lead_id", getattr(row, "id", None))
                        seen[key]["lead_status"] = (
                            row.status.value if getattr(row, "status", None) else None
                        )
                        if "db" not in seen[key]["stored_in"]:
                            seen[key]["stored_in"].append("db")
                    else:
                        created = getattr(row, "created_at", None)
                        records.append(
                            {
                                "id": getattr(row, "id", ""),
                                "at": (created.isoformat() + "Z") if created else None,
                                "name": getattr(row, "contact_name", None),
                                "business_name": getattr(row, "company_name", None),
                                "phone": getattr(row, "phone", None),
                                "niche": getattr(row, "niche", None),
                                "city": getattr(row, "city", None),
                                "message": getattr(row, "notes", None),
                                "lead_status": (
                                    row.status.value if getattr(row, "status", None) else None
                                ),
                                "stored_in": ["db"],
                            }
                        )
            finally:
                db.close()
    except Exception as e:
        logger.debug(f"[public] inquiries DB merge failed: {e}")

    records.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
    items = records[:100]
    return {"ok": True, "count": len(items), "inquiries": items}


__all__ = ["router"]
