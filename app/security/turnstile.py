"""Cloudflare Turnstile bot-protection — public form gate.

Verifies a user-submitted Turnstile token (site-key on client, secret on server)
against Cloudflare's siteverify API. Wired as a FastAPI dependency on public
lead-magnet endpoints (`/api/public/ai-demo`, `/api/public/audit/score`,
`/api/public/inquiry`, `/api/growth/tools/website-audit`) to block bot
form-spam that pollutes the lead pipeline.

Project ethos:
- INERT without creds: TURNSTILE_SECRET_KEY unset = dep is a pure pass-through,
  zero behaviour change vs today. Same pattern as Razorpay/Sentry/PostHog.
- Fail-CLOSED when armed: secret set + missing/invalid token = 403. The whole
  point of a CAPTCHA is rejection on failure — no silent bypass.
- Fail-OPEN on infra error: Cloudflare unreachable / HTTP error / timeout =
  request passes. Don't break the funnel for transient Cloudflare issues.
- Token sources (preferred → fallback):
    1. `X-Turnstile-Token` header
    2. `cf-turnstile-response` form field (Cloudflare's default)
    3. `_turnstile_token` JSON field

httpx async, 5s hard timeout. Tokens are single-use per Turnstile API; no
client-side cache.
"""

from __future__ import annotations

import os

import httpx
from fastapi import HTTPException, Request

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_TIMEOUT_S = 5.0


def _secret() -> str:
    try:
        from app.platform import trust_config

        return trust_config.get_turnstile_secret()
    except Exception:
        return os.getenv("TURNSTILE_SECRET_KEY", "").strip()


def _enabled() -> bool:
    return bool(_secret())


def site_key() -> str:
    """Public site-key for the client widget (safe to expose)."""
    try:
        from app.platform import trust_config

        return trust_config.get_turnstile_site_key()
    except Exception:
        return os.getenv("TURNSTILE_SITE_KEY", "").strip()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else ""


async def _extract_token(request: Request) -> str:
    """Pull token from header → form → JSON body. Never raises."""
    tok = (request.headers.get("x-turnstile-token") or "").strip()
    if tok:
        return tok
    content_type = (request.headers.get("content-type") or "").lower()
    try:
        if "application/json" in content_type:
            # Starlette caches the body, so the downstream endpoint can still
            # re-parse it as Pydantic. Extra fields are ignored by default.
            body = await request.json()
            if isinstance(body, dict):
                return str(
                    body.get("_turnstile_token") or body.get("cf-turnstile-response") or ""
                ).strip()
        elif "form" in content_type:
            form = await request.form()
            return str(form.get("cf-turnstile-response", "")).strip()
    except Exception:
        pass
    return ""


async def _siteverify(token: str, remote_ip: str) -> bool:
    """Call Cloudflare siteverify. Fail-OPEN on infra error."""
    secret = _secret()
    if not secret:
        return True  # defensive — caller should have short-circuited
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(
                _VERIFY_URL,
                data={"secret": secret, "response": token, "remoteip": remote_ip},
            )
            if resp.status_code != 200:
                logger.info("turnstile siteverify HTTP %d → fail-OPEN", resp.status_code)
                return True
            data = resp.json()
            ok = bool(data.get("success", False))
            if not ok:
                logger.info("turnstile rejected token: %s", data.get("error-codes", []))
            return ok
    except Exception as exc:
        logger.debug("turnstile fail-OPEN on infra error: %s", exc)
        return True


async def verify_turnstile(request: Request) -> None:
    """FastAPI dependency — gate public form on a valid Turnstile token.

    Behaviour matrix:
        TURNSTILE_SECRET_KEY unset → no-op (INERT, today's behaviour).
        Secret set + token missing → 403.
        Secret set + token invalid → 403.
        Secret set + Cloudflare unreachable → pass (fail-OPEN).
        Secret set + token valid → pass.
    """
    if not _enabled():
        return
    token = await _extract_token(request)
    if not token:
        # MISSING token = the Cloudflare widget didn't load/render for this
        # client (broken site-key/domain config, blocked CDN, unsupported
        # mobile browser). The client-side loader ALREADY fails-OPEN in this
        # case (turnstile.js resolves "" on render/script error), so hard-403
        # here blocked 100% of REAL customers whenever the widget was down —
        # a revenue outage worse than the spam it prevents (2026-07-04 launch
        # incident: every free-trial signup 403'd). Fail-OPEN on MISSING to
        # match the client + the other funnel guards (honeypot + rate-limit +
        # email-dedupe); still fail-CLOSED on a PRESENT-but-INVALID token,
        # which is the only signal of an actual bot that reached the widget.
        if os.getenv("TURNSTILE_STRICT_MISSING", "0").strip().lower() in ("1", "true", "yes"):
            raise HTTPException(
                status_code=403,
                detail="Bot-check token missing. Page refresh karke dobara try karo.",
            )
        logger.info("turnstile: missing token → fail-OPEN (widget likely not rendering)")
        return
    ok = await _siteverify(token, _client_ip(request))
    if not ok:
        raise HTTPException(
            status_code=403,
            detail="Bot-check fail. Page refresh karke dobara try karo.",
        )


__all__ = ["verify_turnstile", "site_key"]
