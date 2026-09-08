"""app/api/social_oauth.py — Social OAuth + Telegram bot readiness.

Wired when env-approved AND credentials present:
  - Meta facebook/instagram (META_APP_* / FACEBOOK_*)
  - LinkedIn (LINKEDIN_CLIENT_*)
  - YouTube (YOUTUBE_CLIENT_* / GOOGLE_CLIENT_*)

Honest stubs (never fake oauth_ready): GBP, X.

Telegram is NOT OAuth — bot_token readiness is reported on /state only.
Do not re-add Telegram to social_engine default_providers (ban-risk).

Own-brand publish rail remains Postiz.
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
from datetime import datetime, timezone
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
_HTTP_ALLOW_HOSTS = frozenset(
    {
        "graph.facebook.com",
        "www.linkedin.com",
        "api.linkedin.com",
        "accounts.google.com",
        "oauth2.googleapis.com",
        "www.googleapis.com",
    }
)

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
    "linkedin": ["w_organization_social", "w_member_social", "r_liteprofile", "openid", "profile"],
    "x": ["tweet.write", "tweet.read", "users.read"],
    "youtube": ["https://www.googleapis.com/auth/youtube.upload"],
}

_OWNER_ACTION_NOTES = {
    "facebook": (
        "Own-brand Meta app can post without Advanced Access. Arbitrary customer "
        "Pages still need Meta App Review (Advanced Access)."
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
        "LinkedIn Marketing / Community Management API partner access required for "
        "org posting. Console: linkedin.com/developers → Auth → Redirect URLs."
    ),
    "x": ("X API v2 free tier is READ-ONLY. `tweet.write` needs Basic ($100/mo) or Pro tier."),
    "youtube": (
        "OAuth2 consent screen must allow youtube.upload. Redirect URI: "
        "/api/social/oauth/youtube/callback"
    ),
}


def _oauth_approved(platform: str) -> bool:
    flag = _ENV_APPROVED_FLAGS.get(platform)
    if not flag:
        return False
    return (os.getenv(flag) or "").strip().lower() in ("1", "true", "yes")


def _meta_creds() -> tuple[str, str]:
    app_id = (os.getenv("META_APP_ID") or "").strip() or (
        os.getenv("FACEBOOK_APP_ID") or ""
    ).strip()
    app_secret = (os.getenv("META_APP_SECRET") or "").strip() or (
        os.getenv("FACEBOOK_APP_SECRET") or ""
    ).strip()
    return app_id, app_secret


def _linkedin_creds() -> tuple[str, str]:
    return (
        (os.getenv("LINKEDIN_CLIENT_ID") or "").strip(),
        (os.getenv("LINKEDIN_CLIENT_SECRET") or "").strip(),
    )


def _youtube_creds() -> tuple[str, str]:
    cid = (os.getenv("YOUTUBE_CLIENT_ID") or "").strip() or (
        os.getenv("GOOGLE_CLIENT_ID") or ""
    ).strip()
    secret = (os.getenv("YOUTUBE_CLIENT_SECRET") or "").strip() or (
        os.getenv("GOOGLE_CLIENT_SECRET") or ""
    ).strip()
    return cid, secret


def _telegram_bot_ready() -> bool:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    return bool(token and chat)


def _authorize_wired(platform: str) -> bool:
    p = (platform or "").strip().lower()
    if p in _META_PLATFORMS:
        app_id, app_secret = _meta_creds()
        return bool(app_id and app_secret)
    if p == "linkedin":
        cid, secret = _linkedin_creds()
        return bool(cid and secret)
    if p == "youtube":
        cid, secret = _youtube_creds()
        return bool(cid and secret)
    return False


def _creds_missing_reason(platform: str) -> str:
    if platform in _META_PLATFORMS:
        return "meta_app_credentials_missing"
    if platform == "linkedin":
        return "linkedin_client_credentials_missing"
    if platform == "youtube":
        return "youtube_client_credentials_missing"
    return "oauth_authorize_url_not_wired"


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


def _sign_state(*, client_id: str, platform: str, return_to: str) -> str:
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


def _http_json(
    method: str,
    url: str,
    *,
    data: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in _HTTP_ALLOW_HOSTS:
            return {"error": {"message": "url_not_allowlisted"}}
        import httpx

        hdrs = {"Accept": "application/json", **(headers or {})}
        with httpx.Client(timeout=timeout) as cx:
            if method.upper() == "POST":
                resp = cx.post(url, data=data or {}, headers=hdrs)
            else:
                resp = cx.get(url, headers=hdrs)
            body = resp.json() if resp.content else {}
            if not isinstance(body, dict):
                return {"error": {"message": "non_object_response"}}
            if resp.status_code >= 400 and "error" not in body:
                body = {
                    "error": {
                        "message": f"http_{resp.status_code}",
                        "code": resp.status_code,
                        "body": body,
                    }
                }
            return body
    except Exception as e:
        return {"error": {"message": str(e)[:200]}}


def _http_get_json(url: str, timeout: float = 30.0) -> dict[str, Any]:
    return _http_json("GET", url, timeout=timeout)


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


def _build_linkedin_authorize_url(client_id: str, return_to: str) -> str:
    cid, _ = _linkedin_creds()
    state = _sign_state(client_id=client_id, platform="linkedin", return_to=return_to)
    scopes = " ".join(_REQUIRED_SCOPES["linkedin"])
    qs = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": cid,
            "redirect_uri": _redirect_uri("linkedin"),
            "state": state,
            "scope": scopes,
        }
    )
    return f"https://www.linkedin.com/oauth/v2/authorization?{qs}"


def _build_youtube_authorize_url(client_id: str, return_to: str) -> str:
    cid, _ = _youtube_creds()
    state = _sign_state(client_id=client_id, platform="youtube", return_to=return_to)
    scopes = " ".join(_REQUIRED_SCOPES["youtube"])
    qs = urllib.parse.urlencode(
        {
            "client_id": cid,
            "redirect_uri": _redirect_uri("youtube"),
            "response_type": "code",
            "scope": scopes,
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
    )
    return f"https://accounts.google.com/o/oauth2/v2/auth?{qs}"


def _exchange_meta_code(platform: str, code: str) -> dict[str, Any]:
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
        return {"ok": False, "error": str(err.get("message") or "no_pages_returned")[:200]}

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


def _exchange_linkedin_code(code: str) -> dict[str, Any]:
    cid, secret = _linkedin_creds()
    if not cid or not secret:
        return {"ok": False, "error": "linkedin_creds_missing"}
    token_data = _http_json(
        "POST",
        "https://www.linkedin.com/oauth/v2/accessToken",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": _redirect_uri("linkedin"),
            "client_id": cid,
            "client_secret": secret,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access = str(token_data.get("access_token") or "").strip()
    if not access:
        err = token_data.get("error_description") or token_data.get("error") or token_data
        return {"ok": False, "error": str(err)[:200]}

    expires_in = int(token_data.get("expires_in") or 0)
    expires_at = ""
    if expires_in > 0:
        expires_at = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat()

    me = _http_json(
        "GET",
        "https://api.linkedin.com/v2/userinfo",
        headers={"Authorization": f"Bearer {access}"},
    )
    if me.get("error") or not me.get("sub"):
        # Fallback older people/~ endpoint shape
        me = _http_json(
            "GET",
            "https://api.linkedin.com/v2/me",
            headers={"Authorization": f"Bearer {access}"},
        )
    account_ref = str(me.get("sub") or me.get("id") or "").strip()
    if account_ref and not account_ref.startswith("urn:"):
        account_ref = f"urn:li:person:{account_ref}"

    return {
        "ok": True,
        "token": access,
        "account_ref": account_ref or "linkedin_user",
        "expires_at": expires_at,
        "meta": {
            "token_kind": "linkedin_user_token",
            "source": "linkedin_oauth",
            "has_refresh": bool(token_data.get("refresh_token")),
            "name": str(me.get("name") or ""),
        },
    }


def _exchange_youtube_code(code: str) -> dict[str, Any]:
    cid, secret = _youtube_creds()
    if not cid or not secret:
        return {"ok": False, "error": "youtube_creds_missing"}
    token_data = _http_json(
        "POST",
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": cid,
            "client_secret": secret,
            "redirect_uri": _redirect_uri("youtube"),
            "grant_type": "authorization_code",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    access = str(token_data.get("access_token") or "").strip()
    refresh = str(token_data.get("refresh_token") or "").strip()
    if not access:
        err = token_data.get("error_description") or token_data.get("error") or token_data
        return {"ok": False, "error": str(err)[:200]}

    expires_in = int(token_data.get("expires_in") or 0)
    expires_at = ""
    if expires_in > 0:
        expires_at = datetime.fromtimestamp(time.time() + expires_in, tz=timezone.utc).isoformat()

    # Prefer storing refresh token when present (upload sessions need refresh).
    store_token = refresh or access
    channels = _http_json(
        "GET",
        "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true",
        headers={"Authorization": f"Bearer {access}"},
    )
    items = channels.get("items") if isinstance(channels.get("items"), list) else []
    ch0 = items[0] if items and isinstance(items[0], dict) else {}
    account_ref = str(ch0.get("id") or "").strip() or "youtube_channel"
    title = ""
    snip = ch0.get("snippet") if isinstance(ch0.get("snippet"), dict) else {}
    title = str((snip or {}).get("title") or "")

    return {
        "ok": True,
        "token": store_token,
        "account_ref": account_ref,
        "expires_at": expires_at,
        "meta": {
            "token_kind": "google_refresh_or_access",
            "source": "youtube_oauth",
            "has_refresh": bool(refresh),
            "channel_title": title,
        },
    }


def _exchange_code(platform: str, code: str) -> dict[str, Any]:
    if platform in _META_PLATFORMS:
        return _exchange_meta_code(platform, code)
    if platform == "linkedin":
        return _exchange_linkedin_code(code)
    if platform == "youtube":
        return _exchange_youtube_code(code)
    return {"ok": False, "error": "platform_not_wired"}


def _build_authorize_url(platform: str, client_id: str, return_to: str) -> str:
    if platform in _META_PLATFORMS:
        return _build_meta_authorize_url(platform, client_id, return_to)
    if platform == "linkedin":
        return _build_linkedin_authorize_url(client_id, return_to)
    if platform == "youtube":
        return _build_youtube_authorize_url(client_id, return_to)
    return ""


class OAuthStateResponse(BaseModel):
    platform: str
    oauth_ready: bool
    external_blocker: str
    fallback: str
    scopes_required: list[str]


@router.get("/state")
def oauth_state_all(_client_id: str = Depends(require_customer)) -> dict:
    """Per-platform OAuth readiness + Telegram bot_ready (non-OAuth)."""
    out = []
    for platform in _ENV_APPROVED_FLAGS.keys():
        env_ok = _oauth_approved(platform)
        wired = _authorize_wired(platform)
        ready = bool(env_ok and wired)
        if ready:
            blocker = ""
        elif env_ok and not wired:
            blocker = _creds_missing_reason(platform)
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

    tg_ready = _telegram_bot_ready()
    out.append(
        {
            "platform": "telegram",
            "oauth_ready": False,
            "bot_ready": tg_ready,
            "env_approved": tg_ready,
            "authorize_wired": False,
            "external_blocker": (
                "" if tg_ready else "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID required (not OAuth)."
            ),
            "fallback": "bot_token",
            "scopes_required": [],
            "note": (
                "Telegram is bot-token based; not in social_engine default_providers "
                "(ban-risk). Own-brand canary uses TELEGRAM_AUTO_PUBLISH."
            ),
        }
    )
    return {"ok": True, "platforms": out}


@router.get("/{platform}/start")
def oauth_start(
    platform: str,
    return_to: str = Query("", max_length=500),
    client_id: str = Depends(require_customer),
) -> dict:
    p = str(platform or "").strip().lower()
    if p == "telegram":
        ready = _telegram_bot_ready()
        return {
            "ok": ready,
            "status": "bot_ready" if ready else "not_available",
            "platform": "telegram",
            "oauth_ready": False,
            "bot_ready": ready,
            "reason": "" if ready else "telegram_bot_credentials_missing",
            "message": (
                "Telegram bot configured (token+chat). Not an OAuth flow."
                if ready
                else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID unset."
            ),
            "fallback": "bot_token",
        }
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

    if _authorize_wired(p):
        url = _build_authorize_url(p, client_id, return_to)
        if url:
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

    reason = _creds_missing_reason(p)
    return {
        "ok": False,
        "status": "activation_pending",
        "reason": reason,
        "message": (
            "Platform env-approved, lekin authorize URL / token exchange abhi activate "
            "nahi — manual paste use karo."
            if reason == "oauth_authorize_url_not_wired"
            else f"{reason} — console/env se set karo."
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

    if not _authorize_wired(p):
        return {
            "ok": False,
            "status": "activation_pending",
            "message": "OAuth callback wiring is scaffolded but not yet activated.",
            "note": "Fill code->token exchange + vault.put(client_id, platform, token, expires_at) here.",
        }

    verified = _verify_state(state, p)
    if not verified:
        raise HTTPException(status_code=400, detail={"error": "invalid_or_expired_state"})

    exchanged = _exchange_code(p, code)
    if not exchanged.get("ok"):
        logger.warning(
            "[social_oauth] exchange failed platform=%s err=%s", p, exchanged.get("error")
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
        "meta": dict(exchanged.get("meta") or {}),
    }
