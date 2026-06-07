"""
Prospector — HAMARE platform ke liye Tier-1 client hunting (Rohan ka kaam).
===========================================================================

Tier-1 = businesses jo HAMARE client banenge (solar installer, real estate
agency, coaching institute, interior designer...). Google Maps scraper se
unhe dhundo, dedupe karo, personalized Hinglish WhatsApp pitch banao aur
data/prospects.jsonl me queue karo — phir /app/outreach page se user ek-ek
ko "📲 WhatsApp bhejo" karta hai.

Public API:
  - run_prospecting(limit_per_query=10) -> dict   (async; NEVER raises)
  - list_prospects(status=None, limit=100) -> list (newest first)
  - mark_prospect(pid, status) -> bool             (ready→sent/replied/client/dead)

Scraper best-effort hai: Google Maps API key na ho to playwright fallback,
wo bhi na ho to query skip ho jaati hai (count me dikhta hai) — kabhi crash
nahi. Scheduler (team_scheduler) roz 09:30 IST pe chalata hai.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Append-only store — public_site.py ke inquiries.jsonl jaisa pattern.
_PROSPECTS_FILE = os.path.join("data", "prospects.jsonl")

# Allowed pipeline statuses.
VALID_STATUSES = ("ready", "sent", "replied", "client", "dead")

# --------------------------------------------------------------------------- #
# Targets — kaunse niches ke businesses dhundhne hain (env-overridable).
# Env PROSPECT_TARGETS = JSON list: [{"niche": "...", "query": "...",
# "cities": ["...", ...]}, ...]
# --------------------------------------------------------------------------- #
_DEFAULT_CITIES = ["Pune", "Mumbai", "Nagpur"]
_DEFAULT_TARGETS: List[Dict[str, Any]] = [
    {"niche": "solar_residential", "query": "solar installer", "cities": _DEFAULT_CITIES},
    {"niche": "real_estate", "query": "real estate agency", "cities": _DEFAULT_CITIES},
    {"niche": "coaching", "query": "coaching institute", "cities": _DEFAULT_CITIES},
    {"niche": "interior_designers", "query": "interior designer", "cities": _DEFAULT_CITIES},
]

# Niche-specific pain line for the pitch (fallback generic).
_NICHE_PAIN: Dict[str, str] = {
    "solar_residential": "solar inquiries me aadhe log sirf price puch ke gayab ho jaate hain",
    "real_estate": "site-visit tak pahunchne wale serious buyers dhundna mushkil hai",
    "coaching": "admission season me har inquiry ko time pe follow-up nahi ho paata",
    "interior_designers": "naye project ke liye serious clients tak pahunchna costly hai",
}
_GENERIC_PAIN = "naye customers tak pahunchna har mahine mehenga aur slow hai"


def _targets() -> List[Dict[str, Any]]:
    """PROSPECT_TARGETS env (JSON) ya defaults. Malformed env -> defaults."""
    raw = os.environ.get("PROSPECT_TARGETS", "").strip()
    if not raw:
        return _DEFAULT_TARGETS
    try:
        data = json.loads(raw)
        out: List[Dict[str, Any]] = []
        for t in data if isinstance(data, list) else []:
            if not isinstance(t, dict) or not t.get("query"):
                continue
            cities = t.get("cities") or _DEFAULT_CITIES
            out.append({
                "niche": str(t.get("niche") or "general"),
                "query": str(t["query"]),
                "cities": [str(c) for c in cities if str(c).strip()],
            })
        if out:
            return out
    except Exception as e:
        logger.warning(f"[prospector] PROSPECT_TARGETS parse failed, using defaults: {e}")
    return _DEFAULT_TARGETS


# --------------------------------------------------------------------------- #
# Phone helpers
# --------------------------------------------------------------------------- #
def _phone_digits(raw: Optional[str]) -> str:
    """Sirf digits; +91/0 prefix normalize karke 10-digit lautao ('' = unusable)."""
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10:
        return digits
    return ""


# --------------------------------------------------------------------------- #
# Pitch builder (template — NO LLM, instant + deterministic)
# --------------------------------------------------------------------------- #
def _niche_display(niche: str) -> str:
    """NICHES se readable naam (lazy, fallback = key prettified)."""
    try:
        from app.niches import NICHES

        cfg = NICHES.get(niche) or {}
        name = cfg.get("display_name") or cfg.get("name")
        if name:
            # Pitch ke liye short rakho — "(...)" wala suffix kaat do.
            return str(name).split("(")[0].strip()[:40]
    except Exception:
        pass
    return (niche or "business").replace("_", " ").title()


def build_pitch(business_name: str, niche: str, city: str = "") -> str:
    """Short personalized Hinglish WhatsApp pitch (3 lines)."""
    pain = _NICHE_PAIN.get(niche, _GENERIC_PAIN)
    nd = _niche_display(niche)
    return (
        f"Namaste {business_name} ji 🙏 Main Sumit, LeadGen AI se. "
        f"{nd} business me {pain} — hamara AI voice agent aapke liye "
        f"interested customers ko khud call karke QUALIFIED leads laata hai. "
        f"Shuruat me 10 leads bilkul FREE. 2-min live demo yahan suniye: "
        f"leadsgenai.in/app/test-call"
    )


def _wa_link(phone10: str, pitch: str) -> str:
    return f"https://wa.me/91{phone10}?text={urllib.parse.quote(pitch)}"


# --------------------------------------------------------------------------- #
# jsonl persistence
# --------------------------------------------------------------------------- #
def _read_all() -> List[Dict[str, Any]]:
    """Saare prospects (parse-safe; corrupt lines skip)."""
    out: List[Dict[str, Any]] = []
    try:
        if not os.path.isfile(_PROSPECTS_FILE):
            return out
        with open(_PROSPECTS_FILE, "r", encoding="utf-8") as f:
            for ln in f:
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug(f"[prospector] prospects.jsonl read failed: {e}")
    return out


def _append(rec: Dict[str, Any]) -> bool:
    try:
        os.makedirs(os.path.dirname(_PROSPECTS_FILE) or ".", exist_ok=True)
        with open(_PROSPECTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[prospector] prospects.jsonl write failed: {e}")
        return False


def list_prospects(status: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Prospects newest-first; optional status filter. Kabhi raise nahi karta."""
    try:
        rows = _read_all()
        if status:
            rows = [r for r in rows if (r.get("status") or "ready") == status]
        rows.sort(key=lambda r: str(r.get("found_at") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 500))]
    except Exception as e:
        logger.warning(f"[prospector] list_prospects failed: {e}")
        return []


def mark_prospect(pid: str, status: str) -> bool:
    """Ek prospect ka status update karo (poora file rewrite — chhota file hai).

    True = mila aur update hua. Invalid status / missing id = False.
    """
    try:
        status = (status or "").strip().lower()
        if status not in VALID_STATUSES:
            return False
        rows = _read_all()
        found = False
        for r in rows:
            if r.get("id") == pid:
                r["status"] = status
                r["status_at"] = datetime.utcnow().isoformat() + "Z"
                found = True
                break
        if not found:
            return False
        os.makedirs(os.path.dirname(_PROSPECTS_FILE) or ".", exist_ok=True)
        tmp = _PROSPECTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PROSPECTS_FILE)
        return True
    except Exception as e:
        logger.warning(f"[prospector] mark_prospect failed: {e}")
        return False


# --------------------------------------------------------------------------- #
# Main run — scraper best-effort, dedupe by phone digits, pitch + wa_link
# --------------------------------------------------------------------------- #
async def run_prospecting(limit_per_query: int = 10) -> Dict[str, Any]:
    """Targets × cities pe Google Maps scraper chalao, naye prospects queue karo.

    Returns summary dict. NEVER raises — har query apne try/except me hai,
    scraper unavailable ho to skip count badhta hai.
    """
    summary: Dict[str, Any] = {
        "ok": True,
        "new": 0,
        "duplicates": 0,
        "no_phone": 0,
        "queries_run": 0,
        "queries_failed": 0,
        "queries_empty": 0,
        "by_niche": {},
        "scraper": "unavailable",
    }
    try:
        # Dedupe set: existing prospects ke phone digits.
        seen: Set[str] = set()
        for r in _read_all():
            d = _phone_digits(r.get("phone"))
            if d:
                seen.add(d)
            # business+city bhi (phone-less records repeat na ho)
            seen.add(f"{str(r.get('business_name') or '').strip().lower()}|{str(r.get('city') or '').strip().lower()}")

        # Scraper init — best-effort. Na mile to gracefully empty run return.
        scraper = None
        try:
            from app.lead_scraper.google_maps import GoogleMapsScraper

            scraper = GoogleMapsScraper()
            # .env me placeholder key ("your-google-maps-api-key" type) ho to
            # API path har query fail karega — blank karke playwright fallback.
            key = str(getattr(scraper, "api_key", "") or "")
            if key and any(t in key.lower() for t in ("your-", "your_", "placeholder", "xxx", "changeme")):
                scraper.api_key = None
                key = ""
            summary["scraper"] = "api" if key else "playwright_fallback"
        except Exception as e:
            logger.warning(f"[prospector] scraper unavailable: {e}")
            summary["scraper"] = f"unavailable: {e}"

        targets = _targets()
        pairs: List[Tuple[Dict[str, Any], str]] = [
            (t, city) for t in targets for city in (t.get("cities") or [])
        ]

        for target, city in pairs:
            niche = target.get("niche") or "general"
            query = target.get("query") or ""
            businesses: List[Any] = []
            if scraper is not None and query:
                try:
                    businesses = await scraper.search_businesses(
                        query=query, location=city,
                        max_results=max(1, min(int(limit_per_query), 50)),
                    )
                    summary["queries_run"] += 1
                    if not businesses:
                        summary["queries_empty"] += 1
                except Exception as e:
                    summary["queries_failed"] += 1
                    logger.warning(f"[prospector] query '{query}' in {city} failed: {e}")
                    continue
            else:
                summary["queries_failed"] += 1
                continue

            for biz in businesses or []:
                try:
                    name = str(getattr(biz, "name", "") or "").strip()
                    if not name:
                        continue
                    phone10 = _phone_digits(getattr(biz, "phone", None))
                    biz_key = f"{name.lower()}|{city.strip().lower()}"
                    if not phone10:
                        summary["no_phone"] += 1
                        continue
                    if phone10 in seen or biz_key in seen:
                        summary["duplicates"] += 1
                        continue

                    pitch = build_pitch(name, niche, city)
                    rec: Dict[str, Any] = {
                        "id": str(uuid.uuid4()),
                        "found_at": datetime.utcnow().isoformat() + "Z",
                        "business_name": name[:200],
                        "phone": "+91" + phone10,
                        "address": str(getattr(biz, "address", "") or "")[:300],
                        "city": city,
                        "niche": niche,
                        "rating": getattr(biz, "rating", None),
                        "source_query": query,
                        "pitch": pitch,
                        "wa_link": _wa_link(phone10, pitch),
                        "status": "ready",
                    }
                    if _append(rec):
                        seen.add(phone10)
                        seen.add(biz_key)
                        summary["new"] += 1
                        summary["by_niche"][niche] = summary["by_niche"].get(niche, 0) + 1
                except Exception as e:
                    logger.debug(f"[prospector] record build failed: {e}")

        # Team activity — Rohan (Leads Manager). Never raises.
        try:
            from app.platform.team import log_event

            log_event(
                "rohan",
                "prospects_found",
                f"{summary['new']} naye prospects ({summary['queries_run']} queries; "
                f"{summary['duplicates']} dup, {summary['no_phone']} bina-phone)",
                status="ok" if summary["queries_failed"] == 0 else "warn",
                meta={k: summary[k] for k in
                      ("new", "duplicates", "no_phone", "queries_run",
                       "queries_failed", "queries_empty", "by_niche", "scraper")},
            )
        except Exception:
            pass

        logger.info(f"[prospector] run done: {summary}")
        return summary
    except Exception as e:  # absolute guard — scheduler/API kabhi na gire
        logger.warning(f"[prospector] run_prospecting failed: {e}")
        summary["ok"] = False
        summary["error"] = str(e)
        return summary


__all__ = [
    "run_prospecting", "list_prospects", "mark_prospect",
    "build_pitch", "VALID_STATUSES",
]
