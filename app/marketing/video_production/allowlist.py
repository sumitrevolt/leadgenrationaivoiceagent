"""Own-brand allowlist for Stage 2 canary — LeadGen tenants only."""

from __future__ import annotations

from typing import Any

# Must stay aligned with postiz_publish._OWN_BRAND_IDS.
OWN_BRAND_CLIENT_IDS = frozenset({"leadgenai-self", "leadgen-ai"})


def is_own_brand_client_id(client_id: str) -> bool:
    return str(client_id or "").strip().lower() in OWN_BRAND_CLIENT_IDS


def assert_own_brand_allowlist(client_id: str) -> dict[str, Any]:
    """When VIDEO_OWN_BRAND_ENABLED=1, only allowlisted own-brand tenants pass.

    When the flag is OFF, this is a no-op (legacy paths unchanged).
    """
    from app.marketing.video_production import flags

    if not flags.own_brand_enabled():
        return {"ok": True, "skipped": True}
    cid = str(client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id_required"}
    if not is_own_brand_client_id(cid):
        return {
            "ok": False,
            "error": "own_brand_allowlist_denied",
            "client_id": cid,
            "allowed": sorted(OWN_BRAND_CLIENT_IDS),
        }
    return {"ok": True, "client_id": cid}


__all__ = [
    "OWN_BRAND_CLIENT_IDS",
    "assert_own_brand_allowlist",
    "is_own_brand_client_id",
]
