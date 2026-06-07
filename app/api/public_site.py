"""
Public Site API — website inquiry form (lead capture) + admin inquiries view.
==============================================================================

Final paths (main.py prefix="/api" ke saath):
  POST /api/public/inquiry    -> NO AUTH — landing page ka form submit.
                                 Honeypot + per-IP rate limit + phone validation.
                                 DB Lead save best-effort; data/inquiries.jsonl
                                 me HAMESHA append (koi inquiry kabhi lost nahi).
                                 NOTIFY_EMAIL + SMTP set ho to owner ko email.
  GET  /api/public/inquiries  -> ADMIN — last 100 inquiries (jsonl + DB merged).
  GET  /api/public/pay-info   -> NO AUTH — UPI payment info (QR + VPA + plans)
                                 for the landing "Shuru karo" modal. UPI_VPA
                                 env empty ho to {"enabled": false}.

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
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/public", tags=["Public"])

# Append-only file backup — DB down ho tab bhi inquiry kabhi nahi khoti.
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")

_OK_MESSAGE = "Dhanyawad! 24 ghante me call aayega."

# --------------------------------------------------------------------------- #
# In-memory rate limit — max 5 inquiries / minute / IP (simple timestamp list)
# --------------------------------------------------------------------------- #
_RL: Dict[str, List[float]] = {}
_RL_MAX = 5
_RL_WINDOW_S = 60.0


def _client_ip(request: Optional[Request]) -> str:
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


def _rate_limited(ip: str) -> bool:
    """True = is IP ne 1 min me 5+ inquiries bheji (block karo)."""
    now = time.time()
    fresh = [t for t in _RL.get(ip, []) if now - t < _RL_WINDOW_S]
    if len(fresh) >= _RL_MAX:
        _RL[ip] = fresh
        return True
    fresh.append(now)
    _RL[ip] = fresh
    # Opportunistic cleanup taaki dict unbounded na badhe.
    if len(_RL) > 5000:
        for k in list(_RL.keys()):
            if not any(now - t < _RL_WINDOW_S for t in _RL[k]):
                _RL.pop(k, None)
    return False


def _clean_phone(raw: str) -> Optional[str]:
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


def _append_jsonl(rec: Dict[str, Any]) -> bool:
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


def _save_lead_db(rec: Dict[str, Any]) -> Optional[str]:
    """Lead model me best-effort save. Fail ho to None (jsonl me data hai hi)."""
    try:
        from app.models.lead import Lead, LeadSource, LeadStatus

        db = _db()
        if db is None:
            return None
        try:
            notes_parts: List[str] = []
            if rec.get("message"):
                notes_parts.append(f"Message: {rec['message']}")
            if rec.get("city"):
                notes_parts.append(f"City: {rec['city']}")
            if rec.get("niche"):
                notes_parts.append(f"Niche: {rec['niche']}")
            if rec.get("package"):
                notes_parts.append(f"Package: {rec['package']}")
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


def _read_jsonl(limit: int = 300) -> List[Dict[str, Any]]:
    """jsonl ki aakhri `limit` lines (parse-safe, corrupt lines skip)."""
    out: List[Dict[str, Any]] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return out
        with open(_INQUIRIES_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()[-max(1, limit):]
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
                meta={"niche": niche, "placed": placed,
                      "error": result.get("error"),
                      "stream_token": result.get("stream_token")},
            )
        except Exception:
            pass
        if not placed:
            logger.info(f"[public] auto-callback not placed for {phone}: {result.get('error')}")
    except Exception as e:  # absolute guard — task me unhandled exception nahi
        logger.warning(f"[public] auto-callback failed for {phone}: {e}")
        try:
            from app.platform.team import log_event

            log_event("swara", "auto_callback", f"Inquiry callback → {phone} — crash: {e}",
                      status="error")
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Owner email notification — best-effort, fire-and-forget.
# NOTIFY_EMAIL + SMTP_USER/SMTP_PASSWORD .env me ho tabhi bhejta hai; kuch bhi
# missing/fail ho to silent skip (inquiry flow kabhi affect nahi hota).
# --------------------------------------------------------------------------- #
async def _notify_inquiry_email(rec: Dict[str, Any]) -> None:
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
    name: str = ""
    business_name: str = ""
    phone: str = ""
    niche: Optional[str] = None
    city: Optional[str] = None
    message: Optional[str] = None
    package: Optional[str] = None  # Starter/Growth/Advanced (pricing card se)
    website: Optional[str] = ""  # honeypot — insaan ise kabhi nahi bharta


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
@router.post("/inquiry")
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
    if not name or not business:
        raise HTTPException(status_code=422, detail="Naam aur business ka naam dono zaroori hain.")
    phone = _clean_phone(body.phone or "")
    if not phone:
        raise HTTPException(status_code=422, detail="Phone number sahi nahi lag raha (10 digit chahiye).")

    rec: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "at": datetime.utcnow().isoformat() + "Z",
        "name": name[:120],
        "business_name": business[:200],
        "phone": phone,
        "niche": ((body.niche or "").strip()[:50] or None),
        "city": ((body.city or "").strip()[:100] or None),
        "message": ((body.message or "").strip()[:1000] or None),
        "package": ((body.package or "").strip()[:40] or None),
        "source": "website",
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

    # 5) Team activity (Rohan — Leads Manager) — kabhi raise nahi karta.
    try:
        from app.platform.team import log_event

        log_event(
            "rohan",
            "inquiry_received",
            f"{rec['business_name']} ({rec['niche'] or 'unknown'}) - {rec['phone']}",
            meta={"lead_id": lead_id, "city": rec.get("city"), "via": "website_form"},
        )
    except Exception:
        pass

    # 6) Auto-callback (Swara) — fire-and-forget AI call on the inquiry number.
    #    AUTO_CALLBACK_INQUIRY=0 se off; telephony na ho to bas error log hota.
    try:
        if os.environ.get("AUTO_CALLBACK_INQUIRY", "1").strip() != "0":
            task = asyncio.create_task(
                _auto_callback(rec["phone"], rec.get("niche") or "general", rec["business_name"])
            )
            _BG_TASKS.add(task)
            task.add_done_callback(_BG_TASKS.discard)
    except Exception as e:
        logger.debug(f"[public] auto-callback task spawn failed: {e}")

    # 7) Owner email alert — fire-and-forget; NOTIFY_EMAIL+SMTP unset = silent skip.
    try:
        ntask = asyncio.create_task(_notify_inquiry_email(dict(rec)))
        _BG_TASKS.add(ntask)
        ntask.add_done_callback(_BG_TASKS.discard)
    except Exception as e:
        logger.debug(f"[public] notify-email task spawn failed: {e}")

    return {"ok": True, "message": _OK_MESSAGE}


@router.get("/pay-info")
async def pay_info():
    """Landing page ka payment modal — NO AUTH. UPI_VPA env set ho tabhi
    enabled; QR upi_kit (pure-python encoder) se banta hai, packages
    app.marketing.packages se (key/name/price only). Kabhi raise nahi karta."""
    vpa = ""
    try:
        from app.config import settings

        vpa = (getattr(settings, "upi_vpa", "") or "").strip()
    except Exception:
        vpa = ""
    if not vpa:
        return {"enabled": False}

    out: Dict[str, Any] = {"enabled": True, "vpa": vpa}
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
        from app.marketing.packages import get_packages

        out["packages"] = [
            {
                "key": p.get("key"),
                "name": p.get("name"),
                "price_inr_month": p.get("price_inr_month"),
            }
            for p in (get_packages() or [])
        ]
    except Exception:
        out["packages"] = []
    return out


@router.get("/inquiries")
async def list_inquiries(current_user: User = Depends(require_admin)):
    """Admin view — last 100 inquiries, jsonl + DB (source=website) merged."""
    records: List[Dict[str, Any]] = []
    seen: Dict[str, Dict[str, Any]] = {}  # phone|business -> record (dedupe DB vs file)

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
                        seen[key]["lead_status"] = row.status.value if getattr(row, "status", None) else None
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
                                "lead_status": row.status.value if getattr(row, "status", None) else None,
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
