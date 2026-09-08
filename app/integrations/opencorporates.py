"""OpenCorporates company-registry enrichment (legal, key-gated, inert without token).

Adds CIN / company status / incorporation date / type to a lead by company name, from
the OpenCorporates open API (India jurisdiction). Free tier needs OPENCORPORATES_API_TOKEN
(apply at opencorporates.com/api_accounts/new). Inert + never-raise without it.

Used by the Udyam pipeline (optional layer) to strengthen B2B scoring + pitch with
registry data; the enriched fields persist in the prospect record (prospector._append
keeps arbitrary fields).
"""

from __future__ import annotations

import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_BASE = "https://api.opencorporates.com/v0.4/companies/search"


def enabled() -> bool:
    return bool(os.environ.get("OPENCORPORATES_API_TOKEN", "").strip())


async def enrich(name: str, jurisdiction: str = "in") -> dict[str, Any]:
    """Best company match for `name` -> {cin, company_status, incorporation_date,
    company_type, registry_url}. {} if no token / no match / any error. Never raises."""
    token = os.environ.get("OPENCORPORATES_API_TOKEN", "").strip()
    nm = (name or "").strip()
    if not token or not nm:
        return {}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                _BASE,
                params={
                    "q": nm,
                    "jurisdiction_code": jurisdiction,
                    "api_token": token,
                    "per_page": 1,
                    "order": "score",
                },
            )
            if r.status_code != 200:
                return {}
            comps = ((r.json() or {}).get("results") or {}).get("companies") or []
            if not comps:
                return {}
            co = (comps[0] or {}).get("company") or {}
            return {
                "cin": str(co.get("company_number") or ""),
                "company_status": str(co.get("current_status") or ""),
                "incorporation_date": str(co.get("incorporation_date") or ""),
                "company_type": str(co.get("company_type") or ""),
                "registry_url": str(co.get("opencorporates_url") or ""),
            }
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("[opencorporates] enrich skip (%s): %s", nm[:40], e)
        return {}


__all__ = ["enrich", "enabled"]
