"""Zoho CRM integration — Indian SMB ka #1 CRM (native sync, FREE tier friendly).

OAuth2 refresh-token flow, **India DC default** (accounts.zoho.in / zohoapis.in).
hubspot.py ke ZohoCRMIntegration placeholder ka REAL implementation (alag module —
placeholder untouched, ye use karo).

GATED: creds bina = inert (enabled False, sab methods None/False). NEVER raises.
Creds: per-client override (client record `crm` dict) YA global settings/env
(`ZOHO_CLIENT_ID`/`ZOHO_CLIENT_SECRET`/`ZOHO_REFRESH_TOKEN`, optional `ZOHO_DC=in|com|eu`).

Setup (client ke liye, one-time ~5 min):
  1. api-console.zoho.in → Self Client → client_id+secret
  2. Generate Code (scope: ZohoCRM.modules.ALL) → exchange for refresh_token
  3. POST /api/growth/crm/config se save karo

Use:
    z = ZohoCRM(client_id=..., client_secret=..., refresh_token=...)
    lead_id = await z.upsert_lead({"business_name": "...", "phone": "..."})
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_TIMEOUT = 20.0

# DC → (accounts host, api host). India-first.
_DCS = {
    "in": ("https://accounts.zoho.in", "https://www.zohoapis.in"),
    "com": ("https://accounts.zoho.com", "https://www.zohoapis.com"),
    "eu": ("https://accounts.zoho.eu", "https://www.zohoapis.eu"),
}


class ZohoCRM:
    """Zoho CRM v2 client — upsert Lead + note + call log. Defensive everywhere."""

    def __init__(
        self,
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        dc: str = "",
    ):
        import os

        from app.config import settings

        self.client_id = (client_id or getattr(settings, "zoho_client_id", "") or "").strip()
        self.client_secret = (
            client_secret or getattr(settings, "zoho_client_secret", "") or ""
        ).strip()
        self.refresh_token = (
            refresh_token or getattr(settings, "zoho_refresh_token", "") or ""
        ).strip()
        dc = (dc or os.environ.get("ZOHO_DC", "in") or "in").strip().lower()
        self.accounts_base, self.api_base = _DCS.get(dc, _DCS["in"])
        self._access_token = ""
        self._token_expiry = 0.0

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    async def _token(self) -> str:
        """Access token (cached ~50 min). '' on failure — caller graceful."""
        if not self.enabled:
            return ""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(
                    f"{self.accounts_base}/oauth/v2/token",
                    params={
                        "refresh_token": self.refresh_token,
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "grant_type": "refresh_token",
                    },
                )
                data = r.json() if r.status_code == 200 else {}
                tok = str(data.get("access_token") or "")
                if tok:
                    self._access_token = tok
                    self._token_expiry = time.time() + int(data.get("expires_in") or 3600) - 600
                    return tok
                logger.info("zoho token refresh failed: %s %s", r.status_code, str(data)[:150])
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("zoho token error: %s", exc)
        return ""

    async def test_connection(self) -> dict[str, Any]:
        """Creds valid? (token refresh hi asli test hai)."""
        if not self.enabled:
            return {"ok": False, "error": "creds missing"}
        tok = await self._token()
        return {
            "ok": bool(tok),
            "dc": self.api_base,
            "error": "" if tok else "token refresh failed (creds/DC check karo)",
        }

    async def upsert_lead(self, lead: dict[str, Any], note: str = "") -> str | None:
        """Lead upsert (Phone/Email duplicate-check). Returns Zoho record id ya None.

        lead keys: business_name/company_name, contact_name, phone, email, city,
        niche, source, score (0-100), description.
        """
        tok = await self._token()
        if not tok:
            return None
        business = str(
            lead.get("business_name")
            or lead.get("company_name")
            or lead.get("business")
            or "Unknown Business"
        )
        contact = str(lead.get("contact_name") or lead.get("contact") or "").strip()
        record: dict[str, Any] = {
            # Zoho Leads me Last_Name REQUIRED — contact nahi to business name.
            "Last_Name": (contact.split()[-1] if contact else business)[:80] or "Lead",
            "Company": business[:100],
            "Phone": str(lead.get("phone") or "")[:30],
            "Email": str(lead.get("email") or "")[:100],
            "City": str(lead.get("city") or "")[:50],
            "Lead_Source": str(lead.get("source") or "LeadGen AI")[:100],
            "Description": str(note or lead.get("description") or lead.get("qualification") or "")[
                :2000
            ],
        }
        if contact and len(contact.split()) > 1:
            record["First_Name"] = " ".join(contact.split()[:-1])[:40]
        industry = str(lead.get("niche") or lead.get("category") or "").strip()
        if industry:
            record["Industry"] = industry.replace("_", " ").title()[:100]
        try:
            score = int(float(lead.get("score") or lead.get("lead_score") or 0))
            if score:
                record["Rating"] = "Active" if score >= 60 else "Acquired"
        except Exception:
            pass
        record = {k: v for k, v in record.items() if v}
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(
                    f"{self.api_base}/crm/v2/Leads/upsert",
                    headers={"Authorization": f"Zoho-oauthtoken {tok}"},
                    json={"data": [record], "duplicate_check_fields": ["Phone", "Email"]},
                )
                if r.status_code not in (200, 201, 202):
                    logger.info("zoho upsert %s: %s", r.status_code, r.text[:200])
                    return None
                rows = r.json().get("data") or [{}]
                details = rows[0].get("details") or {}
                rid = str(details.get("id") or "")
                if rid:
                    logger.info("zoho lead upserted: %s (%s)", rid, rows[0].get("action", ""))
                return rid or None
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("zoho upsert error: %s", exc)
            return None

    async def add_note(self, lead_id: str, title: str, content: str) -> bool:
        """Lead pe note (call summary / qualification detail)."""
        tok = await self._token()
        if not tok or not lead_id:
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(
                    f"{self.api_base}/crm/v2/Notes",
                    headers={"Authorization": f"Zoho-oauthtoken {tok}"},
                    json={
                        "data": [
                            {
                                "Note_Title": (title or "LeadGen AI")[:120],
                                "Note_Content": (content or "")[:32000],
                                "Parent_Id": lead_id,
                                "se_module": "Leads",
                            }
                        ]
                    },
                )
                return r.status_code in (200, 201, 202)
        except Exception as exc:  # pragma: no cover - defensive
            logger.info("zoho note error: %s", exc)
            return False


__all__ = ["ZohoCRM"]
