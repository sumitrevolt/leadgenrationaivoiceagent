"""Tier-1 governance — centralized server-side audit for consequential admin actions.

Writes an ``AuditLog`` row capturing full request metadata (request_id, user_agent,
source IP), actor identity + role, tenant/target scope, before/after state (redacted),
result/status, error reason and the idempotency key. Runs on its OWN db session so it
never interferes with the caller's transaction.

FAIL POLICY (explicit, per Tier-1 spec):
  These are POST-ACTION audits — the side effect has already happened by the time we
  record it, so failing the HTTP request on an audit-write error would NOT undo the
  action and would only harm availability. Therefore the default policy is
  **FAIL-OPEN-BUT-LOUD**: on audit-write failure we log.error + emit a best-effort ops
  alert (observable), and return False. Callers that audit an INTENT *before* executing
  a high-risk action may pass ``fail_closed=True`` to raise instead (write-ahead).

Server-side only — never depends on frontend JavaScript. Sensitive keys are redacted
before persistence so secrets never land in the audit trail.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Substrings that mark a value as sensitive → redacted before persistence.
_SENSITIVE = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "totp",
    "otp",
    "dsn",
    "private_key",
    "access_token",
    "refresh_token",
    "cookie",
    "session",
    "bearer",
)


def _is_sensitive(key: Any) -> bool:
    k = str(key).lower()
    return any(s in k for s in _SENSITIVE)


def _redact(obj: Any, _depth: int = 0) -> Any:
    """Recursively redact sensitive keys and cap size so the audit row stays bounded."""
    if _depth > 6:
        return "…"
    if isinstance(obj, dict):
        return {
            k: ("***REDACTED***" if _is_sensitive(k) else _redact(v, _depth + 1))
            for k, v in obj.items()
        }
    if isinstance(obj, list | tuple):
        return [_redact(v, _depth + 1) for v in list(obj)[:200]]
    if isinstance(obj, str) and len(obj) > 2000:
        return obj[:2000] + "…"
    return obj


def _actor_fields(actor: Any) -> tuple[str | None, str | None]:
    """Extract (actor_id, actor_role) from a User model or a plain dict."""
    if actor is None:
        return None, None
    aid = getattr(actor, "id", None)
    role = getattr(actor, "role", None)
    if aid is None and isinstance(actor, dict):
        aid = actor.get("id") or actor.get("user_id")
        role = actor.get("role")
    role_str = getattr(role, "value", role)  # UserRole enum → str
    return (str(aid) if aid is not None else None), (
        str(role_str) if role_str is not None else None
    )


def request_meta(request: Any) -> dict:
    """Pull request_id / source IP / user_agent from a FastAPI Request (best-effort)."""
    if request is None:
        return {"request_id": str(uuid.uuid4()), "ip": None, "user_agent": None}
    try:
        headers = request.headers
        rid = (
            headers.get("x-request-id")
            or getattr(getattr(request, "state", None), "request_id", None)
            or str(uuid.uuid4())
        )
        xff = headers.get("x-forwarded-for", "") or ""
        ip = (xff.split(",")[0].strip() if xff else None) or (
            request.client.host if getattr(request, "client", None) else None
        )
        return {
            "request_id": str(rid)[:36],
            "ip": (ip or None),
            "user_agent": headers.get("user-agent"),
        }
    except Exception:
        return {"request_id": str(uuid.uuid4()), "ip": None, "user_agent": None}


def build_audit_row(
    *,
    request: Any,
    actor: Any,
    action: str,
    target_type: str | None = None,
    target_id: Any = None,
    tenant: str | None = None,
    before: Any = None,
    after: Any = None,
    result: str = "success",
    error: Any = None,
    idempotency_key: str | None = None,
    severity: str | None = None,
):
    """Build (but do not persist) an AuditLog row + a small context tuple. Pure/testable."""
    from app.models.user import AuditLog

    meta = request_meta(request)
    actor_id, actor_role = _actor_fields(actor)
    if severity is None:
        severity = {
            "success": "info",
            "rejected": "warning",
            "error": "critical",
            "failed": "critical",
        }.get(result, "info")
    payload = {
        "actor_id": actor_id,  # duplicated in payload so actor survives even if FK is null
        "actor_role": actor_role,
        "tenant": tenant,
        "result": result,
        "error": (str(error)[:500] if error else None),
        "idempotency_key": idempotency_key,
        "after": _redact(after) if after is not None else None,
    }
    row = AuditLog(
        id=str(uuid.uuid4()),
        user_id=actor_id,
        action=action,
        resource_type=(str(target_type)[:50] if target_type else None),
        resource_id=(str(target_id)[:36] if target_id is not None else None),
        old_value=(json.dumps(_redact(before))[:8000] if before is not None else None),
        new_value=json.dumps(payload)[:8000],
        ip_address=(meta.get("ip") or None),
        user_agent=meta.get("user_agent"),
        request_id=meta.get("request_id"),
        created_at=datetime.utcnow(),
        severity=severity,
    )
    return row, (actor_id, actor_role, meta)


async def record_admin_action(
    *,
    request: Any,
    actor: Any,
    action: str,
    target_type: str | None = None,
    target_id: Any = None,
    tenant: str | None = None,
    before: Any = None,
    after: Any = None,
    result: str = "success",
    error: Any = None,
    idempotency_key: str | None = None,
    severity: str | None = None,
    fail_closed: bool = False,
) -> bool:
    """Persist an admin audit record. Returns True on success.

    Never raises on audit failure unless ``fail_closed=True`` (write-ahead use). On
    failure it logs.error + emits a best-effort ops alert so the miss is observable.
    Retries once with a null FK if the actor id is not a persisted user row.
    """
    try:
        row, (actor_id, actor_role, meta) = build_audit_row(
            request=request,
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            tenant=tenant,
            before=before,
            after=after,
            result=result,
            error=error,
            idempotency_key=idempotency_key,
            severity=severity,
        )
    except Exception as e:  # never let audit construction break a request path
        logger.error("AUDIT build failed action=%s err=%s", action, e)
        if fail_closed:
            raise
        return False

    from app.models.base import get_async_session

    for attempt in (1, 2):
        try:
            async with get_async_session() as session:
                session.add(row)
                await session.commit()
            logger.info(
                "AUDIT %s actor=%s role=%s target=%s/%s result=%s rid=%s ip=%s",
                action,
                actor_id,
                actor_role,
                target_type,
                target_id,
                result,
                meta.get("request_id"),
                meta.get("ip"),
            )
            return True
        except Exception as e:
            # First failure is often a FK violation (synthetic admin with no users row).
            # Drop the FK and retry once — actor_id is preserved in new_value payload.
            if attempt == 1 and getattr(row, "user_id", None):
                logger.warning("AUDIT retry without FK action=%s err=%s", action, e)
                try:
                    row.user_id = None
                    continue
                except Exception:
                    pass
            logger.error(
                "AUDIT WRITE FAILED action=%s actor=%s result=%s err=%s (fail_closed=%s)",
                action,
                actor_id,
                result,
                e,
                fail_closed,
            )
            try:
                from app.platform import ops_alerts

                if hasattr(ops_alerts, "notify"):
                    ops_alerts.notify(
                        f"AUDIT WRITE FAILED: {action} by {actor_id} ({result})",
                        severity="critical",
                    )
            except Exception:
                pass
            if fail_closed:
                raise
            return False
    return False
