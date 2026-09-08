"""posthog_funnel.py — inquiry → paid funnel insight (PostHog), split by
business_type / niche.

Funnel steps (events, both server-side captured):
  1. ``lead_captured``      — /api/public/inquiry (app/platform/inquiry_hooks.py)
  2. ``payment_activated``  — real UPI activation (app/platform/upi_payments.py)

Dono events ab ``business_type`` + ``niche`` properties carry karte hain, isliye
PostHog funnel ko inme se kisi pe bhi breakdown kiya ja sakta hai — top-converting
niches budget allokation drive karein. Identity: dono steps **phone-keyed**
(distinct_id = inquiry phone / client record phone) — isliye funnel same person
pe inquiry → payment match karta hai (cid-based identities alag persons hote).

Insight creation: ``ensure_insight()`` PostHog API se funnel insight banata hai
(breakdown: business_type). RESTRICTION: insights/query endpoints PRIVATE hain —
sirf personal API key (``phx_``) chalta hai; repo ka ``POSTHOG_API_KEY`` (``phc_``)
ingestion-only hai. Isliye:

  ENV (optional — bina inke INERT, graceful):
    POSTHOG_PERSONAL_API_KEY=phx_xxx   # Project settings -> Personal API keys
    POSTHOG_PROJECT_ID=12345           # optional — unset ho to /api/projects/ se resolve

Never raises — har call graceful no-op/error-dict. Testable: insight_payload()
pure hai; ensure_insight() HTTP path monkeypatch-able.
"""

from __future__ import annotations

import os
from typing import Any

from app.analytics import posthog_client as _ph
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_INSIGHT_NAME = "Inquiry → Paid (by business type)"


# --------------------------------------------------------------------------- #
# Client → funnel properties (payment side ka business_type/niche)
# --------------------------------------------------------------------------- #
def client_business_type(cid: str) -> dict[str, str | None]:
    """Client record se niche + wizard business-type label resolve karo.

    payment_activated capture isi se properties bharata hai (paid side bhi
    split ho sake). Best-effort — client missing ho to {} (funnel fir bhi
    chalta hai, sirf split bina dimension ke)."""
    try:
        from app.marketing.clients_store import get_client

        rec = get_client(cid) or {}
    except Exception:
        return {}
    if not rec:
        return {}
    niche = str(rec.get("niche") or "").strip() or None
    label: str | None = None
    if niche:
        try:
            from app.marketing.onboard_wizard import BUSINESS_TYPES

            for b in BUSINESS_TYPES:
                if b.get("niche") == niche:
                    label = b.get("label")
                    break
        except Exception:
            pass
    return {
        "niche": niche,
        "business_type": label,
        "phone": str(rec.get("phone") or "").strip() or None,
    }


# --------------------------------------------------------------------------- #
# Insight payload (pure — PostHog UI me paste karne ke liye bhi kaam aata hai)
# --------------------------------------------------------------------------- #
def insight_payload() -> dict[str, Any]:
    """FUNNELS insight filters — lead_captured → payment_activated, breakdown by
    business_type (event property). Strict ordering: pehle inquiry, phir payment."""
    return {
        "name": _INSIGHT_NAME,
        "filters": {
            "insight": "FUNNELS",
            "events": [
                {"id": "lead_captured", "type": "events", "order": 0, "name": "lead_captured"},
                {
                    "id": "payment_activated",
                    "type": "events",
                    "order": 1,
                    "name": "payment_activated",
                },
            ],
            "funnel_order_type": "strict",
            "breakdown_type": "event",
            "breakdown": "business_type",
            "breakdown_limit": 20,
            "date_from": "-90d",
            "display": "FunnelViz",
        },
    }


# --------------------------------------------------------------------------- #
# API access (INERT bina phx_ key)
# --------------------------------------------------------------------------- #
def _personal_key() -> str:
    return (os.getenv("POSTHOG_PERSONAL_API_KEY") or "").strip()


def _api_host() -> str:
    host = (_ph._host() or "https://us.i.posthog.com").strip().rstrip("/")
    # UI host api se alag ho sakta hai (us.i.posthog.com = ingestion/api, UI us.posthog.com)
    return host


def _project_id() -> str | None:
    """POSTHOG_PROJECT_ID, warna /api/projects/ se pehla project (phx_ key)."""
    pid = (os.getenv("POSTHOG_PROJECT_ID") or "").strip()
    if pid:
        return pid
    key = _personal_key()
    if not key:
        return None
    try:
        import httpx

        r = httpx.get(
            f"{_api_host()}/api/projects/",
            headers={"Authorization": f"Bearer {key}"},
            timeout=8,
        )
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, dict):
            data = data.get("results") or data.get("projects") or []
        if isinstance(data, list) and data:
            return str(data[0].get("id") or "")
    except Exception as e:  # pragma: no cover - network/parse
        logger.debug("[posthog-funnel] project resolve skipped: %s", e)
    return None


def ensure_insight(create: bool = False) -> dict[str, Any]:
    """Funnel insight ki status + URL. ``create=True`` pe PostHog API se banao.

    Returns: {"status": inert|exists|created|error, "url"?, "note"?}
    - inert: POSTHOG_PERSONAL_API_KEY (phx_) nahi — phc_ key private endpoints
      pe nahi chalta; owner personal key daale ya payload UI me paste kare.
    - error: key hai par API call fail (401/network) — note me reason.
    """
    key = _personal_key()
    if not key:
        return {
            "status": "inert",
            "note": (
                "POSTHOG_PERSONAL_API_KEY (phx_) set nahi — repo ka phc_ key "
                "ingestion-only hai. Key daalo ya insight UI me paste karo "
                "(payload /api/clientops/posthog/funnel?payload=1 se)."
            ),
        }
    pid = _project_id()
    if not pid:
        return {
            "status": "error",
            "note": "project id resolve nahi hua (POSTHOG_PROJECT_ID set karo ya /api/projects/ accessible ho).",
        }
    try:
        import httpx

        base = f"{_api_host()}/api/projects/{pid}"
        headers = {"Authorization": f"Bearer {key}"}
        # Existing search karo — duplicate insights nahi banenge
        r = httpx.get(
            f"{base}/insights/", params={"search": _INSIGHT_NAME}, headers=headers, timeout=8
        )
        if r.status_code == 200:
            data = r.json()
            results = data.get("results") if isinstance(data, dict) else None
            if results:
                first = results[0]
                return {"status": "exists", "url": _insight_url(pid, first)}
        if create:
            r2 = httpx.post(
                f"{base}/insights/", json=insight_payload(), headers=headers, timeout=10
            )
            if r2.status_code in (200, 201):
                created = r2.json()
                return {"status": "created", "url": _insight_url(pid, created)}
            return {"status": "error", "note": f"create failed: HTTP {r2.status_code}"}
        return {"status": "exists_missing", "note": "insight abhi nahi — ?create=1 se banao."}
    except Exception as e:  # pragma: no cover - network
        logger.debug("[posthog-funnel] insight call failed: %s", e)
        return {"status": "error", "note": f"{type(e).__name__}: {str(e)[:120]}"}


def _insight_url(pid: str, insight: dict[str, Any]) -> str:
    short = insight.get("short_id") or insight.get("id") or ""
    host = _api_host().replace(".i.posthog.com", ".posthog.com")
    return f"{host}/project/{pid}/insights/{short}"


__all__ = ["client_business_type", "insight_payload", "ensure_insight"]
