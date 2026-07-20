"""Auth for Owner Copilot — super-admin JWT and/or OpenClaw gateway token.

Inbound model (preferred):
  OpenClaw Gateway → LeadGen /api/owner-copilot/*
  LeadGen does NOT depend on OpenClaw outbound for core runtime.

Auth modes:
  1. Human browser — canonical super-admin only (same rule as require_super_admin)
  2. OPENCLAW_API_TOKEN bearer (machine gateway) — token + allowlisted source IP

Module-RBAC / normal admin grants do NOT imply Owner Copilot authority.
Bearer token alone is insufficient from untrusted network sources.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request

from app.api.auth_deps import get_current_user_optional
from app.integrations.openclaw.audit import audit_openclaw
from app.models.user import User, UserRole


@dataclass
class CopilotActor:
    """Normalized actor for Owner Copilot commands."""

    id: str
    kind: str  # "admin" | "openclaw_gateway"
    email: str | None = None
    role: str | None = None
    source_ip: str | None = None

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


def gateway_allowed_ips() -> frozenset[str]:
    """Explicit source allowlist for token-only Gateway auth.

    Unset → loopback only (safe default).
    Empty string → empty set (fail closed for machine auth).
    """
    raw = os.getenv("OPENCLAW_GATEWAY_ALLOWED_IPS")
    if raw is None:
        return frozenset({"127.0.0.1", "::1"})
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    return frozenset(parts)


def peer_host(request: Request) -> str:
    """Socket peer only. Do NOT trust X-Forwarded-For for Gateway machine auth."""
    client = getattr(request, "client", None)
    host = getattr(client, "host", None) if client is not None else None
    return str(host or "").strip()


def gateway_source_allowed(request: Request) -> bool:
    allowed = gateway_allowed_ips()
    if not allowed:
        return False
    host = peer_host(request)
    if not host:
        return False
    return host in allowed


def _is_super_admin(user: User) -> bool:
    """Reuse canonical super-admin rule (UserRole.SUPER_ADMIN) — no RBAC bypass."""
    return getattr(user, "role", None) == UserRole.SUPER_ADMIN


async def require_copilot_actor(
    request: Request,
    authorization: str | None = Header(None),
    x_openclaw_gateway_token: str | None = Header(None, alias="X-OpenClaw-Gateway-Token"),
    user: User | None = Depends(get_current_user_optional),
) -> CopilotActor:
    """Super-admin session OR gateway token from allowlisted peer. Fail-closed."""
    source_ip = peer_host(request)

    token_ok = False
    if gateway_token_configured():
        # Accept either Authorization bearer (if it matches gateway token) or dedicated header.
        # When Authorization is a JWT, dedicated header carries the gateway token.
        token_ok = validate_gateway_token(x_openclaw_gateway_token) or (
            validate_gateway_token(authorization)
            and not _looks_like_jwt(extract_bearer(authorization))
        )

    if user is not None:
        role_name = str(
            getattr(getattr(user, "role", None), "value", None) or getattr(user, "role", "") or ""
        )
        if not _is_super_admin(user):
            audit_openclaw(
                str(getattr(user, "id", "") or "unknown"),
                "auth_denied_human",
                detail={
                    "status": "DENIED",
                    "actor_kind": "admin",
                    "role": role_name,
                    "source_ip": source_ip or None,
                    "reason": "super_admin_required",
                },
            )
            raise HTTPException(status_code=403, detail="Super admin access required")
        actor = CopilotActor(
            id=str(getattr(user, "id", "") or "admin"),
            kind="admin",
            email=str(getattr(user, "email", None) or "") or None,
            role="super_admin",
            source_ip=source_ip or None,
        )
        audit_openclaw(
            actor.label(),
            "auth_ok_human",
            detail={
                "status": "OK",
                "actor_kind": actor.kind,
                "role": actor.role,
                "source_ip": source_ip or None,
            },
        )
        return actor

    if token_ok:
        if not gateway_source_allowed(request):
            audit_openclaw(
                "openclaw-gateway",
                "auth_denied_gateway_source",
                detail={
                    "status": "DENIED",
                    "actor_kind": "openclaw_gateway",
                    "source_ip": source_ip or None,
                    "reason": "gateway_source_not_allowlisted",
                    # Never log token. Allowlist size only.
                    "allowlist_size": len(gateway_allowed_ips()),
                },
            )
            raise HTTPException(
                status_code=403,
                detail="OpenClaw gateway source not allowlisted",
            )
        actor = CopilotActor(
            id="openclaw-gateway",
            kind="openclaw_gateway",
            email=None,
            role="gateway",
            source_ip=source_ip or None,
        )
        audit_openclaw(
            actor.id,
            "auth_ok_gateway",
            detail={
                "status": "OK",
                "actor_kind": actor.kind,
                "role": actor.role,
                "source_ip": source_ip or None,
            },
        )
        return actor

    if gateway_token_configured():
        audit_openclaw(
            "anonymous",
            "auth_denied",
            detail={
                "status": "DENIED",
                "actor_kind": "anonymous",
                "source_ip": source_ip or None,
                "reason": "missing_or_invalid_credentials",
            },
        )
        raise HTTPException(
            status_code=401,
            detail="Super-admin JWT or valid OpenClaw gateway token required",
        )
    audit_openclaw(
        "anonymous",
        "auth_denied",
        detail={
            "status": "DENIED",
            "actor_kind": "anonymous",
            "source_ip": source_ip or None,
            "reason": "super_admin_required",
        },
    )
    raise HTTPException(status_code=401, detail="Super admin authentication required")


def _looks_like_jwt(token: str) -> bool:
    parts = token.split(".")
    return len(parts) == 3 and all(parts)


# Back-compat exports used by older imports
def validate_gateway_token_optional(provided: str | None) -> bool:
    """If token unset, True (admin JWT is enough). If set, must match."""
    if not gateway_token_configured():
        return True
    return validate_gateway_token(provided)
