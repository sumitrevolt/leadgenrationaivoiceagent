"""Auth for Owner Copilot — admin JWT and/or OpenClaw gateway token.

Inbound model (preferred):
  OpenClaw Gateway → LeadGen /api/owner-copilot/*
  LeadGen does NOT depend on OpenClaw outbound for core runtime.

Auth modes:
  1. Admin JWT (browser / human) — require_admin
  2. OPENCLAW_API_TOKEN bearer (machine gateway) — when token configured
  3. Both — if token configured, gateway must also present matching token
     when calling with JWT (defense in depth for machine misuse)

If OPENCLAW_API_TOKEN is unset, admin JWT alone is enough (local/dev).
If token is set, machine clients may authenticate with token only.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, Request

from app.api.auth_deps import get_current_user_optional, require_admin
from app.models.user import User


@dataclass
class CopilotActor:
    """Normalized actor for Owner Copilot commands."""

    id: str
    kind: str  # "admin" | "openclaw_gateway"
    email: str | None = None

    def label(self) -> str:
        if self.email:
            return self.email
        return self.id


def gateway_token_configured() -> bool:
    return bool((os.getenv("OPENCLAW_API_TOKEN") or "").strip())


def validate_gateway_token(provided: str | None) -> bool:
    """Constant-time compare. Never logs the token."""
    expected = (os.getenv("OPENCLAW_API_TOKEN") or "").strip()
    if not expected:
        return False
    got = (provided or "").strip()
    if got.lower().startswith("bearer "):
        got = got[7:].strip()
    if not got:
        return False
    return hmac.compare_digest(got, expected)


def extract_bearer(authorization: str | None) -> str:
    got = (authorization or "").strip()
    if got.lower().startswith("bearer "):
        return got[7:].strip()
    return got


async def require_copilot_actor(
    request: Request,
    authorization: str | None = Header(None),
    x_openclaw_gateway_token: str | None = Header(None, alias="X-OpenClaw-Gateway-Token"),
    user: User | None = Depends(get_current_user_optional),
) -> CopilotActor:
    """Admin session OR configured OpenClaw gateway token. Fail-closed."""
    token_ok = False
    if gateway_token_configured():
        # Accept either Authorization bearer (if it matches gateway token) or dedicated header.
        # When Authorization is a JWT, dedicated header carries the gateway token.
        token_ok = validate_gateway_token(x_openclaw_gateway_token) or (
            validate_gateway_token(authorization)
            and not _looks_like_jwt(extract_bearer(authorization))
        )

    if user is not None:
        # Human/admin path — must pass admin gate.
        if not getattr(user, "can_access_admin", lambda: False)():
            # Mirror require_admin module-grant path lightly.
            try:
                from app.platform import rbac

                if not rbac.member_can_access(user, str(request.url.path)):
                    raise HTTPException(status_code=403, detail="Admin access required")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=403, detail="Admin access required")
        # If gateway token is configured, machine-spoofing via stolen JWT alone is still
        # allowed for admins (human UI). Token is required only for pure machine auth.
        return CopilotActor(
            id=str(getattr(user, "id", "") or "admin"),
            kind="admin",
            email=str(getattr(user, "email", None) or "") or None,
        )

    if token_ok:
        return CopilotActor(id="openclaw-gateway", kind="openclaw_gateway", email=None)

    if gateway_token_configured():
        raise HTTPException(
            status_code=401,
            detail="Admin JWT or valid OpenClaw gateway token required",
        )
    raise HTTPException(status_code=401, detail="Admin authentication required")


def _looks_like_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


# Back-compat exports used by older imports
def validate_gateway_token_optional(provided: str | None) -> bool:
    """If token unset, True (admin JWT is enough). If set, must match."""
    if not gateway_token_configured():
        return True
    return validate_gateway_token(provided)
