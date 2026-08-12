"""IndiaMART official Lead Manager (CRM Pull) API — the SELLER's OWN buyer-leads.

This is the LEGAL way to get IndiaMART data: IndiaMART's own official API hands a
registered seller their inbound buyer inquiries (name/mobile/email/query/product). It is
NOT scraping of IndiaMART listings (that stays ToS-blocked). Key-gated INDIAMART_CRM_KEY
(IndiaMART seller account -> Lead Manager -> CRM/Push API). Inert + never-raise without it.

Pulls -> dedup (phone/email) -> persist (prospector) -> scoring/outreach downstream.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PULL = "https://mapi.indiamart.com/wservce/crm/crmListing/v2/"


def enabled() -> bool:
    return bool(os.environ.get("INDIAMART_CRM_KEY", "").strip())


async def fetch_and_persist(days: int = 1, niche: str = "general") -> dict[str, Any]:
    """Pull the seller's IndiaMART leads from the last `days` and persist new ones.
    Returns {enabled, total, new, skipped}. Never raises."""
    key = os.environ.get("INDIAMART_CRM_KEY", "").strip()
    if not key:
        return {"enabled": False, "note": "set INDIAMART_CRM_KEY (seller Lead Manager API)"}
    out = {"enabled": True, "total": 0, "new": 0, "skipped": 0}
    try:
        import httpx

        # IndiaMART expects dd-Mon-YYYY HH:MM:SS
        end = datetime.now()
        start = end - timedelta(days=max(1, int(days)))
        fmt = "%d-%b-%Y %H:%M:%S"
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.get(
                _PULL,
                params={
                    "glusr_crm_key": key,
                    "start_time": start.strftime(fmt),
                    "end_time": end.strftime(fmt),
                },
            )
            if r.status_code != 200:
                return {**out, "error": f"indiamart {r.status_code}"}
            body = r.json() or {}
        rows = body.get("RESPONSE") or []
        if not isinstance(rows, list):
            return {**out, "error": str(body.get("MESSAGE") or "no RESPONSE")}
        out["total"] = len(rows)

        import uuid

        from app.platform import lead_harvester, prospector

        known_phones, known_emails = lead_harvester._existing_keys()
        for row in rows:
            name = str(row.get("SENDER_NAME") or row.get("SENDER_COMPANY") or "").strip()
            phone = lead_harvester._valid_phone(str(row.get("SENDER_MOBILE") or ""))
            email = await lead_harvester._valid_email(str(row.get("SENDER_EMAIL") or ""))
            if not name and not phone and not email:
                out["skipped"] += 1
                continue
            p10 = phone[-10:] if phone else ""
            if (p10 and p10 in known_phones) or (email and email in known_emails):
                out["skipped"] += 1
                continue
            rec = {
                "id": str(uuid.uuid4()),
                "found_at": lead_harvester._now(),
                "business_name": (name or "IndiaMART buyer")[:200],
                "phone": phone,
                "email": email,
                "website": "",
                "address": str(row.get("SENDER_CITY") or ""),
                "city": str(row.get("SENDER_CITY") or ""),
                "niche": niche,
                "query": str(row.get("QUERY_MESSAGE") or row.get("QUERY_PRODUCT_NAME") or "")[:300],
                "source": "indiamart_api",
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
        logger.warning("[indiamart] fetch failed: %s", e)
        out["error"] = str(e)[:120]
    return out


__all__ = ["fetch_and_persist", "enabled"]
