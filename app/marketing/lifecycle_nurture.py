"""Lifecycle Nurture — signup -> paid conversion sequence (Dittofeed/Laudspeaker
pattern, free-stack).

2026 research (ChartMogul): median free->paid ~8%; behavioral day-0/2/7 sequence
conversion double karti. Self-serve signup (pricing.html -> /api/public/signup)
ke baad jo PAY nahi karte unhe yeh engine Hinglish activation emails bhejta:

  day 0  welcome + quick-start    day 2  activation nudge (demo/audit try karo)
  day 5  ROI angle (missed-call revenue)   day 7  upgrade offer
  day 12 last-call offer -> sequence end

Har run pe PAID-CHECK: client ki active subscription mili to status=converted,
aage kuch nahi bhejta (behavioral exit). GATED `LIFECYCLE_NURTURE=1` (default
OFF = run_due no-op). Signup pe enroll hamesha RECORD hota (additive, send nahi).
Store: data/lifecycle_nurture.jsonl + lifecycle_runs.jsonl. Kabhi raise nahi.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_STORE = os.path.join("data", "lifecycle_nurture.jsonl")
_RUNS = os.path.join("data", "lifecycle_runs.jsonl")

PRICING_URL = "https://leadsgenai.in/pricing"
DEMO_URL = "https://leadsgenai.in/demo"
AUDIT_URL = "https://leadsgenai.in/audit"
LOGIN_URL = "https://leadsgenai.in/app/login"

STEPS: list[dict[str, Any]] = [
    {"day": 0, "key": "welcome"},
    {"day": 2, "key": "activation"},
    {"day": 5, "key": "roi"},
    {"day": 7, "key": "upgrade"},
    {"day": 12, "key": "last_call"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _enabled() -> bool:
    return os.environ.get("LIFECYCLE_NURTURE", "0").strip().lower() in ("1", "true", "yes")


def _read(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


def _write_all(path: str, rows: list[dict[str, Any]]) -> None:
    # Lock + atomic — web (signup enroll) + celery (run_due) dono likhte hain.
    try:
        from app.utils.file_lock import locked_rewrite

        content = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in rows)
        if not locked_rewrite(path, content):
            logger.warning(f"[lifecycle] locked write failed: {path}")
    except Exception as e:
        logger.warning(f"[lifecycle] write {path} failed: {e}")


def _append(path: str, rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _plan_lines() -> str:
    """Upgrade-email ke liye PUBLIC pricing plans ki bullet-lines.

    Source-of-truth = packages.get_public_packages() (billing-truth) — sirf
    public plans (Starter ₹1,999 + Combo/Advanced ₹5,999); legacy hidden Growth
    ₹2,999 KABHI nahi (public:False). packages import fail ho to safe 2-line
    fallback (dono public prices, hardcoded Growth nahi). KABHI raise nahi.
    """
    try:
        from app.marketing.packages import get_public_packages

        lines: list[str] = []
        for p in get_public_packages():
            name = str(p.get("name") or "").strip()
            price = p.get("price_inr_month")
            tag = str(p.get("price_note") or p.get("tagline") or "").strip()
            if not name or not price:
                continue
            suffix = f" — {tag}" if tag else ""
            lines.append(f"• {name} ₹{int(price):,}/mo{suffix}")
        if lines:
            return "\n".join(lines) + "\n"
    except Exception as e:  # pragma: no cover - packages import-safe hai
        logger.debug(f"[lifecycle] plan lines fallback: {e}")
    # Fallback = public prices only (koi hidden Growth ₹2,999 nahi).
    return (
        "• AI Marketing Automation ₹1,999/mo — daily posts, GBP, reviews, posters\n"
        "• Combo — Marketing + AI Voice ₹5,999/mo — + AI voice calling feature (2-min inquiry callback)\n"
    )


def build_message(step_key: str, business_name: str, niche: str = "") -> dict[str, str]:
    """Hinglish nurture email (pure function — testable)."""
    biz = (business_name or "Aapka business").strip()
    if step_key == "welcome":
        subject = f"Welcome {biz} 🎉 — 5 minute me pehla AI post + audit"
        body = (
            f"Namaste {biz} team!\n\nAccount ban gaya. Shuru karne ke 3 quick steps:\n"
            f"1) Login karo: {LOGIN_URL}\n"
            f"2) Apna FREE Google profile audit dekho: {AUDIT_URL}\n"
            f"3) AI se pehla branded post banao (2 click): {DEMO_URL}\n\n"
            f"Koi sawal ho to is email ka reply karo — real insaan jawab dega.\n"
        )
    elif step_key == "activation":
        subject = f"{biz} — abhi tak pehla post try kiya? (2 minute lagta hai)"
        body = (
            f"Namaste,\n\nJo log pehle 2 din me apna pehla AI post bana lete hain, unhe "
            f"results sabse pehle dikhte hain. Try karo: {DEMO_URL}\n\n"
            f"Ya seedha login karke dashboard dekho: {LOGIN_URL}\n\nAtke ho? Reply karo, hum help karenge.\n"
        )
    elif step_key == "roi":
        subject = f"{biz} — har missed call ≈ ek khoya customer (calculation andar)"
        body = (
            f"Namaste,\n\nLocal business roz ke 3-5 inquiries miss karta hai — mahine ka "
            f"hazaaron ka nuksan. Hamara AI 2 minute me callback karta hai + leads "
            f"qualify karta hai.\n\nApna number calculate karo: {AUDIT_URL}\n"
            f"Plans (₹1,999 se shuru): {PRICING_URL}\n"
        )
    elif step_key == "upgrade":
        subject = f"{biz} — plan choose karo, aaj se marketing autopilot pe"
        body = (
            f"Namaste,\n\nAapka trial setup ready hai. Ab plan activate karo:\n\n"
            f"{_plan_lines()}\n"
            f"Activate: {PRICING_URL}\n\nUPI/card — 2 minute. Sawal ho to reply karo.\n"
        )
    else:  # last_call
        subject = f"{biz} — aakhri email: setup delete hone se pehle activate kar lo"
        body = (
            f"Namaste,\n\nYeh is sequence ka aakhri email hai. Aapka AI marketing setup "
            f"ready pada hai — activate karo to aaj se hi posts + lead capture chalu:\n\n"
            f"  {PRICING_URL}\n\nAbhi nahi karna? Koi baat nahi — jab ready ho, login "
            f"karke wahi se shuru kar sakte ho: {LOGIN_URL}\n"
        )
    return {"subject": subject, "body": body}


def enroll(
    email: str, business_name: str, client_id: str = "", plan: str = "starter"
) -> dict[str, Any]:
    """Signup hook: nurture me daalo (dedupe by email). Hamesha record (send nahi).
    Kabhi raise nahi."""
    try:
        em = (email or "").strip().lower()
        if not em or "@" not in em:
            return {"ok": False, "error": "valid email required"}
        rows = _read(_STORE)
        for r in rows:
            if r.get("email") == em:
                return {"ok": True, "rec": r, "dedupe": True}
        rec = {
            "id": uuid.uuid4().hex[:12],
            "email": em,
            "business_name": (business_name or "")[:120],
            "client_id": str(client_id or ""),
            "plan": (plan or "starter").lower(),
            "step_idx": 0,
            "status": "active",
            "enrolled_at": _now().isoformat(),
        }
        rows.append(rec)
        _write_all(_STORE, rows)
        return {"ok": True, "rec": rec}
    except Exception as e:
        logger.warning(f"[lifecycle] enroll failed: {e}")
        return {"ok": False, "error": str(e)}


async def _has_paid(client_id: str) -> bool:
    """Client ki active subscription? Error pe False (nurture continue — safe)."""
    if not client_id:
        return False
    try:
        from sqlalchemy import select

        from app.models.base import get_async_session
        from app.models.payment import Subscription

        async with get_async_session() as session:  # type: ignore
            res = await session.execute(
                select(Subscription).where(Subscription.client_id == str(client_id)).limit(5)
            )
            for s in res.scalars().all():
                if "active" in str(getattr(s, "status", "")).lower():
                    return True
    except Exception:
        pass
    return False


async def _send(to_email: str, subject: str, body: str) -> bool:
    try:
        from app.integrations.email_sender import email_sender

        return bool(await email_sender.send_email([to_email], subject, body))
    except Exception as e:
        logger.warning(f"[lifecycle] send failed: {e}")
        return False


async def run_due() -> dict[str, Any]:
    """Daily sweep. GATED LIFECYCLE_NURTURE=1 — off = no-op (zero change)."""
    if not _enabled():
        return {"enabled": False}
    sent = converted = 0
    try:
        rows = _read(_STORE)
        changed = False
        for rec in rows:
            if rec.get("status") != "active":
                continue
            try:
                idx = int(rec.get("step_idx") or 0)
                if idx >= len(STEPS):
                    rec["status"] = "finished"
                    changed = True
                    continue
                # behavioral exit: paid ho gaye -> converted, aur emails nahi
                if await _has_paid(rec.get("client_id", "")):
                    rec["status"] = "converted"
                    rec["converted_at"] = _now().isoformat()
                    converted += 1
                    changed = True
                    continue
                enrolled = datetime.fromisoformat(str(rec.get("enrolled_at")))
                if enrolled.tzinfo is None:
                    enrolled = enrolled.replace(tzinfo=timezone.utc)
                days = (_now() - enrolled).days
                step = STEPS[idx]
                if days < int(step["day"]):
                    continue
                msg = build_message(step["key"], rec.get("business_name", ""))
                ok = await _send(rec["email"], msg["subject"], msg["body"])
                _append(
                    _RUNS,
                    {
                        "rec_id": rec.get("id"),
                        "email": rec.get("email"),
                        "step": step["key"],
                        "auto_sent": ok,
                        **msg,
                        "at": _now().isoformat(),
                    },
                )
                rec["step_idx"] = idx + 1
                if rec["step_idx"] >= len(STEPS):
                    rec["status"] = "finished"
                sent += 1
                changed = True
            except Exception:
                continue
        if changed:
            _write_all(_STORE, rows)
        if sent or converted:
            try:
                from app.platform import team

                team.log_event(
                    "isha", "lifecycle_nurture", f"{sent} nurture emails, {converted} converted"
                )
            except Exception:
                pass
        return {"enabled": True, "sent": sent, "converted": converted}
    except Exception as e:
        logger.warning(f"[lifecycle] run_due failed: {e}")
        return {"enabled": True, "error": str(e)}


def stats() -> dict[str, Any]:
    """Funnel overview. Kabhi raise nahi."""
    try:
        rows = _read(_STORE)
        return {
            "active": sum(1 for r in rows if r.get("status") == "active"),
            "converted": sum(1 for r in rows if r.get("status") == "converted"),
            "finished": sum(1 for r in rows if r.get("status") == "finished"),
            "total": len(rows),
        }
    except Exception:
        return {"active": 0, "converted": 0, "finished": 0, "total": 0}
