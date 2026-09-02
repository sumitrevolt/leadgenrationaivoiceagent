"""
festivals.py — Indian festival calendar (Jun 2026 → Dec 2027) + festival posts.
===============================================================================

Static curated list (approx dates — lunar festivals +/- 1-2 din ho sakte
hain, marketing ke liye kaafi). `upcoming(days)` aaj se aage ke festivals
deta hai; `festival_posts()` nearest 3 ke liye LLM captions (1 call) —
template fallback ke saath. KABHI empty nahi, KABHI raise nahi.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

try:
    from app.voice_agent import free_ai  # type: ignore
except Exception:  # pragma: no cover - free_ai khud import-safe hai
    free_ai = None  # type: ignore

try:
    from app.marketing.post_generator import _niche_name, _niche_pitch  # type: ignore
except Exception:  # pragma: no cover

    def _niche_name(niche: str) -> str:  # type: ignore
        return (niche or "general").replace("_", " ").title()

    def _niche_pitch(niche: str) -> str:  # type: ignore
        return "Quality service, sahi daam, 100% bharosa."


# ============================================================================ #
# Festival calendar — {date, name, type, marketing_angle}
# "type" values: national | hindu | muslim | sikh | christian | regional
# (NOTE: comment "type:" se shuru nahi ho sakta — mypy use PEP-484 type-comment
# samajh ke "Invalid syntax" deta hai.)
# ============================================================================ #

FESTIVALS_2026_27: list[dict[str, str]] = [
    {
        "date": "2026-07-16",
        "name": "Rath Yatra",
        "type": "hindu",
        "marketing_angle": "Naye safar ki shuruaat — 'naya kadam' offer launch karne ka perfect din.",
    },
    {
        "date": "2026-08-15",
        "name": "Independence Day",
        "type": "national",
        "marketing_angle": "Freedom-theme sale (79th I-Day) — 'Aazadi offer' tricolor creatives ke saath.",
    },
    {
        "date": "2026-08-26",
        "name": "Onam",
        "type": "regional",
        "marketing_angle": "Kerala/south audience ke liye Onam sadhya-style 'full thali' bundle offer.",
    },
    {
        "date": "2026-08-28",
        "name": "Raksha Bandhan",
        "type": "hindu",
        "marketing_angle": "Bhai-behen gifting angle — 'Rakhi special' combo ya behen ke liye discount.",
    },
    {
        "date": "2026-09-04",
        "name": "Janmashtami",
        "type": "hindu",
        "marketing_angle": "Matki-phod contest ya midnight flash-offer — engagement bahut high hota hai.",
    },
    {
        "date": "2026-09-14",
        "name": "Ganesh Chaturthi",
        "type": "hindu",
        "marketing_angle": "'Shubh aarambh' angle — naye kaam/booking shuru karne ka sabse mangal din.",
    },
    {
        "date": "2026-10-11",
        "name": "Navratri (Start)",
        "type": "hindu",
        "marketing_angle": "9-din 9-offers series chalao — har din ek naya color/deal, daily posts ready.",
    },
    {
        "date": "2026-10-20",
        "name": "Dussehra",
        "type": "hindu",
        "marketing_angle": "'Burai par jeet' — purani problems (mehengi bijli/purana ghar) par offer-attack.",
    },
    {
        "date": "2026-10-29",
        "name": "Karwa Chauth",
        "type": "hindu",
        "marketing_angle": "Couples gifting — 'patni ke liye special' offers, evening-slot bookings push karo.",
    },
    {
        "date": "2026-11-06",
        "name": "Dhanteras",
        "type": "hindu",
        "marketing_angle": "Saal ka SABSE bada buying-day — 'shubh kharidari' badi-ticket offers aaj hi.",
    },
    {
        "date": "2026-11-08",
        "name": "Diwali",
        "type": "hindu",
        "marketing_angle": "Greetings + gratitude post zaroor; Diwali-dhamaka sale ka final push.",
    },
    {
        "date": "2026-11-11",
        "name": "Bhai Dooj",
        "type": "hindu",
        "marketing_angle": "Rakhi jaisa gifting angle round-2 — sibling combo offers.",
    },
    {
        "date": "2026-11-15",
        "name": "Chhath Puja",
        "type": "regional",
        "marketing_angle": "Bihar/UP/Jharkhand audience se emotional connect — shraddha-bhari greeting post.",
    },
    {
        "date": "2026-11-24",
        "name": "Guru Nanak Jayanti",
        "type": "sikh",
        "marketing_angle": "Seva-bhaav greeting — community-respect post, hard-sell nahi.",
    },
    {
        "date": "2026-12-25",
        "name": "Christmas",
        "type": "christian",
        "marketing_angle": "Year-end festive sale + Secret-Santa style surprise discounts.",
    },
    {
        "date": "2027-01-01",
        "name": "New Year",
        "type": "national",
        "marketing_angle": "'Naya saal, naya …' resolution-angle — saal ki pehli booking par offer.",
    },
    {
        "date": "2027-01-14",
        "name": "Makar Sankranti / Pongal",
        "type": "hindu",
        "marketing_angle": "Patang/fasal theme — 'oonchi udaan' offers, south me Pongal greetings.",
    },
    {
        "date": "2027-01-26",
        "name": "Republic Day",
        "type": "national",
        "marketing_angle": "78th R-Day — desh-bhakti theme sale, tricolor branding ek din pehle se.",
    },
    {
        "date": "2027-03-06",
        "name": "Maha Shivratri",
        "type": "hindu",
        "marketing_angle": "Bhakti-greeting + vrat-special angle (food/wellness businesses ke liye gold).",
    },
    {
        "date": "2027-03-10",
        "name": "Eid-ul-Fitr",
        "type": "muslim",
        "marketing_angle": "Eid Mubarak greetings + Eidi-style gift offers, family-feast angle.",
    },
    {
        "date": "2027-03-22",
        "name": "Holi",
        "type": "hindu",
        "marketing_angle": "Rang-barse colorful creatives — 'rangon wali deal' bundle offers.",
    },
    {
        "date": "2027-04-14",
        "name": "Baisakhi",
        "type": "sikh",
        "marketing_angle": "Fasal/naye saal (Punjabi) ki khushi — harvest-bonus offers north audience ke liye.",
    },
    {
        "date": "2027-05-09",
        "name": "Akshaya Tritiya",
        "type": "hindu",
        "marketing_angle": "'Akshaya' = kabhi na ghatne wala — investments/gold/property ke liye #1 din.",
    },
    {
        "date": "2027-05-17",
        "name": "Eid-ul-Adha",
        "type": "muslim",
        "marketing_angle": "Bakrid Mubarak greeting — community-connect post, qurbani/sharing theme.",
    },
    {
        "date": "2027-08-15",
        "name": "Independence Day",
        "type": "national",
        "marketing_angle": "80th Independence Day — milestone-saal ki badi patriotic sale.",
    },
    {
        "date": "2027-08-17",
        "name": "Raksha Bandhan",
        "type": "hindu",
        "marketing_angle": "Rakhi gifting combos — behen/bhai dono ke liye paired offers.",
    },
    {
        "date": "2027-09-04",
        "name": "Ganesh Chaturthi",
        "type": "hindu",
        "marketing_angle": "Shubh-aarambh bookings — Ganpati ke 10 din daily-post series.",
    },
    {
        "date": "2027-10-29",
        "name": "Diwali",
        "type": "hindu",
        "marketing_angle": "Diwali 2027 mega-sale — Dhanteras se Bhai-Dooj tak full festive week plan.",
    },
    {
        "date": "2027-12-25",
        "name": "Christmas",
        "type": "christian",
        "marketing_angle": "Saal ki aakhri badi sale — year-end gratitude + clearance offers.",
    },
]


def _parse_date(s: str) -> date | None:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def upcoming(days: int = 45) -> list[dict[str, str]]:
    """Aaj se agle `days` din ke festivals (sorted). Kabhi raise nahi karta."""
    try:
        days = max(1, min(int(days), 730))
    except (TypeError, ValueError):
        days = 45
    today = date.today()
    out: list[dict[str, str]] = []
    for f in FESTIVALS_2026_27:
        d = _parse_date(f.get("date", ""))
        if d is None:
            continue
        delta = (d - today).days
        if 0 <= delta <= days:
            entry = dict(f)
            entry["days_away"] = delta  # type: ignore[assignment]
            out.append(entry)
    out.sort(key=lambda x: x["date"])
    return out


def _next_n(n: int = 3) -> list[dict[str, str]]:
    """Aaj ke baad ke nearest n festivals — window ki parwah kiye bina.

    Calendar khatam ho jaaye (sab past) to aakhri n entries (never empty).
    """
    today = date.today()
    future = []
    for f in FESTIVALS_2026_27:
        d = _parse_date(f.get("date", ""))
        if d is not None and (d - today).days >= 0:
            future.append((d, f))
    future.sort(key=lambda x: x[0])
    picked = [dict(f) for _, f in future[:n]]
    if not picked:  # poora calendar past me — phir bhi kuch do
        picked = [dict(f) for f in FESTIVALS_2026_27[-n:]]
    return picked


def _template_caption(festival: str, business_name: str, niche: str) -> str:
    return (
        f"✨ {festival} ki dher saari shubhkamnayein! 🪔\n"
        f"{business_name} parivar ki taraf se aapko aur aapke parivar ko "
        f"khushiyon bhara tyohar mubarak. {_niche_pitch(niche)}\n"
        f"📞 Is shubh avsar par humse judiye — abhi contact karein!"
    )


def _parse_festival_captions(text: str, names: list[str]) -> dict[str, str]:
    """'1. <caption>' / 'FestivalName: <caption>' dono style lenient parse."""
    found: dict[str, str] = {}
    try:
        # Style A: numbered lines (multi-line captions tak chalta hai)
        blocks = re.split(r"\n\s*(?=\d+[\.\)]\s)", "\n" + (text or "").strip())
        cleaned = []
        for b in blocks:
            b = re.sub(r"^\s*\d+[\.\)]\s*", "", b.strip()).strip()
            if b:
                cleaned.append(b)
        if len(cleaned) >= len(names):
            for i, name in enumerate(names):
                cap = cleaned[i].strip()
                # "FestivalName:" prefix hata do agar model ne laga diya
                cap = re.sub(rf"^{re.escape(name)}\s*[:\-–]\s*", "", cap, flags=re.I).strip()
                if cap:
                    found[name] = cap[:500]
            return found
        # Style B: "Name: caption" lines
        for name in names:
            m = re.search(
                rf"{re.escape(name)}\s*[:\-–]\s*(.+?)(?=\n\s*\S+\s*[:\-–]|\Z)", text, re.S | re.I
            )
            if m and m.group(1).strip():
                found[name] = m.group(1).strip()[:500]
    except Exception:  # pragma: no cover
        return found
    return found


# --------------------------------------------------------------------------- #
# FREE public-holidays enrichment — two keyed/keyless sources, defensive, cached.
#
# Source 1 — Calendarific (free tier, CALENDARIFIC_API_KEY env set):
#   https://calendarific.com/api/v2/holidays?api_key=KEY&country=IN&year=YEAR
#   Free plan: 1,000 calls/mo (per-year cache → 2 calls/year plenty).
#   Returns official + Hindu + Muslim + Sikh + Christian public holidays for India.
#   PREFERRED when key available — best India coverage.
#
# Source 2 — Nager.Date (keyless fallback):
#   ⚠️ LIVE-TESTED: India (IN) NOT in AvailableCountries → HTTP 204 → empty [].
#   Effectively a no-op for India; kept for non-IN country future use.
#
# Both: gated FESTIVALS_LIVE_HOLIDAYS=1 (default OFF = zero change),
#        per-year cached, NEVER raises (network/parse fail → []).
# CALENDARIFIC_API_KEY is env-only (not a boolean AUTOMATION_FLAG — it's a secret key).
# --------------------------------------------------------------------------- #
_HOLIDAY_CACHE: dict[int, list[dict[str, str]]] = {}
_CALENDARIFIC_CACHE: dict[int, list[dict[str, str]]] = {}


async def _fetch_calendarific(year: int, api_key: str) -> list[dict[str, str]]:
    """Calendarific India holidays for `year`. Per-year cached. NEVER raises."""
    if year in _CALENDARIFIC_CACHE:
        return _CALENDARIFIC_CACHE[year]
    out: list[dict[str, str]] = []
    try:
        import httpx

        url = "https://calendarific.com/api/v2/holidays"
        params = {"api_key": api_key, "country": "IN", "year": year}
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(url, params=params)
            if r.status_code == 200:
                data = r.json() or {}
                holidays = (data.get("response") or {}).get("holidays") or []
                for h in holidays:
                    nm = (h.get("name") or "").strip()
                    iso = ((h.get("date") or {}).get("iso") or "")[:10]
                    types = h.get("type") or []
                    htype = "national"
                    if isinstance(types, list) and types:
                        t0 = str(types[0]).lower()
                        if "hindu" in t0:
                            htype = "hindu"
                        elif "muslim" in t0 or "islam" in t0:
                            htype = "muslim"
                        elif "sikh" in t0:
                            htype = "sikh"
                        elif "christian" in t0:
                            htype = "christian"
                        elif "regional" in t0 or "observance" in t0:
                            htype = "regional"
                    if nm and iso:
                        out.append(
                            {
                                "name": nm,
                                "date": iso,
                                "type": htype,
                                "marketing_angle": "Chhutti greeting / special offer",
                                "source": "calendarific",
                            }
                        )
            elif r.status_code == 401:
                logger.warning("Calendarific: invalid API key — check CALENDARIFIC_API_KEY")
            else:
                logger.debug("Calendarific: HTTP %s for year %s", r.status_code, year)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("_fetch_calendarific skip: %s", e)
    _CALENDARIFIC_CACHE[year] = out
    return out


async def fetch_public_holidays(year: int, country: str = "IN") -> list[dict[str, str]]:
    """Public holidays for `year`/`country`.

    Priority:
      1. Calendarific (when CALENDARIFIC_API_KEY set) — best India coverage.
      2. Nager.Date (keyless) — good for non-IN; India returns [] (unsupported).
    Per-year cached, 5-8s timeout, NEVER raises (network/parse fail -> []).
    """
    if year in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[year]

    # Calendarific preferred when key available (India coverage)
    cal_key = os.environ.get("CALENDARIFIC_API_KEY", "").strip()
    if cal_key and country == "IN":
        out = await _fetch_calendarific(year, cal_key)
        _HOLIDAY_CACHE[year] = out
        return out

    # Nager.Date keyless fallback (non-IN countries; India = 204/empty)
    out: list[dict[str, str]] = []
    try:
        import httpx

        url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(url)
            if r.status_code == 200:
                for h in r.json() or []:
                    nm = h.get("localName") or h.get("name")
                    dt = h.get("date")
                    if nm and dt:
                        out.append(
                            {
                                "name": str(nm),
                                "date": str(dt),
                                "type": "national",
                                "marketing_angle": "Chhutti greeting / special offer",
                                "source": "nager",
                            }
                        )
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("fetch_public_holidays skip: %s", e)
    _HOLIDAY_CACHE[year] = out
    return out


async def upcoming_enriched(days: int = 45) -> list[dict[str, str]]:
    """`upcoming(days)` + free public-holidays merge (dedup by date+name). Gated
    `FESTIVALS_LIVE_HOLIDAYS=1` (default OFF = sirf static curated list). Never raises.
    """
    base = upcoming(days)
    if os.environ.get("FESTIVALS_LIVE_HOLIDAYS", "0").strip().lower() not in ("1", "true", "yes"):
        return base
    try:
        today = date.today()
        end = date.fromordinal(today.toordinal() + max(1, int(days)))
        seen = {(f.get("date"), str(f.get("name", "")).lower()) for f in base}
        merged = list(base)
        for yr in (today.year, today.year + 1):
            for h in await fetch_public_holidays(yr):
                d = _parse_date(h.get("date", ""))
                key = (h.get("date"), str(h.get("name", "")).lower())
                if d and today <= d <= end and key not in seen:
                    seen.add(key)
                    merged.append(h)
        merged.sort(key=lambda f: f.get("date", ""))
        return merged
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("upcoming_enriched skip: %s", e)
        return base


async def festival_posts(
    business_name: str, niche: str = "general", days: int = 45
) -> dict[str, Any]:
    """Upcoming festivals + nearest 3 ke ready captions (1 LLM call, template fallback).

    Returns: {"upcoming": [...], "posts": [{"festival","date","type","marketing_angle",
    "caption"}], "provider"}. KABHI empty nahi.
    """
    business_name = (business_name or "").strip() or "Aapka Business"
    niche = (niche or "general").strip().lower() or "general"

    upcoming_list = await upcoming_enriched(days)
    targets = upcoming_list[:3] if upcoming_list else _next_n(3)
    names = [t["name"] for t in targets]

    captions: dict[str, str] = {}
    provider = ""
    if free_ai is not None and names:
        try:
            system = (
                "Tu Indian small-business ka festival-marketing expert hai. Har festival "
                "ke liye ek chhota Hinglish social post caption likh (2-3 lines, emojis, "
                "business naam naturally use kar, halka sa CTA). Output EXACTLY:\n"
                + "\n".join(f"{i + 1}. <{n} ka caption>" for i, n in enumerate(names))
                + "\nKoi extra commentary nahi."
            )
            user = (
                f"Business: {business_name} (category: {_niche_name(niche)}, "
                f"angle: {_niche_pitch(niche)}). Festivals: {', '.join(names)}."
            )
            text, provider = await free_ai.chat(
                system,
                [{"role": "user", "content": user}],
                max_tokens=500,
                temperature=0.8,
            )
            if text and text.strip():
                captions = _parse_festival_captions(text, names)
        except Exception as e:
            logger.warning(f"festival_posts LLM step failed, using templates: {e}")

    posts: list[dict[str, str]] = []
    used_template = False
    for t in targets:
        cap = (captions.get(t["name"]) or "").strip()
        if not cap:
            cap = _template_caption(t["name"], business_name, niche)
            used_template = True
        posts.append(
            {
                "festival": t["name"],
                "date": t["date"],
                "type": t.get("type", ""),
                "marketing_angle": t.get("marketing_angle", ""),
                "caption": cap,
            }
        )

    return {
        "business_name": business_name,
        "niche": niche,
        "upcoming": upcoming_list,
        "posts": posts,
        "provider": ("template" if (used_template and not captions) else provider or "template"),
    }
