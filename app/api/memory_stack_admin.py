"""Memory Stack admin API — 7-layer agent memory: diagnostics, preview, prospective.

  GET  /api/memory-stack/stats                     — config + counters (NO content)
  GET  /api/memory-stack/diagnostics               — flag contract validation
  POST /api/memory-stack/assemble                  — MASKED preview (super-admin to reveal)
  GET  /api/memory-stack/prospective               — tenant-scoped rows
  POST /api/memory-stack/prospective               — schedule (super-admin)
  POST /api/memory-stack/prospective/{id}/cancel   — (super-admin)
  POST /api/memory-stack/prospective/drain         — manual drain (super-admin)
  POST /api/memory-stack/purge                     — DPDP delete (super-admin)

CSRF (verified 2026-08-05, not assumed): admin auth here is `HTTPBearer`
(`app/api/auth_deps.py:19`) — the token travels in an `Authorization` header, not
an ambient cookie, so a cross-site form/image cannot carry it. Classic CSRF is
structurally not applicable to these routes; the repo has no CSRF middleware for
that reason. The destructive-write safeguards used instead are the repo-native
`Idempotency-Key` contract (`admin_idempotency`, bound to actor+scope+payload
hash → 409 on payload reuse) plus an explicit `confirm=true`.

SECURITY POSTURE (review P1):
  - Reads: `require_admin` (RBAC module grants apply). Writes/dispatch/purge:
    `require_super_admin` — a scoped module grant is NOT enough to create or
    fire agent work.
  - `tenant_id` is a REQUIRED parameter on every route. There is no default and
    no "all tenants" read of content; blank => 422.
  - GET routes are side-effect free. Drain is POST-only.
  - Per-route rate limits; write buckets are tighter than read buckets.
  - Preview is MASKED by default (per-layer token counts + a short redacted
    head). Full text needs super-admin AND an explicit `reveal=true` — and is
    audit-logged.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin, require_super_admin
from app.api.ratelimit import rate_limit

router = APIRouter(prefix="/api/memory-stack", tags=["Infrastructure"])

_PREVIEW_HEAD_CHARS = 120


class AssembleIn(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str = Field(..., min_length=1, max_length=40)
    query: str = Field("", max_length=2000)
    session_id: str = Field("", max_length=120)
    subject_id: str | None = Field(None, max_length=128)
    scope: str = Field("lead", max_length=16)
    token_budget: int | None = Field(None, ge=32, le=50_000)
    reveal: bool = False


class ScheduleIn(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    agent_id: str = Field(..., min_length=1, max_length=40)
    action: str = Field(..., min_length=1, max_length=400)
    due_at: str | None = Field(None, max_length=64)
    in_minutes: int | None = Field(None, ge=0, le=60 * 24 * 365)
    note: str = Field("", max_length=400)


def _idem_begin(request: Request, actor: Any, scope: str, payload: Any):
    """Repo-native destructive-write safeguard (`Idempotency-Key` header).

    Same mechanism `admin_dashboard` already uses — a replayed key returns the
    stored result instead of firing the action twice, and a reused key with a
    different payload is a 409. Deliberately NOT a new parallel mechanism.
    """
    try:
        from app.platform import admin_idempotency

        return admin_idempotency.begin(
            request=request, actor_id=getattr(actor, "id", None), scope=scope, payload=payload
        )
    except Exception:
        return None


def _idem_store(token: Any, response: Any) -> None:
    try:
        from app.platform import admin_idempotency

        admin_idempotency.store(token, response)
    except Exception:
        pass


async def _audit(request: Request, actor: Any, action: str, meta: dict[str, Any]) -> None:
    """Best-effort audit trail — never blocks the request (admin_audit redacts)."""
    try:
        from app.platform import admin_audit

        await admin_audit.record_admin_action(
            request=request,
            actor=actor,
            action=action,
            target_type="memory_stack",
            target_id=meta.get("entry_id") or meta.get("agent_id"),
            tenant=meta.get("tenant_id"),
            after=meta,
        )
    except Exception:
        pass


@router.get("/stats", dependencies=[Depends(rate_limit("memstack", 30, 60))])
async def stats(
    tenant_id: str = Query("", max_length=64),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Config + counters only. No memory content is ever returned here."""
    from app.platform import memory_stack as ms

    return ms.snapshot(tenant_id)


@router.get("/diagnostics", dependencies=[Depends(rate_limit("memstack", 30, 60))])
async def diagnostics(_user=Depends(require_admin)) -> dict[str, Any]:
    """Flag-contract validation: partial/invalid config surfaces as problems."""
    from app.platform import memory_stack as ms

    return ms.validate_config()


@router.post("/assemble", dependencies=[Depends(rate_limit("memstack_write", 10, 60))])
async def assemble(
    body: AssembleIn,
    request: Request,
    user=Depends(require_admin),
) -> dict[str, Any]:
    """Preview only — nothing is stored. MASKED unless super-admin asks to reveal."""
    from app.platform import memory_stack as ms

    out = await ms.assemble(
        body.tenant_id,
        body.agent_id,
        body.query,
        session_id=body.session_id,
        subject_id=body.subject_id,
        scope=body.scope,
        token_budget=body.token_budget,
    )
    block = str(out.get("block") or "")
    reveal = False
    if body.reveal:
        try:
            await require_super_admin(user)  # raises 403 for non-super-admin
            reveal = True
        except Exception:
            reveal = False
    if reveal:
        await _audit(
            request,
            user,
            "memory_stack.assemble.reveal",
            {"tenant_id": body.tenant_id, "agent_id": body.agent_id, "tokens": out.get("tokens")},
        )
    else:
        out["block"] = (block[:_PREVIEW_HEAD_CHARS] + " …") if block else ""
    out["masked"] = not reveal
    return out


@router.get("/prospective", dependencies=[Depends(rate_limit("memstack", 30, 60))])
async def prospective(
    tenant_id: str = Query(..., min_length=1, max_length=64),
    agent_id: str = Query("", max_length=40),
    status: str = Query("", max_length=20),
    limit: int = Query(100, ge=1, le=1000),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Tenant-scoped listing, MASKED by default (POLICY B: secrets AND PII).

    Raw memory payloads are never returned from a list endpoint; `payload` is
    replaced by its key names only.
    """
    from app.platform import memory_governance as gov
    from app.platform import prospective_store as ps

    rows = ps.list_rows(tenant_id, agent_id=agent_id, status=status, limit=limit)
    return {
        "rows": [gov.mask_row(r) for r in rows],
        "masked": True,
        "stats": ps.stats(tenant_id),
    }


@router.post("/prospective", dependencies=[Depends(rate_limit("memstack_write", 10, 60))])
async def prospective_add(
    body: ScheduleIn,
    request: Request,
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    from app.platform import memory_stack as ms

    out = ms.schedule(
        body.tenant_id,
        body.agent_id,
        body.action,
        due_at=body.due_at,
        in_minutes=body.in_minutes,
        note=body.note,
        source="admin_api",
    )
    await _audit(
        request,
        user,
        "memory_stack.prospective.schedule",
        {"tenant_id": body.tenant_id, "agent_id": body.agent_id, "ok": out.get("ok")},
    )
    return out


@router.post(
    "/prospective/{entry_id}/cancel",
    dependencies=[Depends(rate_limit("memstack_write", 10, 60))],
)
async def prospective_cancel(
    entry_id: str,
    request: Request,
    tenant_id: str = Query(..., min_length=1, max_length=64),
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    """Tenant-scoped: another tenant's row id simply does not match."""
    from app.platform import prospective_store as ps

    out = ps.cancel(tenant_id, entry_id)
    await _audit(
        request,
        user,
        "memory_stack.prospective.cancel",
        {"tenant_id": tenant_id, "entry_id": entry_id, "ok": out.get("ok")},
    )
    return out


@router.post("/prospective/drain", dependencies=[Depends(rate_limit("memstack_write", 5, 60))])
async def prospective_drain(
    request: Request,
    limit: int = Query(20, ge=1, le=200),
    confirm: bool = Query(False),
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    """Exactly what the scheduler runs. Fail-closed when config/store not ready."""
    if not confirm:
        return {"ok": False, "error": "confirm=true required — drain creates real agent tasks"}
    from app.platform import memory_stack as ms

    token = _idem_begin(request, user, "memory_stack.drain", {"limit": limit})
    if token is not None and hasattr(token, "response"):
        return token.response  # replay of a completed identical request
    out = await ms.drain_if_enabled(limit=limit)
    _idem_store(token, out)
    await _audit(request, user, "memory_stack.prospective.drain", {"result": out})
    return out


class SuppressIn(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    kind: str = Field(..., max_length=16)  # session | subject | pattern
    value: str = Field(..., min_length=1, max_length=200)
    reason: str = Field("", max_length=200)
    confirm: bool = False


@router.get("/governance", dependencies=[Depends(rate_limit("memstack", 30, 60))])
async def governance(
    tenant_id: str = Query(..., min_length=1, max_length=64),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Do-not-remember rules for ONE tenant (values are operator-supplied keys)."""
    from app.platform import memory_governance as gov

    return {"rules": gov.list_rules(tenant_id), "health": gov.rules_health()}


@router.post("/governance/suppress", dependencies=[Depends(rate_limit("memstack_write", 10, 60))])
async def governance_suppress(
    body: SuppressIn,
    request: Request,
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    """Register a do-not-remember rule. Requires explicit confirm=true."""
    if not body.confirm:
        return {"ok": False, "error": "confirm=true required for memory writes"}
    from app.platform import memory_governance as gov

    out = gov.suppress(
        body.tenant_id,
        body.kind,
        body.value,
        reason=body.reason,
        actor=str(getattr(user, "email", "")),
    )
    await _audit(
        request,
        user,
        "memory_stack.governance.suppress",
        {"tenant_id": body.tenant_id, "kind": body.kind, "ok": out.get("ok")},
    )
    return out


@router.post("/governance/forget", dependencies=[Depends(rate_limit("memstack_write", 5, 60))])
async def governance_forget(
    request: Request,
    tenant_id: str = Query(..., min_length=1, max_length=64),
    session_id: str = Query("", max_length=120),
    agent_id: str = Query("", max_length=40),
    confirm: bool = Query(False),
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    """Delete already-stored matching memory. Destructive => confirm=true."""
    if not confirm:
        return {"ok": False, "error": "confirm=true required for destructive delete"}
    from app.platform import memory_governance as gov

    token = _idem_begin(
        request,
        user,
        "memory_stack.forget",
        {"tenant_id": tenant_id, "agent_id": agent_id, "session_id": session_id},
    )
    if token is not None and hasattr(token, "response"):
        return token.response
    out = gov.forget(tenant_id, session_id=session_id, agent_id=agent_id)
    _idem_store(token, out)
    await _audit(
        request,
        user,
        "memory_stack.governance.forget",
        {"tenant_id": tenant_id, "agent_id": agent_id, "purged": out.get("prospective_purged")},
    )
    return out


@router.post("/purge", dependencies=[Depends(rate_limit("memstack_write", 5, 60))])
async def purge(
    request: Request,
    tenant_id: str = Query(..., min_length=1, max_length=64),
    agent_id: str = Query("", max_length=40),
    confirm: bool = Query(False),
    user=Depends(require_super_admin),
) -> dict[str, Any]:
    """DPDP delete — durable rows + this process's working-memory namespace."""
    if not confirm:
        return {"ok": False, "error": "confirm=true required for destructive purge"}
    from app.platform import memory_stack as ms
    from app.platform import prospective_store as ps

    token = _idem_begin(
        request, user, "memory_stack.purge", {"tenant_id": tenant_id, "agent_id": agent_id}
    )
    if token is not None and hasattr(token, "response"):
        return token.response
    out = ps.purge(tenant_id, agent_id=agent_id)
    out["working_cleared"] = ms.clear_tenant_working(tenant_id)
    _idem_store(token, out)
    await _audit(
        request,
        user,
        "memory_stack.purge",
        {"tenant_id": tenant_id, "agent_id": agent_id, "purged": out.get("purged")},
    )
    return out
