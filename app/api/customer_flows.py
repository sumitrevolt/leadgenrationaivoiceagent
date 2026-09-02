"""Customer-portal flow builder API (Phase 7) — tenant-scoped, draft-only, gated.

Customers (require_customer -> client_id) CRUD + run + monitor flows scoped to
THEIR client_id, using ONLY CUSTOMER_SAFE_ACTIONS. Hard tenant isolation: every
op owner-checks; cross-tenant access -> 404 (no existence leak). Double-gated
FLOW_RUNNER + FLOW_RUNNER_CUSTOMER (default OFF). Never-raise.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api.customer_auth import require_customer

router = APIRouter(prefix="/api/customer", tags=["Customer Flows"])

_MAX_CUSTOMER_FLOWS = 20  # per-client cap (monkeypatchable)


def _on() -> bool:
    return os.getenv("FLOW_RUNNER", "0") in ("1", "true", "True") and os.getenv(
        "FLOW_RUNNER_CUSTOMER", "0"
    ) in ("1", "true", "True")


def _gate():
    return (
        None if _on() else JSONResponse({"error": "FLOW_RUNNER_CUSTOMER disabled"}, status_code=503)
    )


def _not_found():
    return JSONResponse({"error": "not found"}, status_code=404)


class CustomerFlowIn(BaseModel):
    id: str | None = None
    name: str = "Untitled flow"
    nodes: list[dict] = []
    edges: list[dict] = []


class ApproveIn(BaseModel):
    note: str = ""
    node_id: str = ""


class ApplyTemplateIn(BaseModel):
    name: str = ""


@router.get("/flows")
async def cf_list(cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_store

    return {"flows": flow_store.list_flows(owner=cid)}


@router.get("/flow-templates")
async def cf_templates(cid: str = Depends(require_customer)):
    """Starter flow templates — 1-click apply seeds a real, runnable flow."""
    g = _gate()
    if g:
        return g
    from app.automation import flow_templates

    return {"templates": flow_templates.list_templates()}


@router.post("/flow-templates/{tid}/apply")
async def cf_apply_template(tid: str, body: ApplyTemplateIn, cid: str = Depends(require_customer)):
    """Create an owner-scoped flow from a starter template (validated first)."""
    g = _gate()
    if g:
        return g
    from app.automation import flow_compiler, flow_store, flow_templates

    flow_body = flow_templates.to_flow(tid, name_override=body.name)
    if flow_body is None:
        return _not_found()
    if flow_store.count_for_owner(cid) >= _MAX_CUSTOMER_FLOWS:
        return {"ok": False, "error": f"flow limit reached ({_MAX_CUSTOMER_FLOWS})"}
    # defense-in-depth: validate under the strict customer gate BEFORE persisting
    _proc, errs, _kind = flow_compiler.compile_flow(flow_body, customer_safe=True)
    if errs:
        return {"ok": False, "error": "template not runnable", "compile_errors": errs}
    saved = flow_store.save_flow(flow_body, by=f"customer:{cid}", owner_client_id=cid)
    if not saved.get("ok"):
        return saved
    return {"ok": True, "flow": saved["flow"], "from_template": tid}


@router.post("/flow")
async def cf_save(body: CustomerFlowIn, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_compiler, flow_store

    fid = (body.id or "").strip()
    existing = flow_store.get_flow(fid) if fid else None
    # anti-hijack: an id that exists but isn't yours -> 404 (can't overwrite admin/other-tenant flow)
    if existing and str(existing.get("owner_client_id") or "") != cid:
        return _not_found()
    if existing is None and flow_store.count_for_owner(cid) >= _MAX_CUSTOMER_FLOWS:
        return {"ok": False, "error": f"flow limit reached ({_MAX_CUSTOMER_FLOWS})"}
    saved = flow_store.save_flow(body.model_dump(), by=f"customer:{cid}", owner_client_id=cid)
    if not saved.get("ok"):
        return saved
    _proc, errs, kind = flow_compiler.compile_flow(saved["flow"], customer_safe=True)
    return {
        "ok": True,
        "flow": saved["flow"],
        "compile_errors": errs,
        "runnable": not errs,
        "kind": kind,
    }


@router.get("/flow/{flow_id}")
async def cf_get(flow_id: str, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_compiler, flow_store

    if not flow_store.owned_by(flow_id, cid):
        return _not_found()
    fl = flow_store.get_flow(flow_id)
    proc, errs, kind = flow_compiler.compile_flow(fl, customer_safe=True)
    return {
        "flow": fl,
        "compile_errors": errs,
        "kind": kind,
        "runnable": not errs,
        "steps": (proc or {}).get("steps", []),
    }


@router.get("/flow/{flow_id}/versions")
async def cf_versions(flow_id: str, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_store

    if not flow_store.owned_by(flow_id, cid):
        return _not_found()
    return {"versions": flow_store.list_versions(flow_id)}


class RollbackIn(BaseModel):
    version: int


@router.post("/flow/{flow_id}/rollback")
async def cf_rollback(flow_id: str, body: RollbackIn, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_compiler, flow_store

    if not flow_store.owned_by(flow_id, cid):
        return _not_found()
    saved = flow_store.rollback_flow(flow_id, body.version, by=f"customer:{cid}")
    if not saved.get("ok"):
        return saved
    _proc, errs, kind = flow_compiler.compile_flow(saved["flow"], customer_safe=True)
    return {
        "ok": True,
        "flow": saved["flow"],
        "compile_errors": errs,
        "runnable": not errs,
        "kind": kind,
    }


@router.delete("/flow/{flow_id}")
async def cf_delete(flow_id: str, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.automation import flow_store

    if not flow_store.owned_by(flow_id, cid):
        return _not_found()
    return {"ok": flow_store.delete_flow(flow_id)}


@router.post("/flow/{flow_id}/run")
async def cf_run(flow_id: str, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.agents import flow_dispatch
    from app.automation import flow_compiler, flow_store

    if not flow_store.owned_by(flow_id, cid):
        return _not_found()
    # defense-in-depth: re-validate customer_safe before running
    _proc, errs, _kind = flow_compiler.compile_flow(
        flow_store.get_flow(flow_id), customer_safe=True
    )
    if errs:
        return {"ok": False, "error": "not runnable", "compile_errors": errs}
    # Hydrate the calling tenant's client context into run inputs — executors read
    # inputs.client_id/business_name/niche (e.g. brand_pulse needs business_name,
    # client_report needs client_id); without these the shipped templates fail.
    from app.marketing import clients_store

    _c = clients_store.get_client(cid) or {}
    r = flow_dispatch.start(
        f"flow:{flow_id}",
        {
            "_owner_client_id": cid,
            "client_id": cid,
            "business_name": _c.get("business_name") or "",
            "niche": _c.get("niche") or "general",
            "city": _c.get("city") or "",
        },
    )
    if r.get("ok"):
        run_id = r.get("run_id") or ""
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            try:
                r["advance"] = await flow_dispatch.advance(run_id)
                r["queued"] = False
            except Exception:
                r["queued"] = False
    return r


def _run_owned(run_id: str, cid: str):
    """Return replay state IF the run's flow is owned by cid, else None."""
    from app.agents import flow_dispatch
    from app.automation import flow_store

    st = flow_dispatch.replay(run_id)
    proc = str(st.get("process") or "")
    if not proc.lower().startswith("flow:") or not flow_store.owned_by(proc[5:], cid):
        return None
    return st


@router.get("/flow/run/{run_id}")
async def cf_run_status(run_id: str, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.agents import flow_dispatch

    st = _run_owned(run_id, cid)
    if st is None:
        return _not_found()
    return {"state": st, "journal": flow_dispatch.journal(run_id)}


@router.post("/flow/run/{run_id}/approve")
async def cf_approve(run_id: str, body: ApproveIn, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.agents import flow_dispatch

    if _run_owned(run_id, cid) is None:
        return _not_found()
    r = flow_dispatch.approve(
        run_id, approved_by=f"customer:{cid}", note=body.note, node_id=body.node_id
    )
    if r.get("ok"):
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
        except Exception:
            pass
    return r


@router.post("/flow/run/{run_id}/reject")
async def cf_reject(run_id: str, body: ApproveIn, cid: str = Depends(require_customer)):
    g = _gate()
    if g:
        return g
    from app.agents import flow_dispatch

    if _run_owned(run_id, cid) is None:
        return _not_found()
    return flow_dispatch.reject(
        run_id, by=f"customer:{cid}", reason=body.note, node_id=body.node_id
    )


__all__ = ["router"]
