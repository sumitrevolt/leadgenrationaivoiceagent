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
# Rate limit — Redis-first (multi-worker safe), in-memory fallback (single-worker).
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


async def _rate_check(ip: str, bucket: str = "inquiry") -> None:
    """Redis-backed rate limit — raises HTTPException(429) if throttled.

    Fail-open: Redis unavailable me in-memory fallback. Multi-worker safe
    when Redis is available (shared counter across all uvicorn processes).
    """
    try:
        from app.cache import get_redis_client

        client = await get_redis_client()
        if client is not None and hasattr(client, "incr"):
            key = f"rl:{bucket}:{ip}"
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, int(_RL_WINDOW_S))
            if count > _RL_MAX:
                raise HTTPException(status_code=429, detail="Thoda ruk ke dobara try karo.")
            return
    except HTTPException:
        raise
    except Exception:
        pass  # Redis fail → in-memory fallback

    # In-memory fallback (per-worker, per-bucket)
    store = _RL_AUDIT if bucket == "audit" else _RL
    now = time.time()
    fresh = [t for t in store.get(ip, []) if now - t < _RL_WINDOW_S]
    if len(fresh) >= _RL_MAX:
        store[ip] = fresh
        raise HTTPException(status_code=429, detail="Thoda ruk ke dobara try karo.")
    fresh.append(now)
    store[ip] = fresh
    if len(store) > 5000:
        for k in list(store.keys()):
            if not any(now - t < _RL_WINDOW_S for t in store[k]):
                store.pop(k, None)


# Legacy alias for tests (removed in Phase 5 but some stale mocks still touch it)
_rate_limited = _rate_check


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
    """Lead model me best-effort save. Fail ho to None (jsonl me data hai hi).

    Dedupe-by-phone (production audit 2026-07-01, F-DB2) — this was the one
    real-DB Lead() write path with no dedup check; every other write path
    (app/platform/prospector.py, app/tasks/sync.py) already looks up an
    existing Lead by phone first. Matching that established convention: a
    repeat inquiry from the same phone number appends to the existing lead's
    notes (new inquiry text preserved, nothing lost) instead of creating a
    fresh duplicate row.
    """
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
            if rec.get("business_type"):
                notes_parts.append(f"Business type: {rec['business_type']}")
            if rec.get("package"):
                notes_parts.append(f"Package: {rec['package']}")
            if rec.get("source_slug"):
                notes_parts.append(f"[Mini-site: /b/{rec['source_slug']}]")
            else:
                notes_parts.append("[Website inquiry form]")
            new_notes = "\n".join(notes_parts)

            existing = db.query(Lead).filter(Lead.phone == rec["phone"]).first()
            if existing is not None:
                stamp = datetime.utcnow().isoformat()
                existing.notes = (
                    f"{existing.notes or ''}\n[Repeat inquiry {stamp}]\n{new_notes}".strip()
                )
                existing.updated_at = datetime.utcnow()
                db.commit()
                return existing.id

            lead = Lead(
                id=str(uuid.uuid4()),
                company_name=(rec.get("business_name") or "Unknown")[:255],
                contact_name=(rec.get("name") or "")[:255] or None,
                phone=rec["phone"],
                niche=(rec.get("niche") or None),
                city=(rec.get("city") or None),
                source=LeadSource.WEBSITE,
                status=LeadStatus.NEW,
                notes=new_notes,
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


async def _auto_callback(
    phone: str,
    niche: str,
    business: str,
    client_id: str = "",
    opening_line: str = "",
    dry_run: bool = False,
) -> None:
    """Fire-and-forget: inquiry phone pe conversational AI call try karo.

    client_id (2026-07-02): a mini-site inquiry belongs to a specific paying
    client — without it, the call greeted as generic "Demo Co"/"LeadGen AI"
    instead of that business, skipped KB grounding (TelecallerBrain uses
    client_id for RAG), never showed up in that client's own CallLog/dashboard,
    and skipped the auto-qualify->CRM/sales downstream wiring (gated on
    `self.client_id` in vobiz_stream.py). Platform-level leads (no client yet,
    e.g. leadsgenai.in's own /audit funnel) correctly pass "" — unchanged."""
    try:
        from app.api.telephony_vobiz import start_stream_call

        result = await start_stream_call(
            to=phone,
            niche=niche or "general",
            client_id=client_id or None,
            opening_line=opening_line or "",
            dry_run=dry_run,
        )
        result = result or {}
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
                    "client_id": client_id or "",
                    "dry_run": bool(dry_run),
                },
            )
        except Exception:
            pass
        if not placed:
            logger.info(
                f"[public] auto-callback not placed for ***{str(phone)[-4:]}: {result.get('error')}"
            )
        elif not dry_run:
            # Real call hi side-effects deta hai — dry-run smoke business
            # ledgers (speed_to_lead / delivery) ko pollute nahi karta.
            try:
                from app.platform.speed_to_lead import log_callback_touch

                log_callback_touch(phone, placed=True)
            except Exception:
                pass
            if client_id:
                try:
                    from app.marketing import delivery_ledger

                    delivery_ledger.log_event(
                        client_id, "followup_sent", detail=f"AI callback → {business}"
                    )
                except Exception:
                    pass
    except Exception as e:  # absolute guard — task me unhandled exception nahi
        logger.warning(f"[public] auto-callback failed for ***{str(phone)[-4:]}: {e}")
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
    email: str | None = Field(None, max_length=254)  # optional — sales_autopilot email channel feed
    niche: str | None = Field(None, max_length=60)
    business_type: str | None = Field(
        None, max_length=60
    )  # wizard business-type id/label (audit funnel)
    city: str | None = Field(None, max_length=100)
    message: str | None = Field(None, max_length=1000)
    package: str | None = Field(None, max_length=40)  # Starter/Growth/Advanced (pricing card se)
    source_slug: str | None = Field(None, max_length=80)  # mini-site /b/{slug} se aayi inquiry
    preferred_time: str | None = Field(None, max_length=80)  # booking form ka "pasand ka time"
    utm_source: str | None = Field(
        None, max_length=80
    )  # channel attribution (quora/reddit/seo/...) — bandit seekhta
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
async def submit_inquiry(body: InquiryIn, request: Request, dry_run: bool = False):
    """Landing page ka lead form — NO AUTH. Validate → file+DB save → team log.

    dry_run=1 (verification smoke only): poora chain chalta hai (store →
    wizard opening resolve → auto-callback → pending + answer-url) par ASLI
    Vobiz call nahi lagta. No real call = no cost/no compliance side-effects.
    """
    # 1) Honeypot: bots hidden "website" field bhar dete hain — ok bolo, ignore karo.
    if (body.website or "").strip():
        return {"ok": True, "message": _OK_MESSAGE}

    # 2) Rate limit (5/min/IP) — Redis-first, in-memory fallback
    ip = _client_ip(request)
    await _rate_check(ip, "inquiry")

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

    email_raw = (body.email or "").strip().lower()[:254]
    email = (
        email_raw if email_raw and "@" in email_raw and "." in email_raw.split("@")[-1] else None
    )

    rec: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "at": datetime.utcnow().isoformat() + "Z",
        "name": name[:120],
        "business_name": business[:200],
        "phone": phone,
        "email": email,
        "niche": ((body.niche or "").strip()[:50] or None),
        "business_type": ((body.business_type or "").strip()[:60] or None),
        "city": ((body.city or "").strip()[:100] or None),
        "message": ((body.message or "").strip()[:1000] or None),
        "package": ((body.package or "").strip()[:40] or None),
        "preferred_time": ((body.preferred_time or "").strip()[:80] or None),
        "utm_source": ((body.utm_source or "").strip().lower()[:80] or None),
        "source_slug": source_slug,
        "client_id": mini_client_id,
        "source": "mini_site" if source_slug else "website",
        "ip": ip,
    }

    # 4) File FIRST (never-lose guarantee), phir DB best-effort.
    # JSONL/SQLite writes are synchronous; keep them off the ASGI event loop.
    stored_file = await asyncio.to_thread(_append_jsonl, rec)
    lead_id = await asyncio.to_thread(_save_lead_db, rec)
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
            dry_run=bool(dry_run),
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
    ref_code: str | None = Field(
        "", max_length=80
    )  # affiliate referral code (optional, from ?ref= URL param)
    website: str | None = Field("", max_length=200)  # honeypot — insaan kabhi nahi bharta
    # REAL website field (audit 2026-07-04): honeypot ne `website` naam le liya tha,
    # isliye self-serve signup se kabhi site capture nahi hoti thi -> AUTO_ONBOARD ka
    # website->KB seed is funnel ke liye dead tha. Optional; SSRF guard fetch-time pe.
    business_website: str | None = Field("", max_length=200)


@router.post(
    "/signup", dependencies=[Depends(rate_limit("signup", 10, 60)), Depends(verify_turnstile)]
)
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

    # 1) Rate limit (5/min/IP — Redis-first, in-memory fallback)
    ip = _client_ip(request)
    try:
        await _rate_check(ip, "signup")
    except HTTPException:
        # Enhanced 429 response: Retry-After header + structured detail so
        # pricing.html can show "X seconds me phir try" + ops audit log.
        wait_s = int(_RL_WINDOW_S)
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                job_type="signup_rate_limited",
                status="failed",
                output_summary=f"IP {ip} tripped signup bucket (5/min)",
                triggered_by="signup",
                meta_json={"ip": ip, "scope": "signup_ip"},
            )
        except Exception as _log_err:
            logger.debug(f"[signup] rate_limited log emit skip: {_log_err}")
        raise HTTPException(
            status_code=429,
            detail={
                "error": "rate_limited",
                "message": f"Thoda ruk ke dobara try karo ({wait_s}s).",
                "retry_after": wait_s,
                "scope": "signup_ip",
            },
            headers={"Retry-After": str(wait_s)},
        )

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
    # Loop 13B (2026-07-10): block the most obvious credential-stuffing targets.
    # Small conservative list — real customers with these passwords are indistinguishable
    # from bot signups, and blocking here prevents an account whose first login attempt
    # would tripwire our Loop 8 `login_failed` monitoring. Never leak the list to the
    # attacker; return a generic "safer password" hint.
    _BREACHED = {
        "password",
        "password1",
        "123456",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty",
        "abc123",
        "111111",
        "000000",
        "admin",
        "welcome",
        "letmein",
        "iloveyou",
        "monkey",
        "dragon",
        "master",
        "shadow",
        "sunshine",
        "princess",
    }
    if pw.strip().lower() in _BREACHED:
        raise HTTPException(
            status_code=422,
            detail="Yeh password bahut common hai — kuch alag choose karein (kam se kam 8 char).",
        )

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

        plan_input = (body.plan or "starter").strip().lower()
        if plan_input not in ("starter", "growth", "advanced", "trial"):
            plan_input = "starter"
        body.plan = plan_input

        client = add_client(
            business_name=biz,
            niche=(body.niche or "general"),
            city=(body.city or ""),
            phone=(body.phone or ""),
            plan=plan_input,
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

    # 4.5) Business website (optional) — AUTO_ONBOARD sweep isse KB seed karta hai.
    #      Best-effort: bina scheme wale input pe https:// laga do; junk (no dot) skip.
    try:
        site = (body.business_website or "").strip()[:200]
        if site and "." in site:
            if not site.lower().startswith(("http://", "https://")):
                site = "https://" + site
            from app.marketing.clients_store import update_client as _upd

            _upd(cid, website=site)
    except Exception as e:
        logger.debug(f"[signup] website save skip (account still ok): {e}")

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
    # Loop 23 (2026-07-10): race-safe register. If another concurrent submit with
    # the same email raced past the login_exists check above and already claimed
    # this email for a different client_id, register_login refuses to overwrite
    # and returns `email_claimed`. We then reject THIS submit with the same 409
    # the initial dedupe check uses — no orphan credential row, no silent takeover.
    _reg = register_login(email, pw, cid, allow_reassign=False)
    if _reg and _reg.get("error") == "email_claimed":
        raise HTTPException(
            status_code=409,
            detail="Yeh email already registered hai — login karo.",
        )
    token: str | None = None
    # ENTERPRISE FIX (2026-07-10 onboarding audit): pehle `token=None` silently
    # respond kar diya jaata tha `access_token: null` ke saath — FE (pricing.html:377)
    # `token = d.access_token || ""` karke PAID checkout pe empty Bearer bhejta,
    # `/api/billing/checkout` 401 return karta, aur user ko fallback ka koi signal
    # nahi milta. Ab explicit `auto_login: bool` + `next.url=/app/login` guidance
    # response me daal ke FE explicitly branch kar sake. Account creation still
    # succeeds (idempotent password login intact) — sirf auto-login ka signal honest.
    auto_login = True
    try:
        # Import via module (not `from app.api.admin import ...`) so tests can
        # monkeypatch `app.api.admin.create_access_token` and see the effect here.
        from app.api import admin as _admin_mod

        token = _admin_mod.create_access_token(cid, email, "customer")
    except Exception as e:
        # Escalated DEBUG→WARNING so ops sees this the moment JWT config regresses
        # (missing JWT_SECRET / bad key / jwt import shim etc.). If this ever fires
        # in prod, login for ALL customers will also be broken — it's not a debug event.
        auto_login = False
        logger.warning(
            "[signup] auto-login token mint FAILED for cid=%s email=%s — client will "
            "need manual login (%s: %s)",
            cid,
            email,
            type(e).__name__,
            e,
        )
        # Loop 2 (2026-07-10): surface this in the admin Delivery Command Center's
        # Automation Runs panel (already live via /api/admin/automation-logs). Ops
        # sees the failure count without grepping app logs. Best-effort — signup
        # NEVER fails because of a downstream logging hiccup.
        try:
            from app.platform import automation_log_service as _als

            _als.log_event(
                client_id=cid,
                job_type="signup_auto_login_failed",
                status="failed",
                error_message=f"{type(e).__name__}: {e}"[:500],
                output_summary="Account created, JWT mint failed → customer must login manually",
                triggered_by="signup",
                meta_json={"email": email, "plan": (body.plan or "starter")},
            )
        except Exception as _log_err:
            logger.debug(f"[signup] automation_log emit skip: {_log_err}")

    # 6.5) PLAN PROVISIONING (audit #7): paid plan ka usage-period + minutes provision karo
    #      (activate_plan + reset_usage_period). Pehle yeh sirf orphan customer_signup me tha
    #      (jiska koi caller nahi tha) — ab is CANONICAL path pe, taaki pricing-funnel se aaya
    #      paid customer ka quota signup pe hi set ho jaye. Trial pe SKIP (₹0; trial-fields upar
    #      already set hote). Best-effort — signup KABHI is wajah se fail nahi hota.
    #
    #      ENTERPRISE FIX (2026-07-10): pehle failure DEBUG pe silent hota tha — customer
    #      pay karta, checkout 200, par plan quota ZERO (no minutes, no features).
    #      Ab return values capture karo, WARNING log karo, aur response me
    #      `plan_provisioned: bool` bhejo taaki FE + admin dashboard detect kar sake.
    #      Payment ke BAAD (webhook ya admin UPI approval) phir se `_provision_usage`
    #      call hota hai — yeh pre-payment safety-net hai, post-payment guarantee nahi.
    plan_provisioned = False
    if not is_trial:
        plan_k = body.plan or "starter"
        try:
            from app.billing import usage as _usage

            plan_ok = _usage.activate_plan(cid, plan_k)
            watermark_ok = _usage.reset_usage_period(cid)
            plan_provisioned = bool(plan_ok and watermark_ok)
            if not plan_provisioned:
                logger.warning(
                    "[signup] plan provisioning PARTIAL for cid=%s plan=%s "
                    "(activate=%s reset=%s) — customer MUST get post-payment provisioning",
                    cid,
                    plan_k,
                    plan_ok,
                    watermark_ok,
                )
                try:
                    from app.platform import ops_alerts

                    ops_alerts._ntfy(
                        f"Signup provisioning PARTIAL — {cid}",
                        f"plan={plan_k} activate={plan_ok} reset={watermark_ok}. "
                        "Customer has zero quota until admin fixes.",
                        tags=["rotating_light", "billing"],
                    )
                except Exception:
                    pass
        except Exception as e:
            logger.warning(
                "[signup] plan provisioning RAISED for cid=%s plan=%s — "
                "customer will have ZERO quota until post-payment fix (%s: %s)",
                cid,
                plan_k,
                type(e).__name__,
                e,
            )
            try:
                from app.platform import ops_alerts

                ops_alerts._ntfy(
                    f"Signup provisioning CRASHED — {cid}",
                    f"plan={plan_k} error={type(e).__name__}: {e}. "
                    "Customer has ZERO quota until admin fixes.",
                    tags=["rotating_light", "billing"],
                )
            except Exception:
                pass

    # 6.8) Funnel event (audit 2026-07-04) — silent no-op without POSTHOG_API_KEY.
    try:
        from app.analytics import posthog_client as _ph

        _ph.capture(cid, "signup", {"plan": body.plan, "trial": is_trial, "via": "pricing_page"})
    except Exception:
        pass

    # 6.9) Welcome WhatsApp to the customer who just signed up (audit 2026-07-04
    #      user-ask). Consented/transactional (they gave their number + created an
    #      account this instant) — NOT bulk marketing. Best-effort, never blocks
    #      signup; no-ops gracefully until the WhatsApp engine is armed (WAHA QR
    #      scan / Cloud creds). Gated WHATSAPP_WELCOME (default ON).
    if (os.environ.get("WHATSAPP_WELCOME", "1") or "1").strip().lower() not in ("0", "false", "no"):
        _wa_to = (body.phone or "").strip()
        if _wa_to:
            try:
                import asyncio as _aio

                from app.integrations.whatsapp import get_whatsapp_sender

                if is_trial:
                    _wa_msg = (
                        f"Namaste {biz}! 🎉 Aapka LeadGen AI FREE trial shuru ho gaya.\n\n"
                        "Login: https://leadsgenai.in/app/login\n"
                        f"Email: {email}\n\n"
                        "Roz ki AI marketing posts, Google par upar aana, aur leads — "
                        "sab automatic. Koi dikkat ho to isi number pe reply karein."
                    )
                else:
                    _wa_msg = (
                        f"Namaste {biz}! ✅ Aapka LeadGen AI account ban gaya "
                        f"({body.plan or 'starter'} plan).\n\n"
                        "Login: https://leadsgenai.in/app/login\n"
                        f"Email: {email}\n\n"
                        "Payment confirm hote hi sab AI marketing features chalu ho jayenge."
                    )
                _sender = get_whatsapp_sender()
                if _sender is not None:
                    _coro = _sender.send_text_message(_wa_to, _wa_msg)
                    try:
                        _loop = _aio.get_running_loop()
                        _loop.create_task(_coro)  # fire-and-forget; signup never waits
                    except RuntimeError:
                        _aio.run(_coro)
            except Exception as e:
                logger.debug(f"[signup] welcome WhatsApp skip (account still ok): {e}")

    # 6.95) DAY-1 VALUE — enqueue the done-for-you auto-onboard (website→KB seed +
    #       first content pack + customer-visible content QUEUE + niche snapshot) to
    #       the WORKER, so the new customer's portal isn't empty until the next-day
    #       content job. Runs regardless of the AUTO_ONBOARD hourly-sweep flag; the
    #       sweep stays the backstop (auto_onboard marks setup_done → idempotent).
    #       send_welcome=False — signup already sent its welcome above. Heavy work
    #       stays in Celery (web process never scrapes/LLMs). Gated SIGNUP_AUTO_ONBOARD
    #       (default ON); never blocks signup.
    if (os.environ.get("SIGNUP_AUTO_ONBOARD", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
    ):
        try:
            from app.tasks.staff_jobs import onboard_client

            onboard_client.delay(cid, False)
        except Exception as e:
            logger.debug(f"[signup] onboard enqueue skip (hourly sweep is backstop): {e}")

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

    # Voice follow-up — trial day 8/9 conversion calls (transactional, consented).
    if is_trial and (body.phone or "").strip():
        try:
            from app.telephony import voice_followup

            voice_followup.schedule_trial_callbacks(
                phone=str(body.phone or ""),
                client_id=cid,
                business_name=biz,
                niche=str(body.niche or "ai_marketing"),
                source="signup_trial",
            )
        except Exception as e:
            logger.debug(f"[signup] voice trial schedule skip: {e}")

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

    # Loop 3B (2026-07-10): admin GTM visibility — emit a `signup_completed` row
    # for EVERY successful signup (trial + paid). The admin Delivery Command
    # Center's Automation Runs panel filters by job_type so ops can count
    # new customers per day/week without a separate CRM query. Best-effort
    # (never blocks the response; failure row is already covered by Loop 2).
    try:
        from app.platform import automation_log_service as _als

        _als.log_event(
            client_id=cid,
            job_type="signup_completed",
            status="success",
            output_summary=f"{biz} ({body.plan or 'starter'}){' [trial]' if is_trial else ''}",
            triggered_by="signup",
            meta_json={
                "email": email,
                "plan": (body.plan or "starter"),
                "trial": is_trial,
                "auto_login": auto_login,
                "plan_provisioned": plan_provisioned,
                "via": "pricing_page",
            },
        )
    except Exception as _log_err:
        logger.debug(f"[signup] automation_log signup_completed skip: {_log_err}")

    out: dict[str, Any] = {
        "ok": True,
        "client_id": cid,
        "access_token": token,
        "auto_login": auto_login,
        "token_type": "bearer",
        "business_name": (client or {}).get("business_name"),
        "slug": (client or {}).get("slug"),
        "plan": (client or {}).get("plan"),
        "plan_provisioned": plan_provisioned,
    }
    # If auto-login couldn't be issued (rare — JWT config regression), hand the FE
    # explicit fallback guidance so the paid checkout path doesn't 401 blind. Trial
    # path already redirects on empty token; this keeps paid honest too.
    if not auto_login:
        out["next"] = {
            "url": "/app/login",
            "email": email,
            "reason": "auto_login_unavailable",
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

        # Pay modal me 2 public marketing plans (starter + advanced); legacy growth hidden,
        # taaki checkout flow landing pricing aur billing truth ke saath consistent rahe.
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


@router.get("/business-types")
async def public_business_types():
    """PUBLIC lead-magnet catalog — audit/site-audit forms isse dropdown bharate
    hain; visitor apna business type select karta hai to inquiry `niche` ke saath
    aati hai (lead + auto-callback niche-aware). Read-only, no auth — sirf
    wizard catalog ke labels/niches hain, koi PII nahi."""
    try:
        from app.marketing.onboard_wizard import BUSINESS_TYPES

        return {
            "ok": True,
            "business_types": [
                {
                    "id": b["id"],
                    "label": b["label"],
                    "emoji": b.get("emoji", ""),
                    "niche": b["niche"],
                }
                for b in BUSINESS_TYPES
            ],
        }
    except Exception as e:  # pragma: no cover - fail-open: dropdown ke bina form chalta hai
        logger.warning(f"[public] business-types failed: {e}")
        return {"ok": True, "business_types": []}


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
    await _rate_check(ip, "audit")

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
