"""Lead Harvester — multi-source lead collection, automated loop ke liye.

Research: docs/LeadHarvester_Research_2026.md. LEGAL-FIRST design:
  - Sources sirf compliant: Places/OSM (existing prospector), Brave Search API
    (keyed) → business ki APNI website se public contacts, data.gov.in OGD
    (open license) seed names, website-enrich (email_finder + find_contacts).
  - JustDial/IndiaMART/LinkedIn/Facebook AUTO-scrape KABHI nahi (ToS/ban/IT-Act)
    — directory domains explicitly SKIP hote. Unka path = manual CSV import.
  - Polite: per-run fetch caps, timeouts, UA, sleep; anti-bot bypass NAHI.

Pipeline: collect (enabled sources) → normalize → validate (phonenumbers E.164
+ email MX) → dedupe (store phone/email) → persist (prospector._append = jsonl
+ DB mirror + pitch) → rescore. GATED loop `LEAD_HARVESTER=1` (manual API run
flag-independent). Gated sources bina key = inert skip. Kabhi raise nahi.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS = os.path.join("data", "harvest_runs.jsonl")
_FETCH_CAP = 6          # per websearch run site fetches
_HTTP_TIMEOUT = 10.0
_UA = "LeadGenAI/1.0 (business contact discovery; admin@leadsgenai.in)"

# In domains ko AUTO kabhi fetch/scrape nahi karte (ToS / ban / personal-data)
_BLOCKED_DOMAINS = (
    "justdial.com", "indiamart.com", "sulekha.com", "linkedin.com", "facebook.com",
    "instagram.com", "youtube.com", "twitter.com", "x.com", "quora.com", "reddit.com",
    "google.com", "wikipedia.org", "amazon.", "flipkart.", "olx.", "quikr.",
)

_PHONE_RE = re.compile(r"(?:\+91[\-\s]?|0)?([6-9]\d{9})")


def enabled() -> bool:
    return os.environ.get("LEAD_HARVESTER", "0").strip().lower() in ("1", "true", "yes")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_run(rec: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_RUNS) or ".", exist_ok=True)
        with open(_RUNS, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _blocked(url: str) -> bool:
    u = (url or "").lower()
    return any(d in u for d in _BLOCKED_DOMAINS)


def _existing_keys() -> tuple[set[str], set[str]]:
    """Store me already-known phones (10-digit) + emails — dedupe ke liye."""
    phones: set[str] = set()
    emails: set[str] = set()
    try:
        from app.platform import prospector

        for r in prospector._read_all():
            p = re.sub(r"\D", "", str(r.get("phone") or ""))[-10:]
            if len(p) == 10:
                phones.add(p)
            e = str(r.get("email") or "").strip().lower()
            if e:
                emails.add(e)
    except Exception:
        pass
    return phones, emails


# ---------------------------------------------------------------- validate


def _valid_phone(raw: str) -> str:
    """E.164 IN mobile ya empty. phonenumbers ho to use, warna regex fallback."""
    try:
        from app.lead_scraper import phone_validate

        v = phone_validate.validate_in(raw)
        if v.get("ok") and v.get("e164"):
            return str(v["e164"])
    except Exception:
        pass
    m = _PHONE_RE.search(raw or "")
    return f"+91{m.group(1)}" if m else ""


async def _valid_email(email: str) -> str:
    """Syntax+MX verified email ya empty (sender-rep safe)."""
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return ""
    try:
        from app.lead_scraper import email_verify

        r = email_verify.verify(e)  # sync, {"ok", "email", "reason"}, never raises
        if isinstance(r, dict) and r.get("ok"):
            return str(r.get("email") or e)
        return ""
    except Exception:
        return e  # verifier import na ho to syntax-pass rakho (outreach apna MX-gate karta hai)


# ---------------------------------------------------------------- sources


async def _src_prospector(niche: str, city: str, limit: int) -> dict[str, Any]:
    """Primary: existing Places+OSM rotation (khud persist karta)."""
    try:
        from app.platform import niche_prospector

        res = await niche_prospector.run(batch=2, limit_per_query=max(2, limit // 2))
        return {"source": "prospector", "persisted_internally": True, "detail": f"covered={res.get('covered', [])}", "leads": []}
    except Exception as e:
        return {"source": "prospector", "error": str(e)[:120], "leads": []}


async def _src_websearch(niche: str, city: str, limit: int) -> dict[str, Any]:
    """Brave Search (gated BRAVE_API_KEY) → business websites → public contacts.
    Directory/social domains SKIP (ToS). Bina key = inert."""
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return {"source": "websearch", "skipped": "no BRAVE_API_KEY", "leads": []}
    leads: list[dict[str, Any]] = []
    try:
        import httpx

        q = f"{niche.replace('_', ' ')} {city} contact phone"
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, headers={"User-Agent": _UA}) as client:
            r = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": q, "count": 10, "country": "IN"},
                headers={"X-Subscription-Token": key, "Accept": "application/json"},
            )
            if r.status_code != 200:
                return {"source": "websearch", "error": f"brave {r.status_code}", "leads": []}
            results = ((r.json().get("web") or {}).get("results") or [])[:10]
            fetched = 0
            for item in results:
                url = str(item.get("url") or "")
                if not url or _blocked(url) or fetched >= min(_FETCH_CAP, limit):
                    continue
                fetched += 1
                try:
                    page = await client.get(url, follow_redirects=True)
                    if page.status_code != 200:
                        continue
                    from app.lead_scraper import web_extract

                    contacts = web_extract.find_contacts(page.text) or {}
                    phones = contacts.get("phones") or []
                    emails = contacts.get("emails") or []
                    if not phones and not emails:
                        m = _PHONE_RE.search(page.text)
                        phones = [m.group(0)] if m else []
                    if phones or emails:
                        leads.append(
                            {
                                "business_name": str(item.get("title") or "")[:150],
                                "phone": phones[0] if phones else "",
                                "email": emails[0] if emails else "",
                                "website": url,
                                "city": city,
                                "niche": niche,
                                "source": "websearch",
                            }
                        )
                except Exception:
                    continue
                await asyncio.sleep(0.5)  # polite
    except Exception as e:
        return {"source": "websearch", "error": str(e)[:120], "leads": leads}
    return {"source": "websearch", "leads": leads}


async def _src_opendata(niche: str, city: str, limit: int) -> dict[str, Any]:
    """data.gov.in OGD (gated DATA_GOV_IN_API_KEY + DATA_GOV_RESOURCE_ID) —
    Udyam/MSME unit names = seed leads (no phone; enrich baad me). Open license."""
    key = os.environ.get("DATA_GOV_IN_API_KEY", "").strip()
    rid = os.environ.get("DATA_GOV_RESOURCE_ID", "").strip()
    if not key or not rid:
        return {"source": "opendata", "skipped": "no key/resource", "leads": []}
    leads: list[dict[str, Any]] = []
    try:
        import httpx

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            r = await client.get(
                f"https://api.data.gov.in/resource/{rid}",
                params={"api-key": key, "format": "json", "limit": min(limit, 20)},
            )
            if r.status_code != 200:
                return {"source": "opendata", "error": f"ogd {r.status_code}", "leads": []}
            for rec in (r.json().get("records") or [])[:limit]:
                name = str(rec.get("enterprise_name") or rec.get("name_of_enterprise") or rec.get("name") or "").strip()
                if name:
                    leads.append({"business_name": name[:150], "phone": "", "email": "", "website": "",
                                  "city": city, "niche": niche, "source": "opendata"})
    except Exception as e:
        return {"source": "opendata", "error": str(e)[:120], "leads": leads}
    return {"source": "opendata", "leads": leads}


async def enrich_missing_emails(limit: int = 8) -> dict[str, Any]:
    """Store ke website-wale prospects jinka email nahi — email_finder waterfall
    (site-extract → pattern → MX). Kabhi raise nahi."""
    found = 0
    tried = 0
    try:
        from app.platform import email_finder, prospector

        for r in prospector._read_all():
            if tried >= limit:
                break
            if r.get("email") or not r.get("website"):
                continue
            tried += 1
            try:
                res = await email_finder.find(r["website"], owner_name=str(r.get("business_name") or ""))
                best = (res.get("emails") or [None])[0] if isinstance(res, dict) else None
                email = best.get("email") if isinstance(best, dict) else best
                if email:
                    prospector.set_prospect_fields(r["id"], {"email": str(email)[:200]})
                    found += 1
            except Exception:
                continue
            await asyncio.sleep(0.3)
    except Exception as e:
        return {"tried": tried, "found": found, "error": str(e)[:120]}
    return {"tried": tried, "found": found}


SOURCES = {
    "prospector": _src_prospector,
    "websearch": _src_websearch,
    "opendata": _src_opendata,
}


# ---------------------------------------------------------------- pipeline


async def run_harvest(
    niche: str = "", city: str = "", limit: int = 10, sources: list[str] | None = None
) -> dict[str, Any]:
    """Multi-source harvest: collect → validate → dedupe → persist → rescore.
    Gated sources bina key inert. Kabhi raise nahi."""
    try:
        if not niche or not city:
            from app.marketing.channel_experiments import _pick_niche_city

            n2, c2 = _pick_niche_city()
            niche = niche or n2
            city = city or c2

        keys = [s for s in (sources or list(SOURCES.keys())) if s in SOURCES]
        results = await asyncio.gather(*(SOURCES[s](niche, city, limit) for s in keys), return_exceptions=True)

        known_phones, known_emails = _existing_keys()
        new = 0
        skipped = 0
        per_source: dict[str, Any] = {}
        from app.platform import prospector

        for res in results:
            if isinstance(res, Exception):
                continue
            src = res.get("source", "?")
            per_source[src] = {k: v for k, v in res.items() if k != "leads"}
            src_new = 0
            for lead in res.get("leads") or []:
                phone = _valid_phone(str(lead.get("phone") or ""))
                email = await _valid_email(str(lead.get("email") or ""))
                p10 = phone[-10:] if phone else ""
                if (p10 and p10 in known_phones) or (email and email in known_emails) or (not p10 and not email and not lead.get("business_name")):
                    skipped += 1
                    continue
                name = str(lead.get("business_name") or "Unknown")[:200]
                rec = {
                    "id": str(uuid.uuid4()),
                    "found_at": _now(),
                    "business_name": name,
                    "phone": phone,
                    "address": "",
                    "city": city,
                    "niche": niche,
                    "rating": None,
                    "reviews_count": None,
                    "website": str(lead.get("website") or "")[:300],
                    "has_website": bool(lead.get("website")),
                    "email": email,
                    "source_query": f"harvest:{lead.get('source', '?')}",
                    "pitch": prospector.build_pitch(name, niche, city),
                    "wa_link": "",
                    "google_search_link": "",
                    "status": "ready" if (p10 or email) else "needs_enrich",
                }
                if prospector._append(rec):
                    new += 1
                    src_new += 1
                    if p10:
                        known_phones.add(p10)
                    if email:
                        known_emails.add(email)
            per_source[src]["new"] = src_new

        enr = await enrich_missing_emails(limit=6)

        try:
            from app.platform import lead_scoring

            await lead_scoring.rescore_db(limit=200)
        except Exception:
            pass

        summary = {
            "ok": True, "niche": niche, "city": city, "sources": per_source,
            "new_leads": new, "deduped": skipped, "enrich": enr, "at": _now(),
        }
        _append_run(summary)
        try:
            from app.platform import team

            team.log_event("dev", "lead_harvest", f"{niche}/{city}: +{new} naye leads (dedup {skipped}, enrich {enr.get('found', 0)})")
        except Exception:
            pass
        return summary
    except Exception as e:
        logger.warning(f"[harvester] run failed: {e}")
        return {"ok": False, "error": str(e)[:200]}


async def run_loop_sweep() -> dict[str, Any]:
    """Loop hook (gated LEAD_HARVESTER) — daily prospect job / self_improve se."""
    if not enabled():
        return {"enabled": False}
    return await run_harvest()


def recent_runs(limit: int = 15) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        if os.path.exists(_RUNS):
            with open(_RUNS, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows[-limit:][::-1]


def source_status() -> dict[str, Any]:
    """Kaunse sources armed hain (keys present) — ops visibility."""
    return {
        "enabled_loop": enabled(),
        "prospector": bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()) or "osm-fallback",
        "websearch": bool(os.environ.get("BRAVE_API_KEY", "").strip()),
        "opendata": bool(os.environ.get("DATA_GOV_IN_API_KEY", "").strip()) and bool(os.environ.get("DATA_GOV_RESOURCE_ID", "").strip()),
        "blocked_domains_policy": list(_BLOCKED_DOMAINS[:6]) + ["..."],
    }


__all__ = ["run_harvest", "run_loop_sweep", "enrich_missing_emails", "recent_runs", "source_status", "enabled", "SOURCES"]
