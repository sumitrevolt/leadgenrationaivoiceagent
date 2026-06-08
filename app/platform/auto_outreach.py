"""
Auto Email Outreach — system KHUD scraped prospects ko cold email bhejta hai.
=============================================================================

WhatsApp bulk auto-send = number ban (isliye wo 1-human-click hai). Email
LEGALLY automate ho sakta hai — scraped business ki website se email nikla
(prospector capture karta hai), uspe personalized Hinglish+English cold email
auto-jaata hai. Yeh Rohan (Leads Manager) ka kaam hai.

Public API (sab import-safe, KABHI raise nahi karte):
  - run_email_outreach(limit=None) -> dict   (async; bhejta hai, marks "emailed")
  - outreach_stats() -> dict                 (counts: total/with_email/emailed/pending)
  - _email_subject_body(prospect) -> (subject, text, html)

Guards (har layer):
  - settings.auto_email_outreach False  -> {"skipped": "AUTO_EMAIL_OUTREACH off"}
  - SMTP unset (settings.smtp_user)     -> {"skipped": "smtp_unset"} + warn log
  - daily cap = settings.outreach_daily_cap (env OUTREACH_DAILY_CAP)
  - per-send try/except — ek fail dusre ko nahi rokta
  - bheje hue prospects dobara email NAHI hote (emailed_at marker)
  - sends ke beech ~2-4s sleep (domain reputation safety)

Scheduler (team_scheduler) roz 10:30 IST chalata hai — flag+SMTP off ho to no-op.
"""
from __future__ import annotations

import asyncio
import html as _html
import random
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Public links (footer + CTAs) — landing/audit + WhatsApp.
_AUDIT_URL = "https://leadsgenai.in/audit"
_SITE_URL = "https://leadsgenai.in"
_WA_LINK = "https://wa.me/918459012607"

# Gentle throttle between sends (domain reputation). Seconds.
_SLEEP_MIN_S = 2.0
_SLEEP_MAX_S = 4.0

# Unsubscribe line — har mail me (anti-spam compliance + courtesy).
_UNSUB_LINE = (
    "Agar yeh emails nahi chahiye to is mail ka reply REMOVE likh ke kar dijiye "
    "— hum turant hata denge."
)


def _from_name() -> str:
    try:
        from app.config import settings

        return (getattr(settings, "outreach_from_name", "") or "Sumit — LeadGen AI").strip()
    except Exception:
        return "Sumit — LeadGen AI"


def _email_subject_body(prospect: Dict[str, Any]) -> Tuple[str, str, str]:
    """Personalized Hinglish+English cold email — (subject, text, html).

    Real Google signal (rating/reviews) ho to acknowledge karta hai. FREE GBP
    audit + 3 sample posters + ₹2,999/mo marketing offer + audit link + WA.
    Polite unsubscribe + sender footer. Professional, spammy NAHI (no ALL-CAPS
    shouting, minimal emoji). KABHI raise nahi karta — fields missing ho to bhi
    sane defaults.
    """
    try:
        name = str((prospect or {}).get("business_name") or "").strip() or "aapke business"
        city = str((prospect or {}).get("city") or "").strip()
        try:
            reviews = prospect.get("reviews_count")
            reviews = int(reviews) if reviews is not None else None
        except Exception:
            reviews = None
        try:
            rating = prospect.get("rating")
            rating = float(rating) if rating is not None else None
        except Exception:
            rating = None

        from_name = _from_name()

        # --- subject ---
        subject = f"{name} — aapka Google profile (free audit)"

        # --- opening line: real signal acknowledge karo (warm, not creepy) ---
        if reviews is not None and reviews > 0 and rating is not None and rating > 0:
            opener = (
                f"Maine {name} ka Google profile dekha — {rating}⭐ rating "
                f"aur {reviews} reviews. Achhi shuruat hai!"
            )
        elif reviews is not None and reviews > 0:
            opener = (
                f"Maine {name} ka Google profile dekha — aapke {reviews} reviews "
                f"hain. Achhi baat hai!"
            )
        elif city:
            opener = f"Maine {city} me {name} ka Google profile dekha."
        else:
            opener = f"Maine {name} ka Google profile dekha."

        # --- plain text body ---
        text_lines = [
            "Namaste,",
            "",
            opener,
            "",
            "Main " + from_name + " se hoon. Hum chhote businesses ka online "
            "marketing sambhalte hain — Google profile, reviews, aur regular "
            "social media posts taaki aapko naye customers mile.",
            "",
            "Aapke liye main yeh FREE bhej sakta hoon:",
            "  - Ek free Google profile audit (score + kya improve karein)",
            "  - 3 sample posters aapke business ke naam ke saath",
            "",
            "Pasand aaye to poora marketing sirf ₹2,999/mahina se shuru hota "
            "hai — koi lambi commitment nahi.",
            "",
            "2 minute me apna free audit yahan le lijiye: " + _AUDIT_URL,
            "Ya WhatsApp pe baat kijiye: " + _WA_LINK,
            "",
            _UNSUB_LINE,
            "",
            "Shukriya,",
            from_name,
            "LeadGen AI — " + _SITE_URL,
        ]
        text = "\n".join(text_lines)

        # --- HTML body (clean, light) ---
        e = _html.escape
        html_body = (
            '<html><body style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;line-height:1.5;color:#222;max-width:600px;margin:0 auto;">'
            "<p>Namaste,</p>"
            f"<p>{e(opener)}</p>"
            f"<p>Main {e(from_name)} se hoon. Hum chhote businesses ka online "
            "marketing sambhalte hain — Google profile, reviews, aur regular "
            "social media posts taaki aapko naye customers mile.</p>"
            "<p>Aapke liye main yeh <b>FREE</b> bhej sakta hoon:</p>"
            "<ul>"
            "<li>Ek free Google profile audit (score + kya improve karein)</li>"
            "<li>3 sample posters aapke business ke naam ke saath</li>"
            "</ul>"
            "<p>Pasand aaye to poora marketing sirf <b>₹2,999/mahina</b> se "
            "shuru hota hai — koi lambi commitment nahi.</p>"
            f'<p><a href="{e(_AUDIT_URL)}" '
            'style="background:#4f46e5;color:#fff;padding:10px 18px;'
            'border-radius:6px;text-decoration:none;display:inline-block;">'
            "Free Audit le lijiye</a></p>"
            f'<p>Ya WhatsApp pe baat kijiye: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#888;font-size:12px;">{e(_UNSUB_LINE)}</p>'
            f"<p>Shukriya,<br>{e(from_name)}<br>"
            f'LeadGen AI — <a href="{e(_SITE_URL)}">{e(_SITE_URL)}</a></p>'
            "</body></html>"
        )
        return subject, text, html_body
    except Exception as e:  # absolute guard — never raise
        logger.debug(f"[auto_outreach] subject/body build failed: {e}")
        fb_name = str((prospect or {}).get("business_name") or "aapke business")
        from_name = _from_name()
        subject = f"{fb_name} — free Google profile audit"
        text = (
            "Namaste,\n\n"
            f"Main {from_name} se hoon. Hum chhote businesses ka online marketing "
            "sambhalte hain. Free Google profile audit + 3 sample posters bhej "
            f"sakta hoon. Yahan le lijiye: {_AUDIT_URL}\n\n"
            f"{_UNSUB_LINE}\n\nShukriya,\n{from_name}\nLeadGen AI — {_SITE_URL}"
        )
        return subject, text, text


def _valid_email(addr: str) -> bool:
    a = (addr or "").strip()
    return "@" in a and "." in a.split("@")[-1] and len(a) >= 6


async def run_email_outreach(limit: Optional[int] = None) -> Dict[str, Any]:
    """Ready prospects (jinka email hai aur abhi tak email nahi gaya) ko
    personalized cold email auto-bhejo. NEVER raises.

    Returns: {"sent": n, "skipped_no_email": x, "failed": y, "cap": c, ...}
    ya {"skipped": "<reason>"} jab flag/SMTP off ho.
    """
    result: Dict[str, Any] = {"sent": 0, "skipped_no_email": 0, "failed": 0, "cap": 0}
    try:
        from app.config import settings

        if not bool(getattr(settings, "auto_email_outreach", False)):
            return {"skipped": "AUTO_EMAIL_OUTREACH off"}

        # API key (Resend/Brevo) ya SMTP — koi bhi ek configured ho to chalega.
        _api = False
        try:
            from app.integrations.email_api import api_available
            _api = api_available()
        except Exception:
            _api = False
        if not _api and not (getattr(settings, "smtp_user", "") or "").strip():
            logger.warning("[auto_outreach] na API key na SMTP — outreach skipped")
            return {"skipped": "email_unconfigured"}

        from app.platform import prospector

        # Pick: status ready + email present + not already emailed.
        candidates: List[Dict[str, Any]] = []
        for p in prospector.list_prospects(status="ready", limit=500):
            email = str(p.get("email") or "").strip()
            if not _valid_email(email):
                result["skipped_no_email"] += 1
                continue
            if p.get("emailed_at"):
                continue  # already emailed — never re-send
            candidates.append(p)

        try:
            daily_cap = int(getattr(settings, "outreach_daily_cap", 25))
        except Exception:
            daily_cap = 25
        daily_cap = max(0, daily_cap)
        cap = daily_cap if limit is None else max(0, min(int(limit), daily_cap or int(limit)))
        result["cap"] = cap

        if cap <= 0 or not candidates:
            result["candidates"] = len(candidates)
            return result

        batch = candidates[:cap]

        from app.integrations.email_sender import EmailSender

        sender = EmailSender()

        for idx, p in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            try:
                subject, text, html_body = _email_subject_body(p)
                ok = False
                try:
                    ok = bool(await sender.send_email([to_addr], subject, text, html_body))
                except Exception as e:
                    logger.warning(f"[auto_outreach] send to {to_addr} failed: {e}")
                    ok = False

                if ok:
                    # Mark so it's never re-emailed (keep status "ready" so the
                    # WhatsApp/human pipeline still sees it; emailed_at is the
                    # de-dup marker).
                    try:
                        if pid:
                            prospector.set_prospect_fields(
                                pid,
                                {"emailed_at": datetime.utcnow().isoformat() + "Z"},
                            )
                    except Exception:
                        pass
                    result["sent"] += 1
                    _log_event("email_sent", f"{biz} ({to_addr})")
                else:
                    result["failed"] += 1
            except Exception as e:
                result["failed"] += 1
                logger.debug(f"[auto_outreach] prospect {pid} email error: {e}")

            # Gentle throttle (skip after the last one).
            if idx < len(batch) - 1:
                try:
                    await asyncio.sleep(random.uniform(_SLEEP_MIN_S, _SLEEP_MAX_S))
                except Exception:
                    pass

        _log_event(
            "email_outreach_run",
            f"{result['sent']} emails bheje, {result['failed']} fail, cap {cap}",
            status="ok" if result["failed"] == 0 else "warn",
            meta=dict(result),
        )
        logger.info(f"[auto_outreach] run done: {result}")
        return result
    except Exception as e:  # absolute guard
        logger.warning(f"[auto_outreach] run_email_outreach failed: {e}")
        result["error"] = str(e)
        return result


def outreach_stats() -> Dict[str, Any]:
    """Email-outreach counts: total prospects / with_email / emailed / pending.
    KABHI raise nahi karta (failure pe zeros)."""
    stats = {"total": 0, "with_email": 0, "emailed": 0, "pending": 0}
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=500)
        stats["total"] = len(rows)
        for r in rows:
            has_email = _valid_email(str(r.get("email") or ""))
            if has_email:
                stats["with_email"] += 1
            if r.get("emailed_at"):
                stats["emailed"] += 1
            elif has_email and (r.get("status") or "ready") == "ready":
                stats["pending"] += 1
    except Exception as e:
        logger.debug(f"[auto_outreach] outreach_stats failed: {e}")
    return stats


def _log_event(action: str, summary: str, status: str = "ok",
               meta: Optional[Dict[str, Any]] = None) -> None:
    """Rohan ke naam se team event (best-effort)."""
    try:
        from app.platform.team import log_event

        log_event("rohan", action, summary, status=status, meta=meta or {})
    except Exception:
        pass


__all__ = ["run_email_outreach", "outreach_stats", "_email_subject_body"]
