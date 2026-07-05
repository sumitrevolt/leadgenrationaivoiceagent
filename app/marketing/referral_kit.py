"""
referral_kit.py — "Refer & Earn" word-of-mouth kit (100% free stack).
======================================================================

Chhote local business ke liye referral loop ka poora kit — bina kisi paid
referral-SaaS ke (ReferralCandy/Tremendous skip):

  make_referral(business_name, reward, referrer_name) -> dict
    - referral CODE   (business-initials + 4 alnum, deterministic per business)
    - shareable Hinglish WhatsApp message ("Maine X try kiya, aap bhi karo …")
    - referral LINK   (https://leadsgenai.in/b/<slug>?ref=<code>)
    - referral CARD SVG (1080x1080, "Refer & Earn", code BIG, reward, scan-QR
      via review_kit.qr_svg of the link) — print/share-ready.
  record_referral(code, referred_contact)  -> dict   (append referrals.jsonl)
  referral_stats(code=None)                 -> dict   (counts; per-code ya total)

PURE LOGIC — koi LLM/network nahi. Generator functions KABHI raise nahi karte;
inputs XML-escaped (SVG injection-safe). QR review_kit se reuse hota hai.
File-const `_REFERRALS_FILE` test-monkeypatch ke liye exposed.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import quote

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# QR encoder review_kit se reuse — import-safe (na mile to QR slot khali rahega).
try:
    from app.marketing.review_kit import qr_svg  # type: ignore
except Exception:  # pragma: no cover - review_kit khud pure-stdlib hai
    qr_svg = None  # type: ignore

_FONT = "Segoe UI, Arial, sans-serif"

# Tests isse monkeypatch karte hain (tmp file). Hamesha is const ke through padho.
_REFERRALS_FILE = os.path.join("data", "referrals.jsonl")

_SITE_BASE = "https://leadsgenai.in"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    """kebab-case slug (mini_site/clients_store jaisa); khali = 'business'."""
    s = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return s[:48] or "business"


def _initials(business_name: str) -> str:
    """Business naam se 2-4 letter prefix (REFER code human-readable banane ke liye)."""
    words = re.findall(r"[A-Za-z0-9]+", (business_name or "").strip())
    if not words:
        return "REF"
    if len(words) == 1:
        return words[0][:4].upper()
    return "".join(w[0] for w in words[:4]).upper()


def _code(business_name: str) -> str:
    """Deterministic referral code: <INITIALS><4 alnum> (same business => same code).

    4-char suffix business naam ke md5 se nikalta hai (unguessable-ish, stable,
    no collision-care needed at this scale)."""
    import hashlib

    prefix = _initials(business_name)
    digest = hashlib.md5(
        (business_name or "x").strip().lower().encode("utf-8", "ignore")
    ).hexdigest()
    # Base-36-ish 4-char suffix from the hex digest (A-Z0-9, no ambiguous chars).
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no I/O/0/1 confusion
    n = int(digest[:8], 16)
    suffix = ""
    for _ in range(4):
        n, r = divmod(n, len(alphabet))
        suffix += alphabet[r]
    return f"{prefix}{suffix}"


def _referral_link(slug: str, code: str) -> str:
    """Mini-site link ?ref=<code> ke saath (mini_site /b/<slug> isse track kar sakta)."""
    return f"{_SITE_BASE}/b/{slug}?ref={quote(code)}"


_CARD_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080">'
    "<defs>"
    '<linearGradient id="rfbg" x1="0%" y1="0%" x2="100%" y2="100%">'
    '<stop offset="0%" stop-color="{c1}"/><stop offset="100%" stop-color="{c2}"/>'
    "</linearGradient>"
    "</defs>"
    '<rect width="1080" height="1080" fill="url(#rfbg)"/>'
    '<circle cx="120" cy="140" r="6" fill="#ffffff" opacity="0.55"/>'
    '<circle cx="960" cy="120" r="5" fill="#ffffff" opacity="0.5"/>'
    '<circle cx="990" cy="300" r="4" fill="#ffffff" opacity="0.45"/>'
    '<text x="540" y="150" font-family="{font}" font-size="46" text-anchor="middle">\U0001f381</text>'
    '<text x="540" y="250" font-family="{font}" font-size="70" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle">Refer &amp; Earn</text>'
    '<text x="540" y="312" font-family="{font}" font-size="34" '
    'fill="#fde68a" text-anchor="middle">{business_name}</text>'
    '<text x="540" y="400" font-family="{font}" font-size="30" '
    'fill="#ffffff" text-anchor="middle" opacity="0.9">Dost ko bulao, dono ko milega:</text>'
    '<rect x="190" y="430" width="700" height="92" rx="46" fill="#ffffff"/>'
    '<text x="540" y="492" font-family="{font}" font-size="42" font-weight="bold" '
    'fill="{c2}" text-anchor="middle">\U0001f389 {reward}</text>'
    '<text x="540" y="588" font-family="{font}" font-size="26" '
    'fill="#ffffff" text-anchor="middle" opacity="0.85">Aapka referral code:</text>'
    '<rect x="240" y="612" width="600" height="104" rx="16" fill="#0b1020" opacity="0.28"/>'
    '<text x="540" y="686" font-family="{font}" font-size="62" font-weight="bold" '
    'fill="#ffffff" text-anchor="middle" letter-spacing="6">{code}</text>'
    '<rect x="410" y="760" width="260" height="260" rx="18" fill="#ffffff"/>'
    "{qr}"
    '<text x="540" y="1052" font-family="{font}" font-size="24" '
    'fill="#ffffff" text-anchor="middle" opacity="0.85">\U0001f4f1 Scan karo ya code batao</text>'
    "</svg>"
)

# Default brand-ish gradient (violet) — invalid/khali brand color = default.
_DEFAULT_C1 = "#7c3aed"
_DEFAULT_C2 = "#4f46e5"
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _hex_or(value: str, default: str) -> str:
    v = (value or "").strip()
    return v if _HEX_RE.match(v) else default


def make_referral(
    business_name: str,
    reward: str = "10% off",
    referrer_name: str = "",
    brand_primary: str = "",
    brand_accent: str = "",
    slug: str = "",
) -> dict[str, Any]:
    """Referral kit banao: code + WA message + link + 1080x1080 card SVG.

    KABHI raise nahi karta, never-empty. brand_primary/accent (#RRGGBB, optional)
    card gradient set karte hain; invalid/khali = default violet.

    `slug` = client record ka REAL mini-site slug (e.g. "jiya-makeover-d79d").
    Diya ho to referral link isi se banta hai (/b/<slug>); warna business naam
    se derive hota hai (backward-compat — standalone/agency use). REAL slug pass
    karna zaroori hai warna link 404 deta (derived slug != stored slug).

    Returns: {"code","reward","referrer_name","business_name","link","slug",
              "wa_message","sms_line","card_svg"}.
    """
    name = (business_name or "").strip() or "Hamara business"
    reward_s = (reward or "").strip() or "ek special discount"
    referrer = (referrer_name or "").strip()

    # REAL client slug prefer karo (stored /b/<slug>); na ho to naam se derive.
    slug = (slug or "").strip() or _slug(name)
    code = _code(name)
    link = _referral_link(slug, code)

    who = f"Maine {name}" if referrer == "" else f"Main ({referrer}) ne {name}"
    wa_message = (
        f"Namaste! \U0001f44b {who} try kiya aur mujhe kaafi achha laga. "
        f"Aap bhi try karein — mere referral code *{code}* se aapko *{reward_s}* milega! "
        f"\U0001f381\n\nYahan dekho → {link}"
    )
    sms_line = f"{name}: code {code} use karo, {reward_s} pao — {link}"

    # QR card (review_kit qr_svg of the referral link), gradient brand colors.
    qr = ""
    if qr_svg is not None:
        try:
            q = qr_svg(link, 260)
            # 260x260 QR box top-left at (410, 760) (card slot).
            qr = q.replace("<svg ", '<svg x="410" y="760" ', 1)
        except Exception as e:  # pragma: no cover - qr_svg deterministic
            logger.debug(f"[referral_kit] qr embed skip: {e}")

    c1 = _hex_or(brand_primary, _DEFAULT_C1)
    c2 = _hex_or(brand_accent, _DEFAULT_C2)
    try:
        card = _CARD_SVG.format(
            font=_FONT,
            c1=c1,
            c2=c2,
            business_name=escape(name, quote=True),
            reward=escape(reward_s, quote=True),
            code=escape(code, quote=True),
            qr=qr,
        )
    except Exception as e:  # pragma: no cover - format keys fixed hain
        logger.error(f"[referral_kit] card format failed: {e}")
        card = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080">'
            f'<rect width="1080" height="1080" fill="{_DEFAULT_C1}"/>'
            f'<text x="540" y="520" font-family="{_FONT}" font-size="62" font-weight="bold" '
            f'fill="#ffffff" text-anchor="middle">Refer &amp; Earn</text>'
            f'<text x="540" y="610" font-family="{_FONT}" font-size="54" '
            f'fill="#ffffff" text-anchor="middle" letter-spacing="6">{escape(code, quote=True)}</text>'
            "</svg>"
        )

    return {
        "code": code,
        "reward": reward_s,
        "referrer_name": referrer,
        "business_name": name,
        "slug": slug,
        "link": link,
        "wa_message": wa_message,
        "sms_line": sms_line,
        "card_svg": card,
    }


def record_referral(code: str, referred_contact: str = "") -> dict[str, Any]:
    """Ek referral use/lead append karo (data/referrals.jsonl). KABHI raise nahi.

    Returns: {"recorded": bool, "code", "at"}.
    """
    c = (code or "").strip().upper()
    if not c:
        return {"recorded": False, "code": "", "at": ""}
    rec = {
        "code": c,
        "referred_contact": (referred_contact or "").strip()[:120],
        "at": _now(),
    }
    try:
        os.makedirs(os.path.dirname(_REFERRALS_FILE) or ".", exist_ok=True)
        with open(_REFERRALS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return {"recorded": True, "code": c, "at": rec["at"]}
    except Exception as e:  # pragma: no cover
        logger.warning(f"[referral_kit] record failed: {e}")
        return {"recorded": False, "code": c, "at": ""}


def _read_all() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if not os.path.isfile(_REFERRALS_FILE):
            return rows
        with open(_REFERRALS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("code"):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"[referral_kit] read failed: {e}")
    return rows


def referral_stats(code: str | None = None) -> dict[str, Any]:
    """Referral counts. code diya to us code ka count; warna per-code breakdown
    + total. KABHI raise nahi karta.

    Returns: {"total", "by_code": {code: count}, "code"?: , "count"?: }.
    """
    rows = _read_all()
    by_code: dict[str, int] = {}
    for r in rows:
        c = str(r.get("code") or "").upper()
        if c:
            by_code[c] = by_code.get(c, 0) + 1
    out: dict[str, Any] = {"total": len(rows), "by_code": by_code}
    if code:
        c = code.strip().upper()
        out["code"] = c
        out["count"] = by_code.get(c, 0)
    return out


__all__ = ["make_referral", "record_referral", "referral_stats"]
