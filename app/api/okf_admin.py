"""Admin OKF knowledge-stack API — status / dry-run / ingest (ADR-119 Phase-1).

  GET  /api/admin/okf/status
  POST /api/admin/okf/dry-run
  POST /api/admin/okf/ingest   — requires OKF_INGEST_ENABLED=1 (or force=false path)
  GET  /api/admin/okf/recall?q=

Ingest is fail-closed when flag OFF. No customer namespaces. No secrets.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin, require_super_admin
from app.api.ratelimit import rate_limit

router = APIRouter(prefix="/api/admin/okf", tags=["OKF"])


class IngestIn(BaseModel):
    force: bool = Field(
        False,
        description="Ignored in prod paths — kept for explicitness; flag must still be ON.",
    )


async def _audit(request: Request, actor: Any, action: str, meta: dict[str, Any]) -> None:
    try:
        from app.platform import admin_audit

        await admin_audit.record_admin_action(
            request=request,
            actor=actor,
            action=action,
            target_type="okf",
            target_id="knowledge",
            after=meta,
        )
    except Exception:
        pass


@router.get("/status", dependencies=[Depends(rate_limit("okf", 30, 60))])
async def okf_status(_user=Depends(require_admin)) -> dict[str, Any]:
    from app.platform import okf_bundle

    snap = okf_bundle.snapshot()
    # Trim body listings for status — keep counts + paths only
    return {
        "okf_version": snap["okf_version"],
        "root": snap["root"],
        "doc_count": snap["doc_count"],
        "blocked_count": snap["blocked_count"],
        "blocked": snap["blocked"],
        "namespace": snap["namespace"],
        "public_bundle": snap["public_bundle"],
        "ingest_enabled": snap["ingest_enabled"],
        "paths": [d["relpath"] for d in snap["docs"]],
        "router_hint": "postgres | okf | qdrant | graphify via okf_bundle.route_knowledge_source",
    }


@router.post("/dry-run", dependencies=[Depends(rate_limit("okf", 20, 60))])
async def okf_dry_run(
    request: Request,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import okf_ingest

    out = okf_ingest.dry_run()
    await _audit(request, _user, "okf_dry_run", {"ready": out.get("ready_count")})
    return out


@router.post("/ingest", dependencies=[Depends(rate_limit("okf_write", 5, 60))])
async def okf_ingest_route(
    request: Request,
    body: IngestIn | None = None,
    _user=Depends(require_super_admin),
) -> dict[str, Any]:
    from app.platform import okf_ingest

    # force flag on body does NOT bypass OKF_INGEST_ENABLED — never arm from request alone
    _ = body  # reserved
    out = okf_ingest.ingest(force=False)
    await _audit(
        request,
        _user,
        "okf_ingest",
        {"ok": out.get("ok"), "chunks": out.get("chunks"), "reason": out.get("reason")},
    )
    return out


@router.get("/recall", dependencies=[Depends(rate_limit("okf", 30, 60))])
async def okf_recall(
    q: str = Query("", max_length=500),
    k: int = Query(5, ge=1, le=20),
    _user=Depends(require_admin),
) -> dict[str, Any]:
    from app.platform import okf_bundle, okf_ingest

    return {
        "query": q,
        "route_hint": okf_bundle.route_knowledge_source(q),
        "namespace": okf_bundle.OKF_NAMESPACE,
        "results": okf_ingest.recall(q, k=k),
    }
