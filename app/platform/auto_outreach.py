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
import json
import os
import random
import re
from collections import Counter
from datetime import datetime, timezone
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

_SPINTAX_RE = re.compile(r"\{([^{}]+)\}")

# Niche-specific hook questions — peer-feel, 1 line per niche.
_NICHE_HOOKS: dict[str, str] = {
    "restaurant": "kya naye customers Zomato ke bahar seedha aapko dhundhte hain",
    "dental": "kya naye patients Google se directly aapke paas aa rahe hain",
    "real_estate": "kya aapki listings Google page-1 pe dikh rahi hain",
    "solar": "kya aapko qualified homeowners ki inquiries aa rahi hain",
    "coaching": "kya aapke institute ki online presence fee justify karti hai",
    "beauty": "kya repeat customers Instagram se aa rahe hain",
    "interior_design": "kya aapka portfolio online aisa dikh raha hai jo clients convince kare",
    "insurance": "kya local area se warm leads mil rahe hain",
    "loan": "kya prospects online aapko trustworthy samajhte hain",
    "gym": "kya Google profile naye members attract kar raha hai",
    "hospital": "kya patients online search karke aapko dhundhte hain",
    "school": "kya aapki institution ki online image parents ko impress karti hai",
    "ca_firm": "kya aapko referrals ke alawa bhi leads aa rahi hain",
    "travel": "kya aapke packages online easily milte hain jab log plan karte hain",
}


def _niche_hook(prospect: dict) -> str:
    """Niche-specific hook question — generic fallback."""
    niche = str((prospect or {}).get("niche") or (prospect or {}).get("category") or "").lower()
    for k, v in _NICHE_HOOKS.items():
        if k in niche:
            return v
    return "kya online se consistently naye customers aa rahe hain"


def _track_url(url: str, campaign: str = "cold_email") -> str:
    """UTM attribution via content_feedback.tracked_link (fail-open)."""
    try:
        from app.marketing.content_feedback import tracked_link

        return tracked_link(url, "email_outreach", campaign)
    except Exception:
        return url


def _pick_spintax(text: str) -> str:
    """Expand {a|b|c} spintax — one random choice per slot."""
    if not text or "{" not in text:
        return text

    def _one(m: re.Match) -> str:
        parts = m.group(1).split("|")
        return random.choice(parts).strip() if parts else ""

    out = text
    for _ in range(8):
        if not _SPINTAX_RE.search(out):
            break
        out = _SPINTAX_RE.sub(_one, out)
    return out


# W1.6: is.gd/tracked-link network call ab MODULE-IMPORT pe nahi (import slow/hang
# side-effect hataya) — lazy + cached: first email-build pe compute, phir memoized.
_AUDIT_TRACKED_CACHE: str | None = None
_SITE_TRACKED_CACHE: str | None = None


def _audit_url_tracked() -> str:
    global _AUDIT_TRACKED_CACHE
    if _AUDIT_TRACKED_CACHE is None:
        _AUDIT_TRACKED_CACHE = _track_url(_AUDIT_URL)
    return _AUDIT_TRACKED_CACHE


def _site_url_tracked() -> str:
    global _SITE_TRACKED_CACHE
    if _SITE_TRACKED_CACHE is None:
        _SITE_TRACKED_CACHE = _track_url(_SITE_URL, "site_footer")
    return _SITE_TRACKED_CACHE


def _flywheel_variants_on() -> bool:
    """OUTREACH_CAMPAIGN_VARIANTS=1 → use Kiran-approved champion/challenger copy."""
    try:
        import os as _os

        return (_os.getenv("OUTREACH_CAMPAIGN_VARIANTS") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    except Exception:
        return False


def _personalize_variant(text: str, prospect: dict[str, Any]) -> str:
    name = str((prospect or {}).get("business_name") or "").strip() or "aapke business"
    out = str(text or "")
    for tok in ("{name}", "[Name]", "{Name}"):
        out = out.replace(tok, name)
    return out


def _merge_flywheel_variant(
    prospect: dict[str, Any],
    subject: str,
    text: str,
    html_body: str,
    variant: dict[str, Any],
) -> tuple[str, str, str]:
    """Inject approved variant title/body into standard outreach template."""
    content = str(variant.get("content") or "").strip()
    if not content:
        return subject, text, html_body
    parts = content.split("\n\n", 1)
    title = _personalize_variant(parts[0].strip(), prospect)
    body = _personalize_variant(parts[1].strip() if len(parts) > 1 else "", prospect)
    if title:
        subject = _pick_spintax(title)
    if body:
        text = re.sub(
            r"(Namaste,\n\n)(.*?)(\n\nMain )",
            lambda m: m.group(1) + body + m.group(3),
            text,
            count=1,
            flags=re.DOTALL,
        )
        try:
            html_body = re.sub(
                r"(<p>Namaste,</p>\s*)(<p>.*?</p>)",
                r"\1<p>" + _html.escape(body) + "</p>",
                html_body,
                count=1,
                flags=re.DOTALL,
            )
        except Exception:
            pass
    return subject, text, html_body


def _from_name() -> str:
    try:
        from app.config import settings

        return (getattr(settings, "outreach_from_name", "") or "Sumit — LeadGen AI").strip()
    except Exception:
        return "Sumit — LeadGen AI"


def _audit_led_on() -> bool:
    """OUTREACH_AUDIT_LED gate (default OFF). Env OR settings attr — truthy check.

    Default-OFF => first-touch email unchanged (byte-for-byte). Read at call-time
    (not cached) so admin/env flips take effect without restart. NEVER raises.
    """
    try:
        import os as _os

        if (_os.getenv("OUTREACH_AUDIT_LED") or "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
    except Exception:
        pass
    try:
        from app.config import settings

        return bool(getattr(settings, "outreach_audit_led", False))
    except Exception:
        return False


def _audit_gap(prospect: dict[str, Any]) -> str:
    """Ek SHORT, specific, believable Hinglish "audit gap" line prospect ke
    in-memory fields se derive karo (NO network). Pehla jo apply ho wahi return,
    warna "". KABHI raise nahi karta (any issue -> "").

    Priority:
      1. website missing       -> online discoverability gap
      2. rating present & <4.0 -> rating-behind-competitors gap
      3. reviews very low (<5) -> trust/social-proof gap
      4. niche/category present -> niche-flavored generic gap
      5. else                  -> ""
    """
    try:
        p = prospect or {}

        # 1) Website missing? Prefer explicit has_website flag, else website string.
        has_site_flag = p.get("has_website")
        website = str(p.get("website") or "").strip()
        if has_site_flag is False or (has_site_flag is None and not website):
            return "website link missing — customers aapko online dhund nahi paa rahe"

        # 2) Low rating (present and < 4.0).
        try:
            rating = p.get("rating")
            rating = float(rating) if rating is not None and str(rating).strip() != "" else None
        except Exception:
            rating = None
        if rating is not None and 0 < rating < 4.0:
            return f"rating {rating}★ hai — top competitors 4.5★+ pe hain"

        # 3) Very low reviews (present and < 5).
        try:
            reviews = p.get("reviews_count")
            reviews = int(reviews) if reviews is not None and str(reviews).strip() != "" else None
        except Exception:
            reviews = None
        if reviews is not None and reviews < 5:
            return "Google reviews bahut kam — naye customers trust nahi karte"

        # 4) Niche/category-flavored generic gap.
        niche = str(p.get("niche") or p.get("category") or "").strip()
        if niche:
            label = niche.replace("_", " ")
            return f"{label} jaise businesses online consistent posts ke bina customers miss karte hain"

        return ""
    except Exception:
        return ""


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

        # --- audit-led hook (GATED OUTREACH_AUDIT_LED; OFF = zero change) ---
        # Flag ON + ek specific gap mile to subject + body ki PEHLI line me gap
        # weave karo (audit link / unsub / footer sab waise hi rehte hain).
        if _audit_led_on():
            try:
                gap = _audit_gap(prospect)
            except Exception:
                gap = ""
            if gap:
                subject = f"{name} — {gap}"
                opener = f"Maine {name} ka Google profile dekha — {gap}. " + opener

        hook = _niche_hook(prospect)

        # --- plain text body (peer 3-line format — shorter = better deliverability) ---
        text_lines = [
            "Namaste,",
            "",
            f"{opener} Ek sawaal — {hook}?",
            "",
            f"Maine {city or 'aapke area'} ke businesses ke liye kuch ideas nikali hain — "
            f"2 min me free audit: {_audit_url_tracked()}",
            "",
            f"Ya seedha WhatsApp karein: {_WA_LINK}",
            "",
            _UNSUB_LINE,
            "",
            f"— {from_name}, LeadGen AI",
        ]
        text = "\n".join(text_lines)

        # --- HTML body (clean, light) ---
        e = _html.escape
        html_body = (
            '<html><body style="font-family:Arial,Helvetica,sans-serif;'
            'font-size:15px;line-height:1.6;color:#222;max-width:560px;margin:0 auto;">'
            "<p>Namaste,</p>"
            f"<p>{e(opener)} Ek sawaal — {e(hook)}?</p>"
            f"<p>Maine {e(city or 'aapke area')} ke businesses ke liye kuch ideas nikali hain — "
            f'<a href="{e(_audit_url_tracked())}" style="color:#4f46e5;font-weight:600;">'
            "2 min free audit yahan lo</a>.</p>"
            f'<p>Ya seedha WhatsApp: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#999;font-size:12px;margin-top:24px;">{e(_UNSUB_LINE)}</p>'
            f'<p style="color:#555;font-size:13px;">— {e(from_name)}, '
            f'<a href="{e(_site_url_tracked())}" style="color:#4f46e5;">LeadGen AI</a></p>'
            "</body></html>"
        )
        return _pick_spintax(subject), text, html_body
    except Exception as e:  # absolute guard — never raise
        logger.debug(f"[auto_outreach] subject/body build failed: {e}")
        fb_name = str((prospect or {}).get("business_name") or "aapke business")
        from_name = _from_name()
        subject = f"{fb_name} — free Google profile audit"
        text = (
            "Namaste,\n\n"
            f"Main {from_name} se hoon. Hum chhote businesses ka online marketing "
            "sambhalte hain. Free Google profile audit + 3 sample posters bhej "
            f"sakta hoon. Yahan le lijiye: {_audit_url_tracked()}\n\n"
            f"{_UNSUB_LINE}\n\nShukriya,\n{from_name}\nLeadGen AI — {_site_url_tracked()}"
        )
        return _pick_spintax(subject), text, text


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

        niche_hook = _niche_hook(prospect)
        if int(step) <= 1:
            # ---- Follow-up #1: short Re: nudge + social proof ---- #
            subject = f"Re: {name} — free audit"
            sp_line = (
                "Is mahine humne isi area ke 3 businesses ka profile optimize kiya — "
                "unme se ek ko 40% zyada Google clicks mile pehle 2 hafte me."
            )
            text_lines = [
                "Namaste,",
                "",
                f"Pichle email ka follow-up — {name} ke liye {niche_hook}?",
                "",
                sp_line,
                "",
                f"2 min audit: {_audit_url_tracked()}  ·  WhatsApp: {_WA_LINK}",
                "",
                _UNSUB_LINE,
                f"— {from_name}, LeadGen AI",
            ]
            text = "\n".join(text_lines)
            html_body = (
                '<html><body style="font-family:Arial,Helvetica,sans-serif;'
                'font-size:15px;line-height:1.6;color:#222;max-width:560px;margin:0 auto;">'
                "<p>Namaste,</p>"
                f"<p>Pichle email ka follow-up — {e(name)} ke liye {e(niche_hook)}?</p>"
                f'<p style="background:#f0f4ff;border-left:3px solid #4f46e5;padding:12px 16px;'
                f'border-radius:0 6px 6px 0;">{e(sp_line)}</p>'
                f'<p><a href="{e(_audit_url_tracked())}" style="color:#4f46e5;font-weight:600;">'
                f"2 min audit yahan lo</a> &nbsp;·&nbsp; "
                f'<a href="{e(_WA_LINK)}" style="color:#4f46e5;">WhatsApp</a></p>'
                f'<p style="color:#999;font-size:12px;margin-top:24px;">{e(_UNSUB_LINE)}</p>'
                f'<p style="color:#555;font-size:13px;">— {e(from_name)}, '
                f'<a href="{e(_site_url_tracked())}" style="color:#4f46e5;">LeadGen AI</a></p>'
                "</body></html>"
            )
            return _pick_spintax(subject), text, html_body

        # ---- Follow-up #2: last reminder + concrete sample idea ---- #
        subject = f"{name} ji — aakhri reminder + ek poster idea"
        idea = (
            f'"{name} — aaj ka special!" wala ek festive poster, aapke naam aur '
            "phone ke saath — exactly aisa hum har hafte bana ke de sakte hain."
        )
        text_lines = [
            "Namaste,",
            "",
            f"{name} ji, yeh mera aakhri reminder hai — uske baad aapko pareshan nahi karunga.",
            "",
            "Ek chhota idea jo aapke kaam aa sakta hai:",
            idea,
            "",
            "Aisa free sample + Google profile audit dekhna ho to 2 minute lagenge: "
            + _audit_url_tracked(),
            "Ya seedha WhatsApp: " + _WA_LINK,
            "",
            _UNSUB_LINE,
            "",
            "Shukriya,",
            from_name,
            "LeadGen AI — " + _site_url_tracked(),
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
            f'<p><a href="{e(_audit_url_tracked())}" '
            'style="background:#4f46e5;color:#fff;padding:10px 18px;'
            'border-radius:6px;text-decoration:none;display:inline-block;">'
            "Free sample + audit dekhein</a></p>"
            f'<p>Ya seedha WhatsApp: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#888;font-size:12px;">{e(_UNSUB_LINE)}</p>'
            f"<p>Shukriya,<br>{e(from_name)}<br>"
            f'LeadGen AI — <a href="{e(_site_url_tracked())}">{e(_site_url_tracked())}</a></p>'
            "</body></html>"
        )
        return _pick_spintax(subject), text, html_body
    except Exception as ex:  # absolute guard — never raise
        logger.debug(f"[auto_outreach] followup subject/body build failed: {ex}")
        fb_name = str((prospect or {}).get("business_name") or "aapke business")
        from_name = _from_name()
        subject = f"{fb_name} ji — free Google audit (reminder)"
        text = (
            "Namaste,\n\n"
            f"{fb_name} ji, pichle email ka reminder — free Google profile audit "
            f"+ 3 sample posters ka offer abhi bhi khula hai. Yahan le lijiye: "
            f"{_audit_url_tracked()}\n\n{_UNSUB_LINE}\n\nShukriya,\n{from_name}\n"
            f"LeadGen AI — {_site_url_tracked()}"
        )
        return _pick_spintax(subject), text, text


def _valid_email(addr: str, check_mx: bool = True) -> bool:
    a = (addr or "").strip()
    if not ("@" in a and "." in a.split("@")[-1] and len(a) >= 6):
        return False
    try:
        from app.lead_scraper.email_verify import is_obvious_false_positive

        if is_obvious_false_positive(a):
            return False
    except Exception:
        pass
    # Deliverability gate (syntax + MX) — keeps bounce rate <2% so Gmail/Outlook don't
    # reject our bulk mail and the sending domain stays clean. Defensive: if
    # email-validator isn't installed, the basic check above is enough.
    # check_mx=False (dashboard/stats callers) skips the real DNS MX lookup — a
    # per-prospect network round-trip that made outreach_stats() take 151s across
    # ~2k prospects (admin_dashboard 0-clients incident, 2026-07-04: this call runs
    # on EVERY dashboard load, not just at send-time). Send-decision call sites keep
    # the default True.
    try:
        import os

        from app.lead_scraper.email_verify import verify

        if check_mx:
            check_mx = os.getenv("OUTREACH_VERIFY_MX", "1").strip().lower() not in {
                "0",
                "false",
                "no",
                "off",
            }
        r = verify(a, check_mx=check_mx)
        if "absent" not in r.get("reason", ""):  # verifier actually ran -> trust it
            return bool(r.get("ok"))
    except Exception:
        pass
    return True


def _suppressed_email_set() -> set[str]:
    """Bulk-load opt-out emails once per run/dashboard count. Never raises."""
    try:
        from app.platform import email_unsub

        return email_unsub.suppressed_emails()
    except Exception:
        return set()


def _is_suppressed_email(addr: str, suppressed: set[str] | None = None) -> bool:
    """True when a recipient has opted out. Optional set keeps loops O(N)."""
    e = (addr or "").strip().lower()
    if not e:
        return False
    try:
        if suppressed is not None:
            return e in suppressed
        from app.platform import email_unsub

        return bool(email_unsub.is_suppressed(e))
    except Exception:
        return False


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
    result: dict[str, Any] = {
        "sent": 0,
        "skipped_no_email": 0,
        "failed": 0,
        "cap": 0,
        "suppressed": 0,
        "duplicate_recipients": 0,
    }
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

        # Pick: status ready + not already emailed (emailable hone ka baad `_valid_email`
        # gate karta hai, jo `skipped_no_email` counter ko MEANINGFUL banata hai).
        # `_read_all()` direct use — `list_prospects` 500-newest hard-cap reachable
        # backlog ko chhupa deta tha (470 reachable prospects kabhi email nahi hote the).
        # pending_for_outreach() ka email-filter YAHAAN deliberately nahi lagate — wo
        # sirf caller-side "jo candidates mere paas aaye" semantics ke liye filter karta;
        # yahan hum chahte hain ki NO-EMAIL ready prospects skip count me bhi aayein
        # (product metric: "kitne ready leads ko email nahi mil saka?").
        candidates: list[dict[str, Any]] = []
        try:
            _ready_pool = list(prospector._read_all())
        except Exception:
            _ready_pool = []
        # Oldest first (FIFO backlog drain — purana pehle email jaye).
        _ready_pool.sort(key=lambda r: str(r.get("found_at") or ""))
        # Selection me MX lookup SKIP (default ON) — pehle har candidate (up to 500)
        # pe blocking DNS MX round-trip hota tha (~151s across ~2k prospects, code me
        # already documented) = email_outreach TimeLimitExceeded(600). Asli MX verify
        # ab sirf final chhote batch (<=cap<=25) pe hota hai (send loop me). Flag off
        # (OUTREACH_SELECT_SKIP_MX=0) = purana per-candidate MX behavior wapas.
        import os as _os_sel

        _skip_sel_mx = (
            _os_sel.getenv("OUTREACH_SELECT_SKIP_MX", "1") or ""
        ).strip().lower() not in {"0", "false", "no", "off"}
        _suppressed = _suppressed_email_set()
        _seen_recipients: set[str] = set()
        # Selection can scan hundreds of historical ready prospects. Per-row file
        # rewrites for malformed/blank email addresses made staff email_outreach hit
        # the 600s hard limit; bulk-flush keeps the same dead-marking semantics.
        _selection_invalid_marks: dict[str, dict[str, Any]] = {}
        for p in _ready_pool:
            if str(p.get("status") or "ready") != "ready":
                continue
            if not prospector.is_quality_approved(p):
                result["skipped_quality"] = result.get("skipped_quality", 0) + 1
                continue
            if p.get("emailed_at"):
                continue  # already emailed — never re-send (defensive)
            email = str(p.get("email") or "").strip()
            if not _valid_email(email, check_mx=not _skip_sel_mx):
                result["skipped_no_email"] += 1
                pid = p.get("id")
                if pid:
                    _selection_invalid_marks[str(pid)] = {
                        "status": "dead",
                        "dead_reason": "invalid_email",
                    }
                    if len(_selection_invalid_marks) >= 50:
                        try:
                            prospector.set_prospect_fields_bulk(_selection_invalid_marks)
                        except Exception:
                            pass
                        _selection_invalid_marks = {}
                continue
            if _is_suppressed_email(email, _suppressed):
                result["suppressed"] = result.get("suppressed", 0) + 1
                continue
            recipient = email.lower()
            if recipient in _seen_recipients:
                result["duplicate_recipients"] = result.get("duplicate_recipients", 0) + 1
                continue
            _seen_recipients.add(recipient)
            candidates.append(p)
            if len(candidates) >= 500:
                break  # safety cap — pending_for_outreach jaisa behavior

        if _selection_invalid_marks:
            try:
                prospector.set_prospect_fields_bulk(_selection_invalid_marks)
            except Exception:
                pass
            _selection_invalid_marks = {}

        try:
            daily_cap = int(getattr(settings, "outreach_daily_cap", 25))
        except Exception:
            daily_cap = 25
        daily_cap = max(0, daily_cap)
        try:  # warmup ramp + bounce auto-pause (GATED EMAIL_WARMUP; OFF = base cap unchanged)
            from app.platform import email_warmup

            daily_cap = email_warmup.effective_cap(daily_cap)
        except Exception:
            pass
        cap = daily_cap if limit is None else max(0, min(int(limit), daily_cap or int(limit)))
        result["cap"] = cap
        result["candidates"] = len(candidates)

        if cap <= 0 or not candidates:
            return result

        batch = candidates[:cap]

        from app.integrations.email_sender import EmailSender

        sender = EmailSender()

        # Bulk-mark (default ON): emailed_at markers jama karke har 10 pe + end me
        # ek saath likho — pehle har send poora prospects file rewrite karta tha
        # (O(N²) → OOM/SIGKILL). Flag off (OUTREACH_BULK_MARK=0) = purana per-send.
        import os as _os_mark

        _bulk_mark = (_os_mark.getenv("OUTREACH_BULK_MARK", "1") or "").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        _pending_marks: dict[str, dict[str, Any]] = {}

        for idx, p in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            # RFC 8058 / DPDP: one-click-unsubscribed = skip; baaki sab ko
            # List-Unsubscribe headers ke saath bhejo (Gmail/Yahoo deliverability).
            _unsub_hdrs: dict[str, str] = {}
            try:
                from app.platform import email_unsub as _eu

                if to_addr and _is_suppressed_email(to_addr, _suppressed):
                    result["suppressed"] = result.get("suppressed", 0) + 1
                    continue
                _unsub_hdrs = _eu.headers_for(to_addr)
            except Exception:
                pass
            # Selection me MX skip hua tha (perf) — ab is chhote batch pe asli MX
            # verify karo (bounded: <=cap<=25 DNS calls) taaki dead-domain pe send
            # na ho. Flag off tha to selection me hi MX ho chuka — yahan double na karo.
            if _skip_sel_mx and to_addr and not _valid_email(to_addr):
                result["skipped_no_email"] += 1
                if pid:
                    _pending_marks[pid] = {"status": "dead", "dead_reason": "invalid_mx"}
                    prospector.set_prospect_fields(
                        pid, {"status": "dead", "dead_reason": "invalid_mx"}
                    )
                continue
            try:
                subject, text, html_body = _email_subject_body(p)
                variant_id = ""
                try:
                    if _flywheel_variants_on():
                        from app.platform import campaign_variants

                        picked = await campaign_variants.pick_for_outreach(
                            "cold_email",
                            email=to_addr,
                            niche=str(p.get("niche") or "general"),
                        )
                        if picked:
                            subject, text, html_body = _merge_flywheel_variant(
                                p, subject, text, html_body, picked
                            )
                            variant_id = str(picked.get("id") or "")
                except Exception:
                    pass
                try:  # A/B spintax subject (GATED OUTREACH_AB=1; OFF = zero change)
                    import os as _os

                    if (_os.getenv("OUTREACH_AB") or "").strip().lower() in {
                        "1",
                        "true",
                        "yes",
                        "on",
                    }:
                        from app.marketing.outreach_variants import apply_ab

                        subject, text, html_body = apply_ab(p, subject, text, html_body)
                except Exception:
                    pass
                try:  # email open/click tracking (GATED EMAIL_TRACKING=1; OFF = zero change)
                    from app.marketing import email_tracking

                    if email_tracking.enabled():
                        html_body = email_tracking.instrument(
                            html_body, str(pid), campaign="cold_email"
                        )
                except Exception:
                    pass
                try:  # mailbox rotation (env OUTREACH_MAILBOXES JSON; absent = no-op)
                    from app.marketing.outreach_variants import rotate_sender

                    rotate_sender(sender)
                except Exception:
                    pass
                ok = False
                try:
                    ok = bool(
                        await sender.send_email(
                            [to_addr], subject, text, html_body, extra_headers=_unsub_hdrs
                        )
                    )
                except Exception as e:
                    _es = str(e)
                    logger.warning(f"[auto_outreach] send to {to_addr} failed: {e}")
                    ok = False
                    if "554" in _es or "Disabled by user" in _es:
                        result["error"] = "smtp_account_disabled"
                        break  # account blocked — stop the loop

                if ok:
                    # Mark so it's never re-emailed (keep status "ready" so the
                    # WhatsApp/human pipeline still sees it; emailed_at is the
                    # de-dup marker).
                    try:
                        if pid:
                            fields: dict[str, Any] = {
                                "emailed_at": datetime.utcnow().isoformat() + "Z",
                            }
                            if variant_id:
                                fields["campaign_variant_id"] = variant_id
                            if _bulk_mark:
                                _pending_marks[pid] = fields
                                if (
                                    len(_pending_marks) >= 10
                                ):  # periodic flush (crash pe ≤10 markers ka risk)
                                    prospector.set_prospect_fields_bulk(_pending_marks)
                                    _pending_marks = {}
                            else:
                                prospector.set_prospect_fields(pid, fields)
                    except Exception:
                        pass
                    if variant_id:
                        try:
                            from app.platform import campaign_variants

                            await campaign_variants.record_event(variant_id, impression=True)
                        except Exception:
                            pass
                    result["sent"] += 1
                    _log_event("email_sent", f"{biz} ({to_addr})")
                    try:
                        from app.platform import interaction_log

                        await interaction_log.record(
                            channel="email",
                            direction="out",
                            phone=str(p.get("phone") or ""),
                            email=to_addr,
                            body_summary=subject[:200],
                            outcome="sent",
                            campaign_variant_id=variant_id,
                        )
                    except Exception:
                        pass
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

        # Bache hue bulk markers flush (loop normal-end / break dono ke baad chalta).
        if _bulk_mark and _pending_marks:
            try:
                prospector.set_prospect_fields_bulk(_pending_marks)
            except Exception:
                pass
            _pending_marks = {}

        try:  # warmup stats (flag-independent — bounce-rate denominator)
            from app.platform import email_warmup

            email_warmup.record_sent(int(result.get("sent") or 0))
        except Exception:
            pass
        _log_event(
            "email_outreach_run",
            f"{result['sent']} emails bheje, {result['failed']} fail, cap {cap}",
            status="ok" if result["failed"] == 0 else "warn",
            meta=dict(result),
        )
        logger.info(f"[auto_outreach] run done: {result}")
        if int(result.get("sent") or 0) > 0 and _flywheel_variants_on():
            try:
                from app.platform import campaign_variants

                result["auto_promote"] = await campaign_variants.auto_promote_all()
            except Exception:
                pass
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
        "suppressed": 0,
        "duplicate_recipients": 0,
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
        # _read_all() instead of list_prospects: followup needs ALL emailed leads,
        # not just the newest 500 (list_prospects hard-caps + sorts newest-first,
        # so old emailed leads were never seen by this function).
        _suppressed = _suppressed_email_set()
        _seen_recipients: set[str] = set()
        for p in prospector._read_all():
            try:
                if str(p.get("status") or "ready").lower() in _DONE:
                    continue
                if not p.get("emailed_at"):
                    continue  # initial outreach hi nahi gaya
                to_addr = str(p.get("email") or "").strip()
                if not _valid_email(to_addr):
                    continue
                if _is_suppressed_email(to_addr, _suppressed):
                    result["suppressed"] = result.get("suppressed", 0) + 1
                    continue
                recipient = to_addr.lower()
                if recipient in _seen_recipients:
                    result["duplicate_recipients"] = result.get("duplicate_recipients", 0) + 1
                    continue
                _seen_recipients.add(recipient)
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
        try:  # warmup ramp + bounce auto-pause (GATED EMAIL_WARMUP; OFF = base cap unchanged)
            from app.platform import email_warmup

            daily_cap = email_warmup.effective_cap(daily_cap)
        except Exception:
            pass
        cap = daily_cap if limit is None else max(0, min(int(limit), daily_cap or int(limit)))
        result["cap"] = cap

        if cap <= 0 or not candidates:
            return result

        batch = candidates[:cap]

        from app.integrations.email_sender import EmailSender

        sender = EmailSender()

        # W1.4: bulk-mark (default ON) — followup markers jama karke har 10 pe + end me
        # ek saath likho; pehle har followup send poora prospects file rewrite karta tha
        # (O(N²) → OOM). Same pattern jaisa run_email_outreach. Flag OUTREACH_BULK_MARK=0 = per-send.
        import os as _os_mark

        _bulk_mark = (_os_mark.getenv("OUTREACH_BULK_MARK", "1") or "").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        _pending_marks: dict[str, dict[str, Any]] = {}

        for idx, (p, step) in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            # RFC 8058 / DPDP: unsubscribed = skip followups too; rest get headers.
            _unsub_hdrs: dict[str, str] = {}
            try:
                from app.platform import email_unsub as _eu

                if to_addr and _is_suppressed_email(to_addr, _suppressed):
                    result["suppressed"] = result.get("suppressed", 0) + 1
                    continue
                _unsub_hdrs = _eu.headers_for(to_addr)
            except Exception:
                pass
            try:
                subject, text, html_body = _followup_subject_body(p, step)
                try:  # mailbox rotation (env OUTREACH_MAILBOXES JSON; absent = no-op)
                    from app.marketing.outreach_variants import rotate_sender

                    rotate_sender(sender)
                except Exception:
                    pass
                ok = False
                try:
                    ok = bool(
                        await sender.send_email(
                            [to_addr], subject, text, html_body, extra_headers=_unsub_hdrs
                        )
                    )
                except Exception as e:
                    _es = str(e)
                    logger.warning(f"[auto_outreach] followup to {to_addr} failed: {e}")
                    ok = False
                    if "554" in _es or "Disabled by user" in _es:
                        result["error"] = "smtp_account_disabled"
                        break  # stop retrying all leads — account is blocked

                if ok:
                    try:
                        if pid:
                            _fields = {
                                "followup_count": step,
                                "emailed_at": datetime.utcnow().isoformat() + "Z",
                            }
                            if _bulk_mark:
                                _pending_marks[pid] = _fields
                                if (
                                    len(_pending_marks) >= 10
                                ):  # periodic flush (crash pe ≤10 markers ka risk)
                                    prospector.set_prospect_fields_bulk(_pending_marks)
                                    _pending_marks = {}
                            else:
                                prospector.set_prospect_fields(pid, _fields)
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

        # W1.4: bache hue bulk markers flush (loop normal-end / break dono ke baad).
        if _bulk_mark and _pending_marks:
            try:
                prospector.set_prospect_fields_bulk(_pending_marks)
            except Exception:
                pass
            _pending_marks = {}

        try:  # warmup stats (flag-independent)
            from app.platform import email_warmup

            email_warmup.record_sent(int(result.get("sent") or 0))
        except Exception:
            pass
        _log_event(
            "email_followup_run",
            f"{result['sent']} follow-ups bheje (#1:{result['by_step'].get('1', 0)} "
            f"#2:{result['by_step'].get('2', 0)}), {result['failed']} fail, cap {cap}",
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
    stats = {
        "total": 0,
        "with_email": 0,
        "emailed": 0,
        "pending": 0,
        "pending_total": 0,
        "pending_sendable": 0,
        "duplicate_pending_recipients": 0,
        "suppressed": 0,
    }
    try:
        from app.platform import prospector

        # ALL prospects (not list_prospects' 500-newest cap) — warna pending/total galat
        # dikhte (470 reachable backlog "0 pending" lagta tha).
        try:
            rows = prospector._read_all()
        except Exception:
            rows = prospector.list_prospects(limit=500)
        stats["total"] = len(rows)
        suppressed = _suppressed_email_set()
        seen_pending: set[str] = set()
        for r in rows:
            # check_mx=False — this is a dashboard COUNT, not a send decision; the
            # real MX gate still runs at actual send-time (line ~568 above).
            email = str(r.get("email") or "")
            has_email = _valid_email(email, check_mx=False)
            is_suppressed = has_email and _is_suppressed_email(email, suppressed)
            if has_email:
                stats["with_email"] += 1
            if is_suppressed:
                stats["suppressed"] += 1
            if r.get("emailed_at"):
                stats["emailed"] += 1
            elif has_email and (r.get("status") or "ready") == "ready":
                stats["pending_total"] += 1
                if not is_suppressed:
                    recipient = email.strip().lower()
                    if recipient in seen_pending:
                        stats["duplicate_pending_recipients"] += 1
                    else:
                        seen_pending.add(recipient)
                        stats["pending_sendable"] += 1
        stats["pending"] = stats["pending_sendable"]
    except Exception as e:
        logger.debug(f"[auto_outreach] outreach_stats failed: {e}")
    return stats


# ---------------------------------------------------------------------------
# MULTI-CHANNEL ORCHESTRATION — email → WhatsApp → calling pipeline
# ---------------------------------------------------------------------------
# Enterprise-grade: email-openers ko WhatsApp follow-up link bhejta hai,
# high-intent prospects ko calling queue me flag karta hai.
# NEVER raises — har step ka apna try/except.
# ---------------------------------------------------------------------------

import urllib.parse as _urlparse


def _wa_followup_link(phone10: str, biz_name: str, msg: str) -> str:
    """1-click WhatsApp follow-up link (NOT auto-send — ban-safe)."""
    return f"https://wa.me/91{phone10}?text={_urlparse.quote(msg)}"


def multi_channel_followup(limit: int = 25) -> dict[str, Any]:
    """Email-emailed prospects ke liye WhatsApp follow-up links generate karo.

    Gated: SALES_AUTOPILOT_ENABLED + WHATSAPP_AUTO_SEND (auto-send) ya
    human-click WA links (always safe).  KABHI raise nahi karta.

    Returns: {"processed": n, "wa_links_generated": x, "calling_flagged": y}
    """
    result: dict[str, Any] = {
        "processed": 0,
        "wa_links_generated": 0,
        "calling_flagged": 0,
        "skipped": 0,
    }
    try:
        from app.platform import prospector

        rows = prospector._read_all()
        # Emailed prospects jinke paas phone hai — WhatsApp eligible
        emailed_with_phone = [
            r
            for r in rows
            if r.get("emailed_at")
            and r.get("phone")
            and len("".join(c for c in str(r["phone"]) if c.isdigit())) >= 10
            and (r.get("status") or "ready") in ("ready", "sent")
            and not r.get("wa_followup_sent")
            and not r.get("hq_done")
            and not r.get("hq_parked")
        ]
        emailed_with_phone.sort(key=lambda r: str(r.get("found_at") or ""))
        batch = emailed_with_phone[:limit]

        for p in batch:
            try:
                phone10 = "".join(c for c in str(p["phone"]) if c.isdigit())[-10:]
                if len(phone10) < 10:
                    continue
                biz = str(p.get("business_name") or "Business").strip()
                niche = str(p.get("niche") or "business").replace("_", " ")

                # WhatsApp follow-up message — polite, value-forward
                wa_msg = (
                    f"Namaste {biz} ji 🙏 Maine aapko email kiya tha {niche} ke liye "
                    f"free Google audit ke baare me. Agar dekhna ho to 2 min lagenge: "
                    f"leadsgenai.in/audit — ya yahan baat karte hain!"
                )
                wa_link = _wa_followup_link(phone10, biz, wa_msg)

                # Mark so we don't re-generate
                prospector.set_prospect_fields(
                    str(p.get("id")),
                    {
                        "wa_followup_generated": True,
                        "wa_followup_link": wa_link,
                        "updated_at": datetime.utcnow().isoformat() + "Z",
                    },
                )
                result["wa_links_generated"] += 1

                # High-intent signal: niche is local SMB + has phone → calling candidate
                if str(p.get("niche") or "") in {
                    "solar_residential",
                    "real_estate",
                    "coaching",
                    "interior_designers",
                    "dental",
                    "beauty",
                }:
                    prospector.set_prospect_fields(
                        str(p.get("id")),
                        {
                            "calling_flagged": True,
                            "updated_at": datetime.utcnow().isoformat() + "Z",
                        },
                    )
                    result["calling_flagged"] += 1

                result["processed"] += 1
            except Exception as e:
                logger.debug(f"[auto_outreach] multi_channel_followup item failed: {e}")
                result["skipped"] += 1

        try:
            from app.platform.team import log_event

            log_event(
                "rohan",
                "multi_channel_followup",
                (
                    f"{result['processed']} prospects processed, "
                    f"{result['wa_links_generated']} WA links, "
                    f"{result['calling_flagged']} calling-flagged"
                ),
                status="ok",
                meta=result,
            )
        except Exception:
            pass

        logger.info(f"[auto_outreach] multi_channel_followup done: {result}")
        return result
    except Exception as e:
        logger.warning(f"[auto_outreach] multi_channel_followup failed: {e}")
        result["error"] = str(e)
        return result


def hot_queue_candidates(limit: int = 20) -> list[dict[str, Any]]:
    """Prospects jo Hot Queue ke liye ready hain — replied ya high-intent.

    Hot Queue `/app/inbox` ke liye data source. KABHI raise nahi karta.
    """
    try:
        from app.platform import prospector

        rows = prospector._read_all()
        candidates = []
        for r in rows:
            status = (r.get("status") or "ready").lower()
            # Already in pipeline (replied, client, dead) = skip
            if status in ("client", "dead"):
                continue
            # High-intent signals
            is_reply = status == "replied"
            is_calling_flagged = bool(r.get("calling_flagged"))
            is_wa_engaged = bool(r.get("wa_followup_sent"))
            has_high_score = False
            try:
                score = int(r.get("lead_score") or 0)
                has_high_score = score >= 70
            except Exception:
                pass

            if is_reply or is_calling_flagged or is_wa_engaged or has_high_score:
                candidates.append(
                    {
                        "id": r.get("id"),
                        "business_name": r.get("business_name"),
                        "phone": r.get("phone"),
                        "email": r.get("email"),
                        "niche": r.get("niche"),
                        "city": r.get("city"),
                        "status": status,
                        "lead_score": r.get("lead_score"),
                        "wa_followup_link": r.get("wa_followup_link") or "",
                        "reason": (
                            "replied"
                            if is_reply
                            else (
                                "calling_flagged"
                                if is_calling_flagged
                                else "wa_engaged"
                                if is_wa_engaged
                                else "high_score"
                            )
                        ),
                    }
                )
        candidates.sort(key=lambda c: float(c.get("lead_score") or 0), reverse=True)
        return candidates[:limit]
    except Exception as e:
        logger.debug(f"[auto_outreach] hot_queue_candidates failed: {e}")
        return []


def mark_hot_queue_candidate(prospect_id: str, *, done: bool = False, parked: bool = False) -> bool:
    """Hot Queue Done/Park for calling_flagged synthetic cards. Never raises."""
    pid = str(prospect_id or "").strip()
    if not pid:
        return False
    try:
        from app.platform import prospector

        fields: dict[str, Any] = {"updated_at": datetime.utcnow().isoformat() + "Z"}
        if done:
            fields["hq_done"] = True
        if parked:
            fields["hq_parked"] = True
        prospector.set_prospect_fields(pid, fields)
        return True
    except Exception as e:
        logger.debug(f"[auto_outreach] mark_hot_queue_candidate failed: {e}")
        return False


def _rel_time(iso: str) -> str:
    """ISO timestamp -> Hinglish relative ('abhi' / 'X min pehle' / 'X din pehle')."""
    try:
        s = str(iso or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        secs = (datetime.now(timezone.utc) - dt).total_seconds()
        if secs < 90:
            return "abhi"
        if secs < 3600:
            return f"{int(secs // 60)} min pehle"
        if secs < 86400:
            return f"{int(secs // 3600)} ghante pehle"
        return f"{int(secs // 86400)} din pehle"
    except Exception:
        return ""


_HIGH_INTENT_LOCAL_NICHES = {
    "ayurveda_wellness",
    "automobile_service",
    "beauty_makeover",
    "dental_implants",
    "furniture_decor",
    "hair_transplant",
    "interior_designers",
    "kirana_supermarket",
    "makeup_artist",
    "modular_kitchen",
    "photography_studio",
    "skin_dermatology",
    "solar_residential",
}
_MANUAL_REVIEW_NICHES = {
    "b2b_suppliers",
    "ecommerce_d2c",
    "finance_advisory",
    "home_loans",
    "hospital_appointments",
    "insurance",
    "ivf_clinics",
    "recruitment",
    "travel_agency",
    "travel_packages",
    "upskilling",
}
_LOW_FIT_NICHES = {"ai_marketing", "digital_marketing"}
_LOW_FIT_TERMS = (
    "ad agency",
    "advertising",
    "branding agency",
    "digital marketing",
    "lead generation",
    "marketing agency",
    "performance marketing",
    "seo",
    "social media agency",
    "web design",
    "website design",
)
_CHAIN_REVIEW_TERMS = (
    "group",
    "hospital",
    "limited",
    "ltd",
    "private limited",
    "pvt ltd",
    "university",
)


def _pending_review_bucket(prospect: dict[str, Any]) -> dict[str, str]:
    """Human-review bucket for pending recipients. Informational only; never blocks."""
    p = prospect or {}
    niche = str(p.get("niche") or p.get("category") or "").strip().lower()
    text = " ".join(
        str(p.get(k) or "")
        for k in ("business_name", "name", "category", "niche", "website", "email")
    ).lower()
    if niche in _LOW_FIT_NICHES or any(t in text for t in _LOW_FIT_TERMS):
        return {
            "key": "review_low_fit_vendor",
            "label": "Review: vendor/competitor",
            "reason": "marketing/agency/software-like prospect",
        }
    if niche in _MANUAL_REVIEW_NICHES or any(t in text for t in _CHAIN_REVIEW_TERMS):
        return {
            "key": "review_enterprise_or_edge",
            "label": "Review: enterprise/edge",
            "reason": "chain, enterprise, finance, travel, B2B, or regulated niche",
        }
    if niche in _HIGH_INTENT_LOCAL_NICHES:
        return {
            "key": "priority_local_smb",
            "label": "Priority: local SMB",
            "reason": "local service niche fits Product 1 GTM",
        }
    return {
        "key": "review_unknown_fit",
        "label": "Review: unknown fit",
        "reason": "niche/source not confidently classified",
    }


def pending_review_candidates(bucket: str = "", limit: int = 100) -> dict[str, Any]:
    """Deduped pending recipients for admin review/export. Informational only."""
    wanted = str(bucket or "").strip()
    try:
        limit = max(1, min(int(limit or 100), 500))
    except Exception:
        limit = 100
    out: dict[str, Any] = {"bucket": wanted, "count": 0, "candidates": []}
    try:
        from app.platform import prospector

        try:
            rows = list(prospector._read_all())
        except Exception:
            rows = list(prospector.list_prospects(limit=1000))
        rows.sort(key=lambda r: str(r.get("found_at") or ""))
        suppressed = _suppressed_email_set()
        seen: set[str] = set()
        candidates: list[dict[str, str]] = []
        for r in rows:
            email = str(r.get("email") or "").strip().lower()
            if str(r.get("status") or "ready") != "ready" or r.get("emailed_at"):
                continue
            if not _valid_email(email, check_mx=False) or _is_suppressed_email(email, suppressed):
                continue
            if email in seen:
                continue
            seen.add(email)
            b = _pending_review_bucket(r)
            if wanted and b["key"] != wanted:
                continue
            candidates.append(
                {
                    "id": str(r.get("id") or "")[:80],
                    "business": str(r.get("business_name") or r.get("name") or "")[:120],
                    "email": email[:120],
                    "phone": str(r.get("phone") or "")[:40],
                    "city": str(r.get("city") or "")[:60],
                    "niche": str(r.get("niche") or r.get("category") or "")[:80],
                    "website": str(r.get("website") or "")[:180],
                    "bucket": b["key"],
                    "label": b["label"],
                    "reason": b["reason"],
                }
            )
            if len(candidates) >= limit:
                break
        out["count"] = len(candidates)
        out["candidates"] = candidates
    except Exception as e:
        logger.debug(f"[auto_outreach] pending_review_candidates failed: {e}")
        out["error"] = str(e)
    return out


# --- Outreach review decisions (ADR-061) - operator bookkeeping after ADR-059 export
# Append-only jsonl store of admin "what did I decide for this recipient" decisions
# (reviewed_sent / reviewed_skip / reviewed_schedule / reviewed_suppress / reviewed_unsuppress).
# Informational + auditable: does NOT auto-send, does NOT mutate warmup, does NOT touch
# email_unsub.suppressed_emails() (proper complaint suppression lives there).
_REVIEW_DECISION_FILE = os.path.join("data", "outreach_review_decisions.jsonl")
_REVIEW_DECISION_KINDS = {
    "reviewed_sent",
    "reviewed_skip",
    "reviewed_schedule",
    "reviewed_suppress",
    "reviewed_unsuppress",
}


def _normalise_decision_kind(kind: str) -> str:
    k = str(kind or "").strip().lower()
    if k in _REVIEW_DECISION_KINDS:
        return k
    return ""


def record_review_decision(
    email: str,
    decision: str,
    note: str = "",
    bucket: str = "",
    reviewer: str = "",
) -> dict[str, Any]:
    """Operator bookmark: "is recipient ke liye maine ye decide kiya." Append-only
    jsonl under a file_lock (multi-process safe). Never-raise. Returns the saved
    record on success, safe-empty on failure."""
    out: dict[str, Any] = {"ok": False, "email": str(email or "").strip().lower()}
    try:
        addr = str(email or "").strip().lower()
        if not addr or "@" not in addr:
            out["error"] = "missing_email"
            return out
        kind = _normalise_decision_kind(decision)
        if not kind:
            out["error"] = "invalid_decision"
            return out
        try:
            from app.utils.file_lock import file_lock
        except Exception:  # pragma: no cover - import fail shouldn't crash caller
            file_lock = None  # type: ignore[assignment]
        rec = {
            "email": addr[:120],
            "decision": kind,
            "note": str(note or "")[:300],
            "bucket": str(bucket or "")[:40],
            "reviewer": str(reviewer or "")[:60],
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        os.makedirs(os.path.dirname(_REVIEW_DECISION_FILE) or ".", exist_ok=True)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        if file_lock is not None:
            try:
                with file_lock(_REVIEW_DECISION_FILE, timeout_s=2.0):
                    with open(_REVIEW_DECISION_FILE, "a", encoding="utf-8") as f:
                        f.write(line)
            except Exception:
                # fall through to unlocked append (still best-effort)
                with open(_REVIEW_DECISION_FILE, "a", encoding="utf-8") as f:
                    f.write(line)
        else:
            with open(_REVIEW_DECISION_FILE, "a", encoding="utf-8") as f:
                f.write(line)
        out["ok"] = True
        out["record"] = rec
    except Exception as e:
        logger.debug(f"[auto_outreach] record_review_decision failed: {e}")
        out["error"] = str(e)
    return out


def _read_review_decisions(bucket: str = "", limit: int = 500) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.exists(_REVIEW_DECISION_FILE):
            return rows
        wanted = str(bucket or "").strip()
        try:
            limit = max(1, min(int(limit or 200), 5000))
        except Exception:
            limit = 200
        with open(_REVIEW_DECISION_FILE, encoding="utf-8") as f:
            for line in f:
                line = (line or "").strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                if wanted and str(rec.get("bucket") or "") != wanted:
                    continue
                rows.append(rec)
    except Exception as e:
        logger.debug(f"[auto_outreach] read_review_decisions failed: {e}")
    return rows[-limit:]


def list_review_decisions(bucket: str = "", limit: int = 200) -> dict[str, Any]:
    """Return latest decision per recipient (case-insensitive email key)."""
    out: dict[str, Any] = {"bucket": str(bucket or ""), "count": 0, "decisions": []}
    try:
        rows = _read_review_decisions(bucket=bucket, limit=max(limit * 4, 500))
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            em = str(r.get("email") or "").strip().lower()
            if not em:
                continue
            prev = latest.get(em)
            if (prev is None) or str(r.get("at") or "") >= str(prev.get("at") or ""):
                latest[em] = r
        try:
            limit = max(1, min(int(limit or 200), 1000))
        except Exception:
            limit = 200
        items = list(latest.values())
        items.sort(key=lambda r: str(r.get("at") or ""), reverse=True)
        items = items[:limit]
        out["count"] = len(items)
        out["decisions"] = items
    except Exception as e:
        logger.debug(f"[auto_outreach] list_review_decisions failed: {e}")
        out["error"] = str(e)
    return out


def review_decision_counts() -> dict[str, int]:
    """Counts by decision-kind across all buckets (dashboard tile)."""
    counts: dict[str, int] = dict.fromkeys(sorted(_REVIEW_DECISION_KINDS), 0)
    try:
        rows = _read_review_decisions(bucket="", limit=5000)
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            em = str(r.get("email") or "").strip().lower()
            if not em:
                continue
            prev = latest.get(em)
            if (prev is None) or str(r.get("at") or "") >= str(prev.get("at") or ""):
                latest[em] = r
        for r in latest.values():
            k = str(r.get("decision") or "").strip().lower()
            if k in counts:
                counts[k] += 1
        counts["unique_recipients"] = len(latest)
    except Exception as e:
        logger.debug(f"[auto_outreach] review_decision_counts failed: {e}")
    return counts


def outreach_activity(limit: int = 20) -> dict[str, Any]:
    """Admin-friendly outreach activity — kisko bheja, kitne, kya reply aaya.
    Plain-Hinglish counts + recent sent recipients + recent replies. KABHI raise nahi
    (failure pe safe-empty)."""
    from datetime import date

    out: dict[str, Any] = {
        "summary": {
            "total": 0,
            "with_email": 0,
            "emailed": 0,
            "pending": 0,
            "pending_total": 0,
            "pending_sendable": 0,
            "duplicate_pending_recipients": 0,
            "suppressed": 0,
            "replied": 0,
            "sent_today": 0,
            "opens": 0,
            "clicks": 0,
            "bounce_rate_7d_pct": 0.0,
            "bounced_7d": 0,
            "complaint_rate_7d_pct": 0.0,
            "complaints_7d": 0,
            "warmup_paused": False,
            "warmup_attention": False,
            "paused_reason": "",
        },
        "headline": "",
        "pending_review": {"buckets": [], "samples": []},
        "recent_sent": [],
        "recent_replies": [],
        "review_decisions": {},
    }
    today = ""
    try:
        today = date.today().isoformat()
    except Exception:
        pass
    # 1) Prospect pool -> counts + recent sent recipients
    try:
        from app.platform import prospector

        try:
            rows = prospector._read_all()
        except Exception:
            rows = prospector.list_prospects(limit=1000)
        emailed_rows = []
        suppressed = _suppressed_email_set()
        seen_pending: set[str] = set()
        pending_buckets: Counter[str] = Counter()
        pending_bucket_meta: dict[str, dict[str, str]] = {}
        pending_samples: list[dict[str, str]] = []
        for r in rows:
            # check_mx=False — dashboard COUNT, not a send decision (see outreach_stats).
            email = str(r.get("email") or "")
            has_email = _valid_email(email, check_mx=False)
            is_suppressed = has_email and _is_suppressed_email(email, suppressed)
            if has_email:
                out["summary"]["with_email"] += 1
            if is_suppressed:
                out["summary"]["suppressed"] += 1
            ea = str(r.get("emailed_at") or "")
            if ea:
                out["summary"]["emailed"] += 1
                emailed_rows.append(r)
                if today and ea[:10] == today:
                    out["summary"]["sent_today"] += 1
            elif has_email and (r.get("status") or "ready") == "ready":
                out["summary"]["pending_total"] += 1
                if not is_suppressed:
                    recipient = email.strip().lower()
                    if recipient in seen_pending:
                        out["summary"]["duplicate_pending_recipients"] += 1
                    else:
                        seen_pending.add(recipient)
                        out["summary"]["pending_sendable"] += 1
                        bucket = _pending_review_bucket(r)
                        key = bucket["key"]
                        pending_buckets[key] += 1
                        pending_bucket_meta[key] = bucket
                        if len(pending_samples) < max(5, min(limit, 20)):
                            pending_samples.append(
                                {
                                    "business": str(r.get("business_name") or r.get("name") or "—")[
                                        :80
                                    ],
                                    "email": recipient[:90],
                                    "city": str(r.get("city") or "")[:40],
                                    "niche": str(r.get("niche") or r.get("category") or "")[:50],
                                    "bucket": key,
                                    "label": bucket["label"],
                                    "reason": bucket["reason"],
                                }
                            )
            if (r.get("status") or "") == "replied":
                out["summary"]["replied"] += 1
        out["summary"]["total"] = len(rows)
        out["pending_review"] = {
            "buckets": [
                {
                    "key": key,
                    "label": pending_bucket_meta[key]["label"],
                    "count": count,
                    "reason": pending_bucket_meta[key]["reason"],
                }
                for key, count in pending_buckets.most_common()
            ],
            "samples": pending_samples,
        }
        emailed_rows.sort(key=lambda x: str(x.get("emailed_at") or ""), reverse=True)
        for r in emailed_rows[:limit]:
            out["recent_sent"].append(
                {
                    "business": str(r.get("business_name") or r.get("name") or "—")[:60],
                    "email": str(r.get("email") or "")[:80],
                    "city": str(r.get("city") or "")[:40],
                    "when": _rel_time(str(r.get("emailed_at") or "")),
                    "followups": int(r.get("followup_count") or 0),
                    "status": str(r.get("status") or "sent"),
                }
            )
    except Exception as e:
        logger.debug(f"[auto_outreach] outreach_activity prospects failed: {e}")
    # 2) Recent replies (email + whatsapp drafts)
    try:
        from app.platform import reply_agent

        drafts = reply_agent.list_drafts(limit=limit) or []
        for d in reversed(drafts[-limit:]):
            txt = str(d.get("text") or d.get("body_snippet") or d.get("subject") or "")
            out["recent_replies"].append(
                {
                    "from": str(d.get("from") or "—")[:80],
                    "channel": str(d.get("channel") or "email"),
                    "intent": str(d.get("intent") or "reply"),
                    "snippet": txt[:140],
                    "draft_ready": bool(str(d.get("draft") or "").strip()),
                    "when": _rel_time(str(d.get("at") or "")),
                }
            )
    except Exception as e:
        logger.debug(f"[auto_outreach] outreach_activity replies failed: {e}")
    # 3) Open/click tracking (only meaningful when EMAIL_TRACKING on)
    try:
        from app.marketing import email_tracking

        ts = email_tracking.stats() or {}
        out["summary"]["opens"] = int(ts.get("opens") or 0)
        out["summary"]["clicks"] = int(ts.get("clicks") or 0)
    except Exception:
        pass
    # 3b) Bounce-rate visibility (2026-07-04: reply_agent ab bounce/NDR mail auto
    # detect + record_bounce() karta hai — is se pehle yeh counter hamesha ~0 read
    # hota tha kyunki koi automatic feed nahi tha). Deliverability ka REAL signal
    # yahan dikhta hai — 0-reply funnel diagnose karne ke liye zaroori.
    try:
        from app.platform import email_warmup

        rate, sent_7d, bounced_7d = email_warmup.bounce_rate_7d()
        out["summary"]["bounce_rate_7d_pct"] = rate
        out["summary"]["bounced_7d"] = bounced_7d
        out["summary"]["sent_7d"] = sent_7d
        st = email_warmup.status()
        out["summary"]["complaint_rate_7d_pct"] = st.get("complaint_rate_7d_pct", 0.0)
        out["summary"]["complaints_7d"] = st.get("complaints_7d", 0)
        paused_reason = str(st.get("paused_reason") or "")
        out["summary"]["warmup_paused"] = bool(st.get("paused"))
        out["summary"]["warmup_attention"] = bool(st.get("paused") or paused_reason)
        out["summary"]["paused_reason"] = paused_reason
    except Exception:
        pass
    # 4) Plain-Hinglish headline
    s = out["summary"]
    s["pending"] = s.get("pending_sendable", s.get("pending", 0))
    # 5) Operator review decisions (ADR-061) - best-effort, fail-OPEN
    try:
        out["review_decisions"] = review_decision_counts()
    except Exception as e:
        logger.debug(f"[auto_outreach] outreach_activity review_decisions failed: {e}")
        out["review_decisions"] = {"unique_recipients": 0}
    if s.get("warmup_attention"):
        state = "PAUSED" if s.get("warmup_paused") else "ATTENTION"
        out["headline"] = (
            f"Email warmup {state}: {s.get('paused_reason') or 'deliverability gate red'}; "
            f"complaint rate (7d) {s.get('complaint_rate_7d_pct', 0.0)}% "
            f"({s.get('complaints_7d', 0)} complaints), "
            f"{s.get('pending', 0)} sendable pending, {s.get('suppressed', 0)} suppressed"
        )
    else:
        out["headline"] = (
            f"Email: aaj {s['sent_today']} bheje, ab tak {s['emailed']} total, "
            f"{len(out['recent_replies'])} reply aaye, {s['pending']} sendable pending, "
            f"bounce rate (7d) {s['bounce_rate_7d_pct']}%, "
            f"complaint rate (7d) {s.get('complaint_rate_7d_pct', 0.0)}%"
        )
    return out


def last_run_summaries(limit: int = 5) -> list[dict[str, Any]]:
    """Last email-outreach / follow-up run outcomes (admin UI ke liye).

    run_email_outreach/run_email_followups already record har run ka result
    (sent/failed/cap/... meta) via _log_event -> team.log_event (AgentEvent).
    Isse bas newest-first filter karke return karo — koi naya persistence nahi.
    Never raises (failure pe safe-empty)."""
    out: list[dict[str, Any]] = []
    try:
        from app.platform import team

        rows = team.recent_events(limit=400)
        wanted = {"email_outreach_run", "email_followup_run"}
        try:
            limit = max(1, min(int(limit or 5), 50))
        except Exception:
            limit = 5
        for ev in rows:
            action = str(ev.get("action") or "")
            if action not in wanted:
                continue
            meta = ev.get("meta") or {}
            if not isinstance(meta, dict):
                meta = {}
            out.append(
                {
                    "at": ev.get("at"),
                    "kind": action,
                    "status": str(ev.get("status") or "ok"),
                    "summary": str(ev.get("detail") or ""),
                    "meta": meta,
                }
            )
            if len(out) >= limit:
                break
    except Exception as e:
        logger.debug(f"[auto_outreach] last_run_summaries failed: {e}")
    return out


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
    "outreach_activity",
    "pending_review_candidates",
    "record_review_decision",
    "list_review_decisions",
    "review_decision_counts",
    "last_run_summaries",
    "_email_subject_body",
    "_followup_subject_body",
]
