"""Udyam-PRIMARY lead pipeline (user/council 2026-06-28).

Enterprise-grade, third-party-directory-FREE acquisition:

  PRIMARY   data.gov.in Udyam/MSME registry (legal govt open-data, crores of
            registered Indian businesses) -> seed names + city + category.
  ENRICH-1  Google Maps (search "<name> <city>") -> phone, website, address, rating.
  ENRICH-2  company website crawl (email_finder waterfall) -> deliverable email.
  -> dedup (phone/email) -> persist (prospector) -> scoring + voice/email/WA outreach.

WHY this shape (user's call): Udyam = the authoritative, maintainable, legal base;
Maps + the business's own website are public-data ENRICHMENT on top — so the pipeline
never depends on scraping third-party directories (Justdial/IndiaMart are ToS-blocked).

CONTRACT (enterprise gate):
- Flag-gated `UDYAM_PIPELINE=1` (default OFF). Inert without it AND without the
  data.gov.in key (`DATA_GOV_IN_API_KEY` + `DATA_GOV_RESOURCE_ID`) -> Udyam seed empty.
- Never-raise; free-stack; reuses harvester dedup + prospector persist (no duplicate logic).
- Cost-bounded: caller passes `limit`; Maps lookups = 1 per seed (capped by limit).
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def enabled() -> bool:
    return os.environ.get("UDYAM_PIPELINE", "0").strip().lower() in ("1", "true", "yes", "on")


async def _udyam_seeds(city: str, limit: int) -> list[dict[str, Any]]:
    """PRIMARY source: Udyam/MSME names from data.gov.in (reuses harvester's opendata)."""
    try:
        from app.platform import lead_harvester

        res = await lead_harvester._src_opendata("", city, limit)
        return list(res.get("leads") or [])
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[udyam] seed fetch failed: %s", e)
        return []


async def _maps_enrich(name: str, city: str) -> dict[str, Any]:
    """ENRICH-1: Google Maps lookup by name+city -> phone/website/address/rating/email."""
    out: dict[str, Any] = {}
    try:
        from app.lead_scraper.google_maps import GoogleMapsClient

        client = GoogleMapsClient()
        res = await client.search_businesses(name, city, max_results=1)
        if res:
            bl = res[0]
            out = {
                "phone": str(getattr(bl, "phone", "") or ""),
                "website": str(getattr(bl, "website", "") or ""),
                "address": str(getattr(bl, "address", "") or ""),
                "rating": getattr(bl, "rating", None),
                "email": str(getattr(bl, "email", "") or ""),
            }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[udyam] maps enrich skip (%s): %s", name[:40], e)
    return out


async def _web_enrich(website: str) -> str:
    """ENRICH-2: company website crawl -> first deliverable email (MX-verified)."""
    try:
        if not website:
            return ""
        from app.platform import email_finder

        ef = await email_finder.find(website)
        for em in ef.get("emails") or []:
            e = str((em or {}).get("email") or "").strip()
            if e:
                return e
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[udyam] web enrich skip: %s", e)
    return ""


async def run(limit: int = 20, city: str = "", niche: str = "general") -> dict[str, Any]:
    """Udyam-primary -> Maps+website enrich -> dedup -> persist. Never raises.

    Returns {enabled, seeds, enriched, new, skipped}. `niche` tags the persisted leads
    (Udyam category is coarse; the harvester/scoring re-classifies downstream)."""
    if not enabled():
        return {"enabled": False}
    seeds = await _udyam_seeds(city, limit)
    if not seeds:
        return {"enabled": True, "seeds": 0, "new": 0, "note": "no Udyam seeds (set DATA_GOV_IN_API_KEY + DATA_GOV_RESOURCE_ID)"}

    out = {"enabled": True, "seeds": len(seeds), "enriched": 0, "new": 0, "skipped": 0}
    try:
        from app.platform import lead_harvester, prospector

        known_phones, known_emails = lead_harvester._existing_keys()
        for s in seeds:
            name = str(s.get("business_name") or "").strip()
            c = str(s.get("city") or city or "").strip()
            if not name:
                out["skipped"] += 1
                continue

            m = await _maps_enrich(name, c)
            if m:
                out["enriched"] += 1
            phone = lead_harvester._valid_phone(str(m.get("phone") or ""))
            website = str(m.get("website") or "")
            email = await lead_harvester._valid_email(str(m.get("email") or ""))
            if website and not email:
                email = await lead_harvester._valid_email(await _web_enrich(website))

            p10 = phone[-10:] if phone else ""
            if (p10 and p10 in known_phones) or (email and email in known_emails):
                out["skipped"] += 1
                continue

            rec = {
                "id": str(uuid.uuid4()),
                "found_at": lead_harvester._now(),
                "business_name": name[:200],
                "phone": phone,
                "email": email,
                "website": website,
                "address": str(m.get("address") or ""),
                "city": c,
                "niche": niche,
                "rating": m.get("rating"),
                "reviews_count": None,
                "source": "udyam_enriched",
                "status": "new",
                "lead_score": 0,
            }
            if prospector._append(rec):
                out["new"] += 1
                if p10:
                    known_phones.add(p10)
                if email:
                    known_emails.add(email)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[udyam] run failed: %s", e)
        out["error"] = str(e)[:120]
    return out


__all__ = ["run", "enabled"]
