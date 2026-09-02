"""Reusable integration-health classifier + honest status adapters.

Single source of truth for integration/webhook expiry honesty. The classifier is a
PURE function over an *evidence* dict — it never invents evidence. Real evidence
comes from the social-token vault (`app/social_engine/vault.py`: authoritative
`expires_at` for facebook/instagram/linkedin; soft-`deleted`) and, where present,
operational failure signals. When configuration exists but there is no trustworthy
verification evidence, the status is `unknown` — NOT `healthy`. Env-var presence
alone is never `healthy`.

Statuses: healthy | expiring_soon | expired | revoked | unauthorized |
          transient_failure | unreachable | never_configured | unknown

Safe precedence (a problem always outranks stale success):
  never_configured > revoked > expired > unauthorized > unreachable >
  transient_failure > expiring_soon > healthy > unknown
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

HEALTHY = "healthy"
EXPIRING_SOON = "expiring_soon"
EXPIRED = "expired"
REVOKED = "revoked"
UNAUTHORIZED = "unauthorized"
TRANSIENT_FAILURE = "transient_failure"
UNREACHABLE = "unreachable"
NEVER_CONFIGURED = "never_configured"
UNKNOWN = "unknown"

# Statuses that need the customer/admin to reconnect the integration.
_RECONNECT = {EXPIRED, REVOKED, UNAUTHORIZED, EXPIRING_SOON}
# Statuses that are retryable/temporary (no user reconnect needed).
_RETRYABLE = {TRANSIENT_FAILURE, UNREACHABLE}

# Customer-safe human strings (no provider/technical text).
_CUSTOMER_LABEL = {
    HEALTHY: "Connected",
    EXPIRING_SOON: "Expiring soon",
    EXPIRED: "Reconnect required",
    REVOKED: "Reconnect required",
    UNAUTHORIZED: "Reconnect required",
    TRANSIENT_FAILURE: "Temporarily unavailable",
    UNREACHABLE: "Temporarily unavailable",
    NEVER_CONFIGURED: "Not configured",
    UNKNOWN: "Status unknown",
}
_CUSTOMER_ACTION = {
    HEALTHY: "",
    EXPIRING_SOON: "Reconnect soon to avoid interruption.",
    EXPIRED: "Reconnect this integration to resume.",
    REVOKED: "Reconnect this integration to resume.",
    UNAUTHORIZED: "Reconnect this integration to resume.",
    TRANSIENT_FAILURE: "No action needed — it will retry automatically.",
    UNREACHABLE: "No action needed — please check back shortly.",
    NEVER_CONFIGURED: "Connect this integration to enable it.",
    UNKNOWN: "We could not verify this connection yet.",
}
_ADMIN_ACTION = {
    EXPIRED: "Trigger reconnect/OAuth refresh for this client.",
    REVOKED: "Access revoked provider-side — reconnect required.",
    UNAUTHORIZED: "Auth failing (401/403) — re-authorize credentials.",
    EXPIRING_SOON: "Schedule a proactive reconnect before expiry.",
    TRANSIENT_FAILURE: "Transient provider/server failure — monitor; auto-retry.",
    UNREACHABLE: "Provider unreachable within timeout — check network/provider status.",
    NEVER_CONFIGURED: "Not configured for this client.",
    UNKNOWN: "Configured but unverified — no trustworthy health evidence.",
    HEALTHY: "",
}


def expiring_threshold_days() -> int:
    try:
        return max(1, int(os.getenv("INTEGRATION_EXPIRY_WARN_DAYS", "7")))
    except Exception:
        return 7


def _parse_dt(v) -> datetime | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    try:
        s = str(v).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def classify(
    evidence: dict, *, now: datetime | None = None, threshold_days: int | None = None
) -> dict:
    """Pure classifier. Evidence keys (all optional):
      configured (bool), expires_at (dt|iso|None), revoked (bool),
      auth_failure/unauthorized (bool), transient_failure (bool), unreachable (bool),
      last_success (dt|iso|None), success_window_hours (int, default 48).
    Returns {status, reconnect_required, retry_eligible, expires_at (iso|None)}.
    """
    now = now or datetime.now(timezone.utc)
    thr = threshold_days if threshold_days is not None else expiring_threshold_days()

    def _out(status: str) -> dict:
        return {
            "status": status,
            "reconnect_required": status in _RECONNECT,
            "retry_eligible": status in _RETRYABLE,
        }

    if not evidence.get("configured"):
        return _out(NEVER_CONFIGURED)
    # Hard failures override stale success (safe precedence).
    if evidence.get("revoked"):
        return _out(REVOKED)
    exp = _parse_dt(evidence.get("expires_at"))
    if exp is not None and exp <= now:
        return _out(EXPIRED)
    if evidence.get("auth_failure") or evidence.get("unauthorized"):
        return _out(UNAUTHORIZED)
    if evidence.get("unreachable"):
        return _out(UNREACHABLE)
    if evidence.get("transient_failure"):
        return _out(TRANSIENT_FAILURE)
    if exp is not None and exp <= now + timedelta(days=thr):
        return _out(EXPIRING_SOON)
    # Healthy requires positive evidence: a recent authoritative success OR a stored,
    # non-expired, provider-issued expiry. Configuration presence alone is NOT enough.
    last_success = _parse_dt(evidence.get("last_success"))
    window_h = int(evidence.get("success_window_hours", 48) or 48)
    recent_success = last_success is not None and last_success >= now - timedelta(hours=window_h)
    valid_token = exp is not None  # not expired/expiring (handled above) => future beyond threshold
    if recent_success or valid_token:
        return _out(HEALTHY)
    return _out(UNKNOWN)


# --- real-evidence adapter (social-token vault) -----------------------------
_CUSTOMER_PLATFORMS = ("facebook", "instagram", "linkedin", "gbp", "x", "youtube")
_DISPLAY = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "linkedin": "LinkedIn",
    "gbp": "Google Business Profile",
    "x": "X (Twitter)",
    "youtube": "YouTube",
}


def _vault_evidence(client_id: str, platform: str) -> dict:
    """Build classifier evidence for one client+platform from the token vault.
    Never raises. Only facebook/instagram/linkedin carry an authoritative expiry."""
    try:
        from app.social_engine import vault

        accts = vault.list_accounts(client_id) or []
    except Exception:
        return {"configured": False}
    plat = [a for a in accts if str(a.get("platform")) == platform and not a.get("deleted")]
    if not plat:
        return {"configured": False}
    exp = None
    for a in plat:
        e = a.get("expires_at")
        if e:
            exp = e if exp is None else min(exp, str(e))  # ISO strings sort chronologically
    return {
        "configured": True,
        "expires_at": exp,
        "revoked": False,
        "last_success": None,
        "account_count": len(plat),
    }


def _reference_id(client_id: str, platform: str) -> str:
    import hashlib

    return "int_" + hashlib.sha1(f"{client_id}:{platform}".encode()).hexdigest()[:12]


def customer_integration_statuses(client_id: str) -> list[dict]:
    """Tenant-scoped, customer-SAFE statuses. No client IDs, correlation IDs, tokens,
    provider error text, or expiry timestamps."""
    out = []
    thr = expiring_threshold_days()
    for platform in _CUSTOMER_PLATFORMS:
        ev = _vault_evidence(client_id, platform)
        if not ev.get("configured"):
            continue  # don't advertise every unconnected provider to customers
        c = classify(ev, threshold_days=thr)
        st = c["status"]
        out.append(
            {
                "integration": _DISPLAY.get(platform, platform.title()),
                "status": st,
                "label": _CUSTOMER_LABEL.get(st, "Status unknown"),
                "action_required": c["reconnect_required"],
                "recommended_action": _CUSTOMER_ACTION.get(st, ""),
            }
        )
    return out


def admin_integration_statuses(
    client_id: str | None = None, *, max_clients: int = 200
) -> list[dict]:
    """Admin diagnostics (sanitized). Includes reference id + expiry (when known) +
    recommended action, but never tokens/secrets/raw payloads. Bounded scan."""
    thr = expiring_threshold_days()
    if client_id:
        client_ids = [client_id]
    else:
        client_ids = _bounded_client_ids(max_clients)
    now = datetime.now(timezone.utc).isoformat()
    out = []
    for cid in client_ids:
        for platform in _CUSTOMER_PLATFORMS:
            ev = _vault_evidence(cid, platform)
            if not ev.get("configured"):
                continue
            c = classify(ev, threshold_days=thr)
            st = c["status"]
            out.append(
                {
                    "integration": platform,
                    "display_name": _DISPLAY.get(platform, platform.title()),
                    "client_id": cid,
                    "status": st,
                    "expires_at": ev.get("expires_at") or None,  # only when authoritatively known
                    "last_successful_activity": ev.get("last_success") or None,
                    "last_checked": now,
                    "reconnect_required": c["reconnect_required"],
                    "retry_eligible": c["retry_eligible"],
                    "failure_category": st if st not in (HEALTHY, EXPIRING_SOON) else None,
                    "reference_id": _reference_id(cid, platform),
                    "recommended_action": _ADMIN_ACTION.get(st, ""),
                }
            )
    return out


def _bounded_client_ids(limit: int) -> list[str]:
    """Best-effort bounded list of client IDs that have social integrations."""
    try:
        from app.marketing import clients_store

        ids = [str(c.get("client_id") or c.get("id")) for c in (clients_store.list_clients() or [])]
        return [i for i in ids if i][: max(0, limit)]
    except Exception:
        return []
