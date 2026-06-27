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
import re
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


_AUDIT_URL_TRACKED = _track_url(_AUDIT_URL)
_SITE_URL_TRACKED = _track_url(_SITE_URL, "site_footer")


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
            f"2 min me free audit: {_AUDIT_URL_TRACKED}",
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
            f'<a href="{e(_AUDIT_URL_TRACKED)}" style="color:#4f46e5;font-weight:600;">'
            "2 min free audit yahan lo</a>.</p>"
            f'<p>Ya seedha WhatsApp: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#999;font-size:12px;margin-top:24px;">{e(_UNSUB_LINE)}</p>'
            f'<p style="color:#555;font-size:13px;">— {e(from_name)}, '
            f'<a href="{e(_SITE_URL_TRACKED)}" style="color:#4f46e5;">LeadGen AI</a></p>'
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
            f"sakta hoon. Yahan le lijiye: {_AUDIT_URL_TRACKED}\n\n"
            f"{_UNSUB_LINE}\n\nShukriya,\n{from_name}\nLeadGen AI — {_SITE_URL_TRACKED}"
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
                f"2 min audit: {_AUDIT_URL_TRACKED}  ·  WhatsApp: {_WA_LINK}",
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
                f'<p><a href="{e(_AUDIT_URL_TRACKED)}" style="color:#4f46e5;font-weight:600;">'
                f"2 min audit yahan lo</a> &nbsp;·&nbsp; "
                f'<a href="{e(_WA_LINK)}" style="color:#4f46e5;">WhatsApp</a></p>'
                f'<p style="color:#999;font-size:12px;margin-top:24px;">{e(_UNSUB_LINE)}</p>'
                f'<p style="color:#555;font-size:13px;">— {e(from_name)}, '
                f'<a href="{e(_SITE_URL_TRACKED)}" style="color:#4f46e5;">LeadGen AI</a></p>'
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
            f"{name} ji, yeh mera aakhri reminder hai — uske baad aapko pareshan " "nahi karunga.",
            "",
            "Ek chhota idea jo aapke kaam aa sakta hai:",
            idea,
            "",
            "Aisa free sample + Google profile audit dekhna ho to 2 minute lagenge: " + _AUDIT_URL_TRACKED,
            "Ya seedha WhatsApp: " + _WA_LINK,
            "",
            _UNSUB_LINE,
            "",
            "Shukriya,",
            from_name,
            "LeadGen AI — " + _SITE_URL_TRACKED,
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
            f'<p><a href="{e(_AUDIT_URL_TRACKED)}" '
            'style="background:#4f46e5;color:#fff;padding:10px 18px;'
            'border-radius:6px;text-decoration:none;display:inline-block;">'
            "Free sample + audit dekhein</a></p>"
            f'<p>Ya seedha WhatsApp: <a href="{e(_WA_LINK)}">{e(_WA_LINK)}</a></p>'
            f'<p style="color:#888;font-size:12px;">{e(_UNSUB_LINE)}</p>'
            f"<p>Shukriya,<br>{e(from_name)}<br>"
            f'LeadGen AI — <a href="{e(_SITE_URL_TRACKED)}">{e(_SITE_URL_TRACKED)}</a></p>'
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
            f"{_AUDIT_URL_TRACKED}\n\n{_UNSUB_LINE}\n\nShukriya,\n{from_name}\n"
            f"LeadGen AI — {_SITE_URL_TRACKED}"
        )
        return _pick_spintax(subject), text, text


def _valid_email(addr: str) -> bool:
    a = (addr or "").strip()
    if not ("@" in a and "." in a.split("@")[-1] and len(a) >= 6):
        return False
    # Deliverability gate (syntax + MX) — keeps bounce rate <2% so Gmail/Outlook don't
    # reject our bulk mail and the sending domain stays clean. Defensive: if
    # email-validator isn't installed, the basic check above is enough.
    try:
        import os

        from app.lead_scraper.email_verify import verify

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
        # pending_for_outreach = ALL prospects me se reachable+unemailed (oldest-first),
        # list_prospects(limit=500) ke bajaye — jiska 500-newest cap reachable backlog
        # ko outreach se chhupa deta tha (470 emailable prospects kabhi email nahi hote).
        candidates: list[dict[str, Any]] = []
        for p in prospector.pending_for_outreach(limit=500):
            email = str(p.get("email") or "").strip()
            if not _valid_email(email):
                result["skipped_no_email"] += 1
                continue
            if p.get("emailed_at"):
                continue  # already emailed — never re-send (defensive; pre-filtered)
            candidates.append(p)

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
            result["candidates"] = len(candidates)
            return result

        batch = candidates[:cap]

        from app.integrations.email_sender import EmailSender

        sender = EmailSender()

        for idx, p in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            # RFC 8058 / DPDP: one-click-unsubscribed = skip; baaki sab ko
            # List-Unsubscribe headers ke saath bhejo (Gmail/Yahoo deliverability).
            _unsub_hdrs: dict[str, str] = {}
            try:
                from app.platform import email_unsub as _eu

                if to_addr and _eu.is_suppressed(to_addr):
                    result["suppressed"] = result.get("suppressed", 0) + 1
                    continue
                _unsub_hdrs = _eu.headers_for(to_addr)
            except Exception:
                pass
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
        for p in prospector._read_all():
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

        for idx, (p, step) in enumerate(batch):
            pid = p.get("id")
            to_addr = str(p.get("email") or "").strip()
            biz = str(p.get("business_name") or "").strip() or "(unknown)"
            # RFC 8058 / DPDP: unsubscribed = skip followups too; rest get headers.
            _unsub_hdrs: dict[str, str] = {}
            try:
                from app.platform import email_unsub as _eu

                if to_addr and _eu.is_suppressed(to_addr):
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

        try:  # warmup stats (flag-independent)
            from app.platform import email_warmup

            email_warmup.record_sent(int(result.get("sent") or 0))
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

        # ALL prospects (not list_prospects' 500-newest cap) — warna pending/total galat
        # dikhte (470 reachable backlog "0 pending" lagta tha).
        try:
            rows = prospector._read_all()
        except Exception:
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
