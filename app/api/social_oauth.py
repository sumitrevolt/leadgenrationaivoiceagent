"""app/api/social_oauth.py — Social OAuth start/callback + readiness map.

Meta (Facebook + Instagram): real authorize URL + code→token→vault when
``META_OAUTH_APPROVED=1`` AND ``META_APP_ID`` + ``META_APP_SECRET`` are set.

GBP / LinkedIn / X / YouTube: honest stubs — never fake ``oauth_ready``.
Customer fallback: ``/api/customer/social/accounts/connect`` (manual paste).

Own-brand publish rail remains Postiz; this path stores customer/page tokens
in ``social_engine.vault`` for native Graph adapters when used.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.parse
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.customer_auth import require_customer
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/social/oauth", tags=["Social OAuth"])

_META_PLATFORMS = frozenset({"facebook", "instagram"})
_GRAPH_VERSION = "v21.0"
_STATE_MAX_AGE_S = 600

_ENV_APPROVED_FLAGS = {
    "facebook": "META_OAUTH_APPROVED",
    "instagram": "META_OAUTH_APPROVED",
    "gbp": "GBP_OAUTH_APPROVED",
    "linkedin": "LINKEDIN_OAUTH_APPROVED",
    "x": "X_OAUTH_APPROVED",
    "youtube": "GOOGLE_OAUTH_APPROVED",
}

_REQUIRED_SCOPES = {
    "facebook": ["pages_manage_posts", "pages_read_engagement", "pages_show_list"],
    "instagram": [
        "instagram_content_publish",
        "instagram_basic",
        "pages_show_list",
        "pages_read_engagement",
    ],
    "gbp": ["https://www.googleapis.com/auth/business.manage"],
    "linkedin": ["w_organization_social", "w_member_social", "r_liteprofile"],
    "x": ["tweet.write", "tweet.read", "users.read"],
    "youtube": ["https://www.googleapis.com/auth/youtube.upload"],
}

_OWNER_ACTION_NOTES = {
    "facebook": (
        "Own-brand Meta app can post without Advanced Access. Arbitrary customer "
        "Pages still need Meta App Review (Advanced Access). Console: "
        "developers.facebook.com/apps → Facebook Login → Valid OAuth Redirect URIs."
    ),
    "instagram": (
        "Same Meta app as Facebook — instagram_content_publish. Own-brand IG OK; "
        "customer IG accounts need App Review Advanced Access."
    ),
    "gbp": (
        "Google Business Profile API access request required. Google Cloud Console "
        "→ APIs & Services → Business Profile API."
    ),
    "linkedin": (
        "LinkedIn Marketing / Community Management API partner access required. "
        "linkedin.com/developers → Products."
    ),
    "x": ("X API v2 free tier is READ-ONLY. `tweet.write` needs Basic ($100/mo) or Pro tier."),
    "youtube": (
        "OAuth2 consent screen must be published + verified. Domain verification + "
        "video upload consent = Google trust review."
    ),
}


def _oauth_approved(platform: str) -> bool:
    flag = _ENV_APPROVED_FLAGS.get(platform)
    if not flag:
        return False
    return (os.getenv(flag) or "").strip().lower() in ("1", "true", "yes")


def _meta_creds() -> tuple[str, str]:
    # Prefer META_*; accept FACEBOOK_* aliases (Postiz deploy already stores these).
    app_id = (os.getenv("META_APP_ID") or "").strip() or (
        os.getenv("FACEBOOK_APP_ID") or ""
    ).strip()
    app_secret = (os.getenv("META_APP_SECRET") or "").strip() or (
        os.getenv("FACEBOOK_APP_SECRET") or ""
    ).strip()
    return app_id, app_secret


def _authorize_wired(platform: str) -> bool:
    """True only when this platform's authorize + exchange path can actually run."""
    p = (platform or "").strip().lower()
    if p in _META_PLATFORMS:
        app_id, app_secret = _meta_creds()
        return bool(app_id and app_secret)
    return False


def _public_base() -> str:
    try:
        from app.config import settings

        base = (getattr(settings, "public_base_url", None) or "").strip()
    except Exception:
        base = ""
    if not base:
        base = (os.getenv("PUBLIC_BASE_URL") or "https://leadsgenai.in").strip()
    return base.rstrip("/")


def _redirect_uri(platform: str) -> str:
    return f"{_public_base()}/api/social/oauth/{platform}/callback"


def _state_secret() -> bytes:
    key = (
        (os.getenv("SOCIAL_TOKEN_KEY") or "").strip()
        or (os.getenv("SECRET_KEY") or "").strip()
        or (os.getenv("SECRET") or "").strip()
        or "dev-insecure-social-oauth"
    )
    return key.encode("utf-8")


def _safe_return_to(return_to: str) -> str:
    rt = (return_to or "").strip()
    if not rt or not rt.startswith("/") or rt.startswith("//"):
        return "/app/office"
    if any(c in rt for c in ("\n", "\r", "\\")):
        return "/app/office"
    return rt[:500]


def _sign_state(
    *,
    client_id: str,
    platform: str,
    return_to: str,
) -> str:
    payload = {
        "c": (client_id or "").strip(),
        "p": (platform or "").strip().lower(),
        "r": _safe_return_to(return_to),
        "n": secrets.token_hex(8),
        "t": int(time.time()),
    }
    raw = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    sig = hmac.new(_state_secret(), raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def _verify_state(state: str, platform: str) -> dict[str, Any] | None:
    try:
        raw, sig = (state or "").rsplit(".", 1)
        if not raw or not sig:
            return None
        good = hmac.new(_state_secret(), raw.encode(), hashlib.sha256).hexdigest()[:32]
        if not hmac.compare_digest(sig, good):
            return None
        pad = "=" * (-len(raw) % 4)
        payload = json.loads(base64.urlsafe_b64decode((raw + pad).encode()).decode())
        if str(payload.get("p") or "") != (platform or "").strip().lower():
            return None
        ts = int(payload.get("t") or 0)
        if abs(int(time.time()) - ts) > _STATE_MAX_AGE_S:
            return None
        cid = str(payload.get("c") or "").strip()
        if not cid:
            return None
        return {
            "client_id": cid,
            "platform": str(payload.get("p") or ""),
            "return_to": _safe_return_to(str(payload.get("r") or "")),
        }
    except Exception:
        return None


def _http_get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    """HTTPS GET JSON — Meta Graph only (scheme/host pinned)."""
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != "graph.facebook.com":
            return {"error": {"message": "url_not_allowlisted"}}
        import httpx

        with httpx.Client(timeout=timeout) as cx:
            resp = cx.get(url, headers={"Accept": "application/json"})
            data = resp.json() if resp.content else {}
            if not isinstance(data, dict):
                return {"error": {"message": "non_object_response"}}
            if resp.status_code >= 400 and "error" not in data:
                data = {"error": {"message": f"http_{resp.status_code}", "code": resp.status_code}}
            return data
    except Exception as e:
        return {"error": {"message": str(e)[:200]}}


def _build_meta_authorize_url(platform: str, client_id: str, return_to: str) -> str:
    app_id, _ = _meta_creds()
    state = _sign_state(client_id=client_id, platform=platform, return_to=return_to)
    scopes = ",".join(_REQUIRED_SCOPES.get(platform, []))
    qs = urllib.parse.urlencode(
        {
            "client_id": app_id,
            "redirect_uri": _redirect_uri(platform),
            "state": state,
            "scope": scopes,
            "response_type": "code",
        }
    )
    return f"https://www.facebook.com/{_GRAPH_VERSION}/dialog/oauth?{qs}"


def _exchange_meta_code(platform: str, code: str) -> dict[str, Any]:
    """code → short-lived → long-lived user token → page (+ optional IG) token.

    Returns {ok, token, account_ref, meta, expires_at, error}.
    """
    app_id, app_secret = _meta_creds()
    if not app_id or not app_secret:
        return {"ok": False, "error": "meta_creds_missing"}

    redirect = _redirect_uri(platform)
    short_url = (
        f"https://graph.facebook.com/{_GRAPH_VERSION}/oauth/access_token?"
        + urllib.parse.urlencode(
            {
                "client_id": app_id,
                "client_secret": app_secret,
                "redirect_uri": redirect,
                "code": code,
            }
        )
    )
    short = _http_get_json(short_url)
    short_token = str(short.get("access_token") or "").strip()
    if not short_token:
        err = (short.get("error") or {}) if isinstance(short.get("error"), dict) else {}
        return {
            "ok": False,
            "error": str(err.get("message") or short.get("error") or "code_exchange_failed")[:200],
        }

    long_url = (
        f"https://graph.facebook.com/{_GRAPH_VERSION}/oauth/access_token?"
        + urllib.parse.urlencode(
            {
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": short_token,
            }
        )
    )
    long = _http_get_json(long_url)
    user_token = str(long.get("access_token") or short_token).strip()
    expires_in = int(long.get("expires_in") or short.get("expires_in") or 0)

    pages_url = (
        f"https://graph.facebook.com/{_GRAPH_VERSION}/me/accounts?"
        + urllib.parse.urlencode(
            {
                "fields": "id,name,access_token,instagram_business_account",
                "access_token": user_token,
            }
        )
    )
    pages_data = _http_get_json(pages_url)
    pages = pages_data.get("data") if isinstance(pages_data.get("data"), list) else []
    if not pages:
        err = (pages_data.get("error") or {}) if isinstance(pages_data.get("error"), dict) else {}
        return {
            "ok": False,
            "error": str(err.get("message") or "no_pages_returned")[:200],
        }

    page = pages[0] if isinstance(pages[0], dict) else {}
    page_token = str(page.get("access_token") or "").strip()
    page_id = str(page.get("id") or "").strip()
    page_name = str(page.get("name") or "").strip()
    if not page_token or not page_id:
        return {"ok": False, "error": "page_token_missing"}

    ig = (
        page.get("instagram_business_account")
        if isinstance(page.get("instagram_business_account"), dict)
        else {}
    )
    ig_id = str((ig or {}).get("id") or "").strip()

    expires_at = ""
    if expires_in > 0:
        from datetime import datetime, timezone

        expires_at = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat()

    if platform == "instagram":
        if not ig_id:
            return {
                "ok": False,
                "error": "no_instagram_business_account_on_page",
                "meta": {"page_id": page_id, "page_name": page_name},
            }
        return {
            "ok": True,
            "token": page_token,
            "account_ref": ig_id,
            "expires_at": expires_at,
            "meta": {
                "page_id": page_id,
                "page_name": page_name,
                "instagram_account_id": ig_id,
                "token_kind": "page_token_for_ig",
                "source": "meta_oauth",
            },
        }

    return {
        "ok": True,
        "token": page_token,
        "account_ref": page_id,
        "expires_at": expires_at,
        "meta": {
            "page_id": page_id,
            "page_name": page_name,
            "instagram_account_id": ig_id,
            "token_kind": "page_access_token",
            "source": "meta_oauth",
        },
    }


class OAuthStateResponse(BaseModel):
    platform: str
    oauth_ready: bool
    external_blocker: str
    fallback: str
    scopes_required: list[str]


@router.get("/state")
def oauth_state_all(_client_id: str = Depends(require_customer)) -> dict:
    """Per-platform OAuth readiness — customer wizard Connect button truth."""
    out = []
    for platform in _ENV_APPROVED_FLAGS.keys():
        env_ok = _oauth_approved(platform)
        wired = _authorize_wired(platform)
        ready = bool(env_ok and wired)
        if ready:
            blocker = ""
        elif env_ok and not wired:
            blocker = (
                "meta_app_credentials_missing"
                if platform in _META_PLATFORMS
                else "oauth_authorize_url_not_wired"
            )
        else:
            blocker = _OWNER_ACTION_NOTES.get(platform, "")
        out.append(
            {
                "platform": platform,
                "oauth_ready": ready,
                "env_approved": env_ok,
                "authorize_wired": wired,
                "external_blocker": blocker,
                "fallback": "oauth_v1" if ready else "manual_paste",
                "scopes_required": _REQUIRED_SCOPES.get(platform, []),
            }
        )
    return {"ok": True, "platforms": out}


@router.get("/{platform}/start")
def oauth_start(
    platform: str,
    return_to: str = Query("", max_length=500),
    client_id: str = Depends(require_customer),
) -> dict:
    """Customer initiates OAuth. Meta returns authorize_url when armed; else honest stub."""
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

    if p in _META_PLATFORMS and _authorize_wired(p):
        url = _build_meta_authorize_url(p, client_id, return_to)
        return {
            "ok": True,
            "status": "ready",
            "platform": p,
            "authorize_url": url,
            "scopes_required": _REQUIRED_SCOPES.get(p, []),
            "return_to": _safe_return_to(return_to),
            "fallback": "manual_paste",
            "fallback_endpoint": "/api/customer/social/accounts/connect",
        }

    reason = (
        "meta_app_credentials_missing" if p in _META_PLATFORMS else "oauth_authorize_url_not_wired"
    )
    return {
        "ok": False,
        "status": "activation_pending",
        "reason": reason,
        "message": (
            "Platform env-approved, lekin authorize URL / token exchange abhi activate "
            "nahi — manual paste use karo."
            if reason == "oauth_authorize_url_not_wired"
            else "META_APP_ID / META_APP_SECRET unset — console se set karo, phir OAuth ready hoga."
        ),
        "platform": p,
        "scopes_required": _REQUIRED_SCOPES.get(p, []),
        "fallback": "manual_paste",
        "fallback_endpoint": "/api/customer/social/accounts/connect",
        "return_to": _safe_return_to(return_to),
    }


@router.get("/{platform}/callback")
def oauth_callback(
    platform: str,
    code: str = Query("", max_length=2048),
    state: str = Query("", max_length=2048),
) -> dict:
    """Provider redirects here with ?code=…&state=…. Meta: exchange + vault.put."""
    p = str(platform or "").strip().lower()
    if p not in _ENV_APPROVED_FLAGS:
        raise HTTPException(status_code=400, detail="invalid platform")
    if not _oauth_approved(p):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "oauth_not_available",
                "message": _OWNER_ACTION_NOTES.get(p, ""),
            },
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing code / state")

    if p not in _META_PLATFORMS or not _authorize_wired(p):
        return {
            "ok": False,
            "status": "activation_pending",
            "message": "OAuth callback wiring is scaffolded but not yet activated.",
            "note": "Fill code->token exchange + vault.put(client_id, platform, token, expires_at) here.",
        }

    verified = _verify_state(state, p)
    if not verified:
        raise HTTPException(status_code=400, detail={"error": "invalid_or_expired_state"})

    exchanged = _exchange_meta_code(p, code)
    if not exchanged.get("ok"):
        logger.warning(
            "[social_oauth] meta exchange failed platform=%s err=%s", p, exchanged.get("error")
        )
        raise HTTPException(
            status_code=400,
            detail={
                "error": "token_exchange_failed",
                "message": str(exchanged.get("error") or "exchange_failed")[:200],
            },
        )

    try:
        from app.social_engine import vault
    except Exception as e:
        logger.warning("[social_oauth] vault import failed: %s", e)
        raise HTTPException(status_code=500, detail={"error": "vault_unavailable"}) from e

    stored = vault.put(
        verified["client_id"],
        p,
        str(exchanged["token"]),
        account_ref=str(exchanged.get("account_ref") or ""),
        meta=dict(exchanged.get("meta") or {}),
        expires_at=str(exchanged.get("expires_at") or ""),
    )
    if not stored:
        raise HTTPException(status_code=500, detail={"error": "vault_put_failed"})

    return {
        "ok": True,
        "status": "connected",
        "platform": p,
        "client_id": verified["client_id"],
        "account_ref": exchanged.get("account_ref") or "",
        "return_to": verified.get("return_to") or "/app/office",
        "meta": {
            "page_id": (exchanged.get("meta") or {}).get("page_id"),
            "page_name": (exchanged.get("meta") or {}).get("page_name"),
            "instagram_account_id": (exchanged.get("meta") or {}).get("instagram_account_id"),
        },
    }
