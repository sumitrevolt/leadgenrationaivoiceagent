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


async def _maps_enrich(name: str, city: str, pincode: str = "") -> dict[str, Any]:
    """ENRICH-1: Google Maps lookup (name+city+PINCODE for higher match-rate) ->
    phone/website/address/rating/email. OSM (free, keyless) fallback when Maps finds no
    contact, so coverage doesn't depend on a Maps match alone."""
    out: dict[str, Any] = {}
    try:
        from app.lead_scraper.google_maps import GoogleMapsClient

        client = GoogleMapsClient()
        q = " ".join(x for x in (name, city, pincode) if x)
        res = await client.search_businesses(q, city, max_results=1)
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
    if not (out.get("phone") or out.get("website")):  # OSM fallback (keyless)
        try:
            import asyncio

            from app.platform.prospector import _osm_search

            rows = await asyncio.to_thread(_osm_search, name, city, 1)
            if rows:
                r0 = rows[0]
                out["phone"] = out.get("phone") or str(r0.get("phone") or "")
                out["website"] = out.get("website") or str(r0.get("website") or "")
                out["address"] = out.get("address") or str(r0.get("address") or "")
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("[udyam] osm fallback skip: %s", e)
    return out


async def _web_enrich(website: str) -> dict[str, str]:
    """ENRICH-2: company website crawl -> {email, phone} (find_contacts). SSRF-guarded
    (only fetch a public-IP host, redirects off). Caller MX-verifies the email."""
    out = {"email": "", "phone": ""}
    try:
        if not website:
            return out
        import re

        import httpx

        from app.lead_scraper.web_extract import find_contacts
        from app.marketing.website_auditor import _resolve_is_public

        d = re.sub(r"^https?://", "", str(website)).split("/")[0].strip()
        if not d or not _resolve_is_public(d):
            return out
        async with httpx.AsyncClient(
            follow_redirects=False, headers={"User-Agent": "Mozilla/5.0"}
        ) as client:
            r = await client.get(f"https://{d}", timeout=10.0)
            if r.status_code == 200:
                info = find_contacts(r.text) or {}
                emails = info.get("emails") or []
                phones = info.get("phones") or []
                if emails:
                    out["email"] = str(emails[0]).lower()
                if phones:
                    out["phone"] = str(phones[0])
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[udyam] web enrich skip: %s", e)
    return out


async def run(limit: int = 20, city: str = "", niche: str = "general") -> dict[str, Any]:
    """Udyam-primary -> Maps+website enrich -> dedup -> persist. Never raises.

    Returns {enabled, seeds, enriched, new, skipped}. `niche` tags the persisted leads
    (Udyam category is coarse; the harvester/scoring re-classifies downstream)."""
    if not enabled():
        return {"enabled": False}
    seeds = await _udyam_seeds(city, limit)
    if not seeds:
        return {
            "enabled": True,
            "seeds": 0,
            "new": 0,
            "note": "no Udyam seeds (set DATA_GOV_IN_API_KEY + DATA_GOV_RESOURCE_ID)",
        }

    out = {"enabled": True, "seeds": len(seeds), "enriched": 0, "new": 0, "skipped": 0}
    try:
        from app.niches import classify_from_text
        from app.platform import lead_harvester, prospector

        known_phones, known_emails = lead_harvester._existing_keys()
        try:
            from app.integrations import opencorporates

            _oc_on = opencorporates.enabled()
        except Exception:
            _oc_on = False
        for s in seeds:
            name = str(s.get("business_name") or "").strip()
            c = str(s.get("city") or city or "").strip()
            if not name:
                out["skipped"] += 1
                continue
            pincode = str(s.get("pincode") or "").strip()
            # classify the RIGHT niche from Udyam MajorActivity + name -> accurate scoring
            # + pitch (was tagging every lead 'general').
            lead_niche = classify_from_text(
                f"{s.get('major_activity') or ''} {name}", default=niche
            )

            m = await _maps_enrich(name, c, pincode)
            if m.get("phone") or m.get("website"):
                out["enriched"] += 1
            phone = lead_harvester._valid_phone(str(m.get("phone") or ""))
            website = str(m.get("website") or "")
            email = await lead_harvester._valid_email(str(m.get("email") or ""))
            # website crawl fills any still-missing email/phone
            if website and (not email or not phone):
                wc = await _web_enrich(website)
                if not email:
                    email = await lead_harvester._valid_email(str(wc.get("email") or ""))
                if not phone:
                    phone = lead_harvester._valid_phone(str(wc.get("phone") or ""))

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
                "pincode": pincode,
                "niche": lead_niche,
                "rating": m.get("rating"),
                "reviews_count": None,
                "source": "udyam_enriched",
                # State-machine fix (2026-07-25): hamesha "new" likhna in rows ko
                # PERMANENT black hole banata tha — koi job "new" ko kabhi promote
                # nahi karta aur outreach sirf "ready" padhta hai (prod: 1,736 "new"
                # rows stuck). Ab harvester ke ingest semantics mirror karo:
                # contact mila = ready, warna needs_enrich (enrich sweep target).
                "status": "ready" if (p10 or email) else "needs_enrich",
                "lead_score": 0,
            }
            if _oc_on:  # OpenCorporates registry enrich (CIN/status) — adds B2B signal
                try:
                    from app.integrations import opencorporates

                    co = await opencorporates.enrich(name)
                    rec.update({k: v for k, v in co.items() if v})
                except Exception:
                    pass
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
