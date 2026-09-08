"""CRM sync — qualified leads ko client ke Zoho/HubSpot me native push.

Indian SMB CRM integration (feature-gap report ka last real gap): voice agent /
funnel se aaya QUALIFIED lead client ke apne CRM me auto dikhe — "apna CRM
chhodna nahi padega" = enterprise-feel selling point.

Design (project pattern: gated / inert-without-creds / never-raise):
  - Per-client config: client record (clients_store) me `crm` dict —
    {"provider": "zoho"|"hubspot", "zoho_client_id":..., "zoho_client_secret":...,
     "zoho_refresh_token":..., "zoho_dc": "in", "hubspot_token":..., "create_deal": false}
  - Global fallback: settings/env (ZOHO_* / HUBSPOT_API_KEY) — apne khud ke CRM ke liye.
  - AUTO hook (call_qualifier qualified=true) GATED `CRM_SYNC=1`; manual API
    endpoints flag-independent (project convention).
  - Har push `data/crm_sync.jsonl` me logged (ops visibility + dedupe).

Use:
    from app.platform import crm_sync
    res = await crm_sync.push_lead(lead, client_id="abc", note="Call summary...")
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

_LOG_PATH = os.path.join("data", "crm_sync.jsonl")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def auto_enabled() -> bool:
    """AUTO hooks ka gate (manual API isse independent)."""
    return os.environ.get("CRM_SYNC", "0").strip().lower() in ("1", "true", "yes")


def _client_crm(client_id: str) -> dict[str, Any]:
    """Client record se `crm` config dict ('' client_id ya absent = {})."""
    if not client_id:
        return {}
    try:
        from app.marketing import clients_store

        client = clients_store.get_client(client_id) or {}
        crm = client.get("crm") or {}
        return crm if isinstance(crm, dict) else {}
    except Exception:
        return {}


def _resolve(client_id: str = "") -> tuple[str, dict[str, Any]]:
    """(provider, creds) — pehle client config, warna global env. ('' = none)."""
    crm = _client_crm(client_id)
    provider = str(crm.get("provider") or "").strip().lower()
    if provider in ("zoho", "hubspot"):
        return provider, crm
    # Global fallback
    try:
        from app.config import settings

        if getattr(settings, "zoho_refresh_token", ""):
            return "zoho", {}
        if getattr(settings, "hubspot_api_key", ""):
            return "hubspot", {}
    except Exception:
        pass
    return "", {}


def _log(rec: dict[str, Any]) -> None:
    try:
        os.makedirs("data", exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # Staff-visibility (2026-07-01): CRM push runs completely invisibly on /app/team
    # today — no STAFF member ever logs it. Attribute to "priya" (CRM Sync Specialist).
    try:
        from app.platform import team

        ok = bool(rec.get("ok"))
        provider = rec.get("provider") or "?"
        ref = rec.get("lead_ref") or ""
        detail = f"{provider}: {ref}" + (
            "" if ok else f" — {rec.get('skipped') or rec.get('error') or 'failed'}"
        )
        team.log_event(
            "priya",
            "crm_synced" if ok else "crm_sync_failed",
            detail,
            status="ok" if ok else "warn",
        )
    except Exception:
        pass


def recent(limit: int = 50) -> list[dict[str, Any]]:
    try:
        if not os.path.exists(_LOG_PATH):
            return []
        rows: list[dict[str, Any]] = []
        with open(_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        return rows[-limit:][::-1]
    except Exception:
        return []


async def push_lead(
    lead: dict[str, Any],
    client_id: str = "",
    note: str = "",
) -> dict[str, Any]:
    """Lead ko resolved CRM me push karo. NEVER raises.

    Returns {"ok", "provider", "record_id"/"contact_id", "skipped"/"error"}.
    """
    lead = lead or {}
    provider, creds = _resolve(client_id)
    base = {
        "ts": _now(),
        "client_id": client_id,
        "provider": provider,
        "lead_ref": str(
            lead.get("business_name") or lead.get("company_name") or lead.get("phone") or "?"
        )[:80],
    }
    if not provider:
        return {
            "ok": False,
            "skipped": "no CRM configured (client crm config ya global ZOHO_*/HUBSPOT_API_KEY)",
        }
    try:
        if provider == "zoho":
            from app.integrations.zoho_crm import ZohoCRM

            z = ZohoCRM(
                client_id=str(creds.get("zoho_client_id") or ""),
                client_secret=str(creds.get("zoho_client_secret") or ""),
                refresh_token=str(creds.get("zoho_refresh_token") or ""),
                dc=str(creds.get("zoho_dc") or ""),
            )
            if not z.enabled:
                return {"ok": False, "provider": provider, "skipped": "zoho creds incomplete"}
            rid = await z.upsert_lead(lead, note=note)
            if rid and note:
                await z.add_note(rid, "LeadGen AI — qualification", note)
            out = {"ok": bool(rid), "provider": provider, "record_id": rid or ""}
            _log({**base, **out})
            return out

        # hubspot
        from app.integrations.hubspot import HubSpotIntegration

        hs = HubSpotIntegration(api_key=str(creds.get("hubspot_token") or "") or None)
        if not hs.headers:
            return {"ok": False, "provider": provider, "skipped": "hubspot token missing"}
        contact_data = {
            "email": lead.get("email", ""),
            "contact_name": lead.get("contact_name") or lead.get("contact") or "",
            "phone": lead.get("phone", ""),
            "company_name": lead.get("business_name")
            or lead.get("company_name")
            or lead.get("business")
            or "",
            "city": lead.get("city", ""),
            "source": lead.get("source", "LeadGen AI"),
            "lead_score": int(float(lead.get("score") or lead.get("lead_score") or 0) or 0),
        }
        try:
            contact_id = await hs.create_contact(contact_data)
        except Exception as ce:
            out = {"ok": False, "provider": provider, "error": str(ce)[:150]}
            _log({**base, **out})
            return out
        if contact_id and note:
            try:
                await hs.add_note(contact_id, note[:5000])
            except Exception:
                pass
        out = {"ok": bool(contact_id), "provider": provider, "contact_id": contact_id or ""}
        _log({**base, **out})
        return out
    except Exception as exc:  # pragma: no cover - defensive
        logger.info("crm push failed: %s", exc)
        out = {"ok": False, "provider": provider, "error": str(exc)[:150]}
        _log({**base, **out})
        return out


async def test_connection(client_id: str = "") -> dict[str, Any]:
    """Configured CRM ke creds verify (kuch create nahi karta — Zoho token / HubSpot search)."""
    provider, creds = _resolve(client_id)
    if not provider:
        return {"ok": False, "provider": "", "error": "no CRM configured"}
    try:
        if provider == "zoho":
            from app.integrations.zoho_crm import ZohoCRM

            z = ZohoCRM(
                client_id=str(creds.get("zoho_client_id") or ""),
                client_secret=str(creds.get("zoho_client_secret") or ""),
                refresh_token=str(creds.get("zoho_refresh_token") or ""),
                dc=str(creds.get("zoho_dc") or ""),
            )
            res = await z.test_connection()
            return {"provider": provider, **res}
        from app.integrations.hubspot import HubSpotIntegration

        hs = HubSpotIntegration(api_key=str(creds.get("hubspot_token") or "") or None)
        if not hs.headers:
            return {"ok": False, "provider": provider, "error": "token missing"}
        found = await hs.find_contact_by_phone("0000000000")  # auth check (None result fine)
        return {
            "ok": True,
            "provider": provider,
            "note": "auth ok" if found is None or found else "auth ok",
        }
    except Exception as exc:
        return {"ok": False, "provider": provider, "error": str(exc)[:150]}


def status(client_id: str = "") -> dict[str, Any]:
    """Armed status — kya configure hai (creds expose NAHI hote)."""
    provider, creds = _resolve(client_id)
    return {
        "auto_sync": auto_enabled(),
        "provider": provider or "none",
        "scope": (
            "client"
            if (client_id and _client_crm(client_id))
            else ("global" if provider else "none")
        ),
        "recent_pushes": len(recent(20)),
    }


def save_client_config(client_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Client record me crm config save (admin API se). Creds client record me
    rehte (data/ gitignored). Returns sanitized status."""
    provider = str(config.get("provider") or "").strip().lower()
    if provider not in ("zoho", "hubspot"):
        return {"ok": False, "error": "provider must be zoho|hubspot"}
    allowed = {
        "provider",
        "zoho_client_id",
        "zoho_client_secret",
        "zoho_refresh_token",
        "zoho_dc",
        "hubspot_token",
        "create_deal",
    }
    clean = {k: v for k, v in (config or {}).items() if k in allowed}
    try:
        from app.marketing import clients_store

        updated = clients_store.update_client(client_id, crm=clean)
        if not updated:
            return {"ok": False, "error": "client not found"}
        return {"ok": True, "client_id": client_id, "provider": provider}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:150]}


async def pull_lead_status(
    *,
    phone: str = "",
    email: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """Bidirectional sync (pull): CRM se lead status read karo. GATED CRM_SYNC_PULL=1."""
    if os.environ.get("CRM_SYNC_PULL", "0").strip().lower() not in ("1", "true", "yes"):
        return {"ok": False, "skipped": "CRM_SYNC_PULL off"}
    provider, creds = _resolve(client_id)
    if not provider:
        return {"ok": False, "skipped": "no CRM configured"}
    try:
        if provider == "hubspot":
            from app.integrations.hubspot import HubSpotIntegration

            hs = HubSpotIntegration(api_key=str(creds.get("hubspot_token") or "") or None)
            if not hs.headers:
                return {"ok": False, "error": "hubspot token missing"}
            found = await hs.find_contact_by_phone(phone) if phone else None
            if not found and email:
                found = await hs.find_contact_by_phone(email)  # best-effort
            out = {
                "ok": bool(found),
                "provider": provider,
                "status": (
                    (found or {}).get("properties", {}).get("hs_lead_status") if found else None
                ),
                "record": found,
            }
            _log({"ts": _now(), "direction": "pull", "client_id": client_id, **out})
            return out
        # Zoho pull — search by phone (best-effort stub until full Zoho search wired)
        return {"ok": False, "provider": provider, "skipped": "zoho pull search not configured"}
    except Exception as exc:
        return {"ok": False, "provider": provider, "error": str(exc)[:150]}


__all__ = [
    "push_lead",
    "pull_lead_status",
    "test_connection",
    "status",
    "save_client_config",
    "recent",
    "auto_enabled",
]
