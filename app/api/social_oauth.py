"""app/api/social_oauth.py — Phase 4 OAuth callback route stubs.

These routes are the customer-facing entry points for the standard OAuth
`Login with X` flow per platform. Today they return an honest `not_available`
response because Meta / LinkedIn / GBP app-review is externally blocked — the
customer's fallback is Loop-social-1's manual-paste flow (`/api/customer/
social/accounts/connect`).

The moment provider approval clears, the flip is a small implementation swap
(state validation, code→token exchange, `vault.put(..., expires_at=…)`). The
stub structure preserves URL shape + state param + PKCE hash slots so
downstream frontend + tests can be written now.

Routes:
  GET  /api/social/oauth/{platform}/start    → returns not-available JSON with
       exact owner action + docs link. When approval clears, this will return
       a signed redirect URL that goes to the provider's consent page.
  GET  /api/social/oauth/{platform}/callback → callback stub. Validates state
       + rejects unknown platform. When approval clears, exchanges code for
       token and vault-puts it.

  GET  /api/social/oauth/state                → per-platform readiness map so
       admin cockpit + customer wizard render honest "review pending" vs
       "OAuth ready" buttons.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.customer_auth import require_customer

router = APIRouter(prefix="/api/social/oauth", tags=["Social OAuth"])

# Per-platform review-status truth table. Flip an env var when approval clears
# and the wizard's Connect button will switch from manual-paste to OAuth
# without any code redeploy needed.
_ENV_APPROVED_FLAGS = {
    "facebook":  "META_OAUTH_APPROVED",
    "instagram": "META_OAUTH_APPROVED",
    "gbp":       "GBP_OAUTH_APPROVED",
    "linkedin":  "LINKEDIN_OAUTH_APPROVED",
    "x":         "X_OAUTH_APPROVED",
    "youtube":   "GOOGLE_OAUTH_APPROVED",
}

# Required scopes documented per platform (verify at activation — providers
# rotate these). This is what the OAuth-start URL will actually request.
_REQUIRED_SCOPES = {
    "facebook":  ["pages_manage_posts", "pages_read_engagement", "pages_show_list"],
    "instagram": ["instagram_content_publish", "instagram_basic", "pages_show_list"],
    "gbp":       ["https://www.googleapis.com/auth/business.manage"],
    "linkedin":  ["w_organization_social", "w_member_social", "r_liteprofile"],
    "x":         ["tweet.write", "tweet.read", "users.read"],
    "youtube":   ["https://www.googleapis.com/auth/youtube.upload"],
}

_OWNER_ACTION_NOTES = {
    "facebook":  "Meta app-review + business verification required. Console: developers.facebook.com/apps → App Review → Permissions and Features.",
    "instagram": "Same Meta app as Facebook — instagram_content_publish scope must be individually reviewed.",
    "gbp":       "Google Business Profile API access request required. Google Cloud Console → APIs & Services → Business Profile API.",
    "linkedin":  "LinkedIn Marketing / Community Management API partner access required. linkedin.com/developers → Products.",
    "x":         "X API v2 free tier is READ-ONLY. `tweet.write` needs Basic ($100/mo) or Pro tier.",
    "youtube":   "OAuth2 consent screen must be published + verified. Domain verification + video upload consent = Google trust review.",
}


def _oauth_approved(platform: str) -> bool:
    flag = _ENV_APPROVED_FLAGS.get(platform)
    if not flag:
        return False
    return (os.getenv(flag) or "").strip().lower() in ("1", "true", "yes")


class OAuthStateResponse(BaseModel):
    platform: str
    oauth_ready: bool
    external_blocker: str
    fallback: str
    scopes_required: list[str]


@router.get("/state")
def oauth_state_all(_client_id: str = Depends(require_customer)) -> dict:
    """Per-platform OAuth readiness — customer wizard consumes this to decide
    Connect button label + tooltip. Never raises.

    ``oauth_ready`` is True ONLY when env-approved AND authorize URL path is
    actually implemented. Today authorize is not wired → always manual_paste
    even if META_OAUTH_APPROVED=1 (honest; matches /start activation_pending).
    """
    # Flip to True only when real authorize_url + code→token exchange ship.
    _authorize_wired = False
    out = []
    for platform in _ENV_APPROVED_FLAGS.keys():
        env_ok = _oauth_approved(platform)
        ready = bool(env_ok and _authorize_wired)
        out.append({
            "platform": platform,
            "oauth_ready": ready,
            "env_approved": env_ok,
            "external_blocker": (
                "" if ready
                else (
                    "oauth_authorize_url_not_wired"
                    if env_ok
                    else _OWNER_ACTION_NOTES.get(platform, "")
                )
            ),
            "fallback": "oauth_v1" if ready else "manual_paste",
            "scopes_required": _REQUIRED_SCOPES.get(platform, []),
        })
    return {"ok": True, "platforms": out}


@router.get("/{platform}/start")
def oauth_start(
    platform: str,
    return_to: str = Query("", max_length=500),
    client_id: str = Depends(require_customer),
) -> dict:
    """Customer initiates OAuth. STUB: returns not_available if platform not
    approved; the frontend then falls back to the manual-paste dialog. When
    the platform's approval env flag flips, this route will 302 to the real
    provider consent URL."""
    p = str(platform or "").strip().lower()
    if p not in _ENV_APPROVED_FLAGS:
        raise HTTPException(status_code=400, detail={"error": "invalid_platform"})
    if not _oauth_approved(p):
        return {
            "ok": False,
            "status": "not_available",
            "reason": "provider_review_pending",
            "message": _OWNER_ACTION_NOTES.get(p, "External approval pending"),
            "scopes_required": _REQUIRED_SCOPES.get(p, []),
            "fallback": "manual_paste",
            "fallback_endpoint": "/api/customer/social/accounts/connect",
        }
    # Env flag may be ON (owner approved Meta/etc.) but authorize URL + code→token
    # exchange are NOT wired yet. Never return ok:True with empty authorize_url —
    # that is fake-ready (UI would think OAuth works). Honest path = manual paste.
    return {
        "ok": False,
        "status": "activation_pending",
        "reason": "oauth_authorize_url_not_wired",
        "message": (
            "Platform env-approved, lekin authorize URL / token exchange abhi activate "
            "nahi — manual paste use karo."
        ),
        "platform": p,
        "scopes_required": _REQUIRED_SCOPES.get(p, []),
        "fallback": "manual_paste",
        "fallback_endpoint": "/api/customer/social/accounts/connect",
        "return_to": return_to or "/app/office",
    }


@router.get("/{platform}/callback")
def oauth_callback(
    platform: str,
    code: str = Query("", max_length=2048),
    state: str = Query("", max_length=200),
) -> dict:
    """Provider redirects here with ?code=…&state=…. STUB: rejects if platform
    not approved (403), refuses missing state/code (400). Real implementation
    (post-approval) exchanges code for token and vault.put(..., expires_at)."""
    p = str(platform or "").strip().lower()
    if p not in _ENV_APPROVED_FLAGS:
        raise HTTPException(status_code=400, detail="invalid platform")
    if not _oauth_approved(p):
        raise HTTPException(status_code=403, detail={
            "error": "oauth_not_available",
            "message": _OWNER_ACTION_NOTES.get(p, ""),
        })
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code / state")
    return {
        "ok": False,
        "status": "activation_pending",
        "message": "OAuth callback wiring is scaffolded but not yet activated.",
        "note": "Fill code->token exchange + vault.put(client_id, platform, token, expires_at) here.",
    }
