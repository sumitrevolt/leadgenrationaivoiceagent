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
from typing import Any

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


def _email_subject_body(prospect: dict[str, Any]) -> tuple[str, str, str]:
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


def _followup_subject_body(prospect: dict[str, Any], step: int) -> tuple[str, str, str]:
    """Multi-touch follow-up email — (subject, text, html). step 1 ya 2.

    Cold-email me ek touch kaafi nahi — log busy hote hain. Yeh DIFFERENT (chhota,
    polite) reminder bhejta hai jo pehle wale `_email_subject_body` se alag dikhe:
      step 1 (~3 din baad): "pichla email dekha? FREE audit ka offer abhi bhi khula"
      step 2 (~7 din baad): "last reminder" + ek concrete sample-poster idea
    Step 2 ke baad aur follow-up nahi (run_email_followups cap karta hai).
    KABHI raise nahi karta — fields missing ho to sane defaults.
    """
    try:
        name = str((prospect or {}).get("business_name") or "").strip() or "aapke business"
        from_name = _from_name()
        e = _html.escape

        if int(step) <= 1:
            # ---- Follow-up #1: gentle nudge ---- #
            subject = f"{name} ji — pichla email dekha? (free audit)"
            text_lines = [
                "Namaste,",
                "",
                f"{name} ji, kuch din pehle maine ek email bheja tha — shayad "
                "busy schedule me reh gaya ho.",
                "",
                "Bas yaad dilana chahta tha: aapke Google profile ka ek FREE audit "
                "(score + kya improve karein) + 3 sample posters ka offer abhi bhi "
                "khula hai. Koi charge nahi, koi commitment nahi.",
                "",
                "2 minute me yahan le lijiye: " + _AUDIT_URL,
                "Ya WhatsApp pe ek 'Hi' bhej dijiye: " + _WA_LINK,
                "",
                _UNSUB_LINE,
                "",
                "Shukriya,",
                from_name,
                "LeadGen AI — " + _SITE_URL,
            ]
            text = "\n".join(text_lines)
            html_body = (
                '<html><body style="font-family:Arial,Helvetica,sans-serif;'
                'font-size:15px;line-height:1.5;color:#222;max-width:600px;margin:0 auto;">'
                "<p>Namaste,</p>"
                f"<p>{e(name)} ji, kuch din pehle maine ek email bheja tha — shayad "
                "busy schedule me reh gaya ho.</p>"
                "<p>Bas yaad dilana chahta tha: aapke Google profile ka ek "
                "<b>FREE audit</b> (score + kya improve karein) + 3 sample posters "
                "ka offer abhi bhi khula hai. Koi charge nahi, koi commitment nahi.</p>"
                f'<p><a href="{e(_AUDIT_URL)}" '
                'style="background:#4f46e5;color:#fff;padding:10px 18px;'
                'border-radius:6px;text-decoration:none;display:inline-block;">'
                "Free Audit le lijiye</a></p>"
                f'<p>Ya WhatsApp pe ek "Hi" bhej dijiye: '
                f'<a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
                f'<p style="color:#888;font-size:12px;">{e(_UNSUB_LINE)}</p>'
                f"<p>Shukriya,<br>{e(from_name)}<br>"
                f'LeadGen AI — <a href="{e(_SITE_URL)}">{e(_SITE_URL)}</a></p>'
                "</body></html>"
            )
            return subject, text, html_body

        # ---- Follow-up #2: last reminder + concrete sample idea ---- #
        subject = f"{name} ji — aakhri reminder + ek poster idea"
        idea = (
            f'"{name} — aaj ka special!" wala ek festive poster, aapke naam aur '
            "phone ke saath — exactly aisa hum har hafte bana ke de sakte hain."
        )
        text_lines = [
            "Namaste,",
            "",
            f"{name} ji, yeh mera aakhri reminder hai — uske baad aapko pareshan " "nahi karunga.",
            "",
            "Ek chhota idea jo aapke kaam aa sakta hai:",
            idea,
            "",
            "Aisa free sample + Google profile audit dekhna ho to 2 minute lagenge: " + _AUDIT_URL,
            "Ya seedha WhatsApp: " + _WA_LINK,
            "",
            _UNSUB_LINE,
            "",
            "Shukriya,",
            from_name,
            "LeadGen AI — " + _SITE_URL,
        ]
        text = "\n".join(text_lines)
        html_body = (
            '<html><body style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;line-height:1.5;color:#222;max-width:600px;margin:0 auto;">'
            "<p>Namaste,</p>"
            f"<p>{e(name)} ji, yeh mera <b>aakhri reminder</b> hai — uske baad "
            "aapko pareshan nahi karunga.</p>"
            "<p>Ek chhota idea jo aapke kaam aa sakta hai:</p>"
            f'<p style="background:#f4f4ff;border-left:3px solid #4f46e5;'
            f'padding:10px 14px;border-radius:4px;">{e(idea)}</p>'
            f'<p><a href="{e(_AUDIT_URL)}" '
            'style="background:#4f46e5;color:#fff;padding:10px 18px;'
            'border-radius:6px;text-decoration:none;display:inline-block;">'
            "Free sample + audit dekhein</a></p>"
            f'<p>Ya seedha WhatsApp: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#888;font-size:12px;">{e(_UNSUB_LINE)}</p>'
            f"<p>Shukriya,<br>{e(from_name)}<br>"
            f'LeadGen AI — <a href="{e(_SITE_URL)}">{e(_SITE_URL)}</a></p>'
            "</body></html>"
        )
        return subject, text, html_body
    except Exception as ex:  # absolute guard — never raise
        logger.debug(f"[auto_outreach] followup subject/body build failed: {ex}")
        fb_name = str((prospect or {}).get("business_name") or "aapke business")
        from_name = _from_name()
        subject = f"{fb_name} ji — free Google audit (reminder)"
        text = (
            "Namaste,\n\n"
            f"{fb_name} ji, pichle email ka reminder — free Google profile audit "
            f"+ 3 sample posters ka offer abhi bhi khula hai. Yahan le lijiye: "
            f"{_AUDIT_URL}\n\n{_UNSUB_LINE}\n\nShukriya,\n{from_name}\n"
            f"LeadGen AI — {_SITE_URL}"
        )
        return subject, text, text


def _valid_email(addr: str) -> bool:
    a = (addr or "").strip()
    return "@" in a and "." in a.split("@")[-1] and len(a) >= 6


# Follow-up timing: din-gaps + max touches.
_FOLLOWUP_MAX = 2
_FOLLOWUP_GAP_DAYS = {0: 3, 1: 7}  # followup_count -> days since last email before next touch


def _days_since(iso_ts: str) -> float | None:
    """ISO timestamp (emailed_at) se ab tak kitne din. Parse-fail -> None."""
    s = (iso_ts or "").strip()
    if not s:
        return None
    try:
        # Tolerate trailing 'Z' (we write datetime.utcnow().isoformat()+"Z").
        if s.endswith("Z"):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        return (datetime.utcnow() - dt).total_seconds() / 86400.0
    except Exception:
        return None


async def run_email_outreach(limit: int | None = None) -> dict[str, Any]:
    """Ready prospects (jinka email hai aur abhi tak email nahi gaya) ko
    personalized cold email auto-bhejo. NEVER raises.

    Returns: {"sent": n, "skipped_no_email": x, "failed": y, "cap": c, ...}
    ya {"skipped": "<reason>"} jab flag/SMTP off ho.
    """
    result: dict[str, Any] = {"sent": 0, "skipped_no_email": 0, "failed": 0, "cap": 0}
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
        candidates: list[dict[str, Any]] = []
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


async def run_email_followups(limit: int | None = None) -> dict[str, Any]:
    """Pehle email ho chuke prospects ko multi-touch FOLLOW-UP bhejo. NEVER raises.

    Eligible prospect:
      - emailed ho chuka (emailed_at set), reply nahi aaya (status not in
        replied/client/dead), followup_count < 2
      - followup #1: emailed_at >3 din purana AND followup_count == 0
      - followup #2: emailed_at >7 din purana AND followup_count == 1
    Har send pe followup_count++ + emailed_at = ab (taaki agla touch 7 din baad).
    Same gate jaisa run_email_outreach (flag + API/SMTP), same daily cap.

    Returns: {"sent","skipped":..,"failed","cap","candidates","by_step":{1,2}}
    """
    result: dict[str, Any] = {
        "sent": 0,
        "failed": 0,
        "cap": 0,
        "candidates": 0,
        "by_step": {"1": 0, "2": 0},
    }
    try:
        from app.config import settings

        if not bool(getattr(settings, "auto_email_outreach", False)):
            return {"skipped": "AUTO_EMAIL_OUTREACH off"}

        _api = False
        try:
            from app.integrations.email_api import api_available

            _api = api_available()
        except Exception:
            _api = False
        if not _api and not (getattr(settings, "smtp_user", "") or "").strip():
            logger.warning("[auto_outreach] na API key na SMTP — followups skipped")
            return {"skipped": "email_unconfigured"}

        from app.platform import prospector

        _DONE = {"replied", "client", "dead"}
        candidates: list[tuple[dict[str, Any], int]] = []  # (prospect, step)
        for p in prospector.list_prospects(limit=500):
            try:
                if str(p.get("status") or "ready").lower() in _DONE:
                    continue
                if not p.get("emailed_at"):
                    continue  # initial outreach hi nahi gaya
                to_addr = str(p.get("email") or "").strip()
                if not _valid_email(to_addr):
                    continue
                try:
                    fc = int(p.get("followup_count") or 0)
                except Exception:
                    fc = 0
                if fc >= _FOLLOWUP_MAX:
                    continue
                days = _days_since(str(p.get("emailed_at") or ""))
                if days is None:
                    continue
                need = _FOLLOWUP_GAP_DAYS.get(fc)
                if need is None or days <= need:
                    continue
                candidates.append((p, fc + 1))  # next step = fc+1 (1 or 2)
            except Exception:
                continue

        result["candidates"] = len(candidates)

        try:
            daily_cap = int(getattr(settings, "outreach_daily_cap", 25))
        except Exception:
            daily_cap = 25
        daily_cap = max(0, daily_cap)
        cap = daily_cap if limit is None else max(0, min(int(limit), daily_cap or int(limit)))
        result["cap"] = cap

        if cap <= 0 or not candidates:
            return result

        batch = candidates[:cap]

        from app.integrations.email_sender import EmailSender

        sender = EmailSender()

        for idx, (p, step) in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            try:
                subject, text, html_body = _followup_subject_body(p, step)
                ok = False
                try:
                    ok = bool(await sender.send_email([to_addr], subject, text, html_body))
                except Exception as e:
                    logger.warning(f"[auto_outreach] followup to {to_addr} failed: {e}")
                    ok = False

                if ok:
                    try:
                        if pid:
                            prospector.set_prospect_fields(
                                pid,
                                {
                                    "followup_count": step,
                                    "emailed_at": datetime.utcnow().isoformat() + "Z",
                                },
                            )
                    except Exception:
                        pass
                    result["sent"] += 1
                    result["by_step"][str(step)] = result["by_step"].get(str(step), 0) + 1
                    _log_event("email_followup", f"#{step} {biz} ({to_addr})")
                else:
                    result["failed"] += 1
            except Exception as e:
                result["failed"] += 1
                logger.debug(f"[auto_outreach] followup {pid} error: {e}")

            if idx < len(batch) - 1:
                try:
                    await asyncio.sleep(random.uniform(_SLEEP_MIN_S, _SLEEP_MAX_S))
                except Exception:
                    pass

        _log_event(
            "email_followup_run",
            f"{result['sent']} follow-ups bheje (#1:{result['by_step'].get('1',0)} "
            f"#2:{result['by_step'].get('2',0)}), {result['failed']} fail, cap {cap}",
            status="ok" if result["failed"] == 0 else "warn",
            meta=dict(result),
        )
        logger.info(f"[auto_outreach] followups done: {result}")
        return result
    except Exception as e:  # absolute guard
        logger.warning(f"[auto_outreach] run_email_followups failed: {e}")
        result["error"] = str(e)
        return result


def outreach_stats() -> dict[str, Any]:
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


def _log_event(
    action: str, summary: str, status: str = "ok", meta: dict[str, Any] | None = None
) -> None:
    """Rohan ke naam se team event (best-effort)."""
    try:
        from app.platform.team import log_event

        log_event("rohan", action, summary, status=status, meta=meta or {})
    except Exception:
        pass


__all__ = [
    "run_email_outreach",
    "run_email_followups",
    "outreach_stats",
    "_email_subject_body",
    "_followup_subject_body",
]
