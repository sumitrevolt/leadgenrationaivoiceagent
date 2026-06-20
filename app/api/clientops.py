"""ClientOps API — agency client-operations batch (speed-to-lead, approvals,
snapshots, lead routing, proposal tracking).

  GET  /api/clientops/speed-to-lead               (admin)  first-touch metric + verdict
  POST /api/clientops/approval                    (admin)  content approval submit
  GET  /api/clientops/approvals                   (admin)  list (pending/all)
  GET  /api/clientops/approve/{token}             (PUBLIC, 10/60s) client 1-click
                                                  approve|reject — Hinglish HTML
  POST /api/clientops/snapshots/capture           (admin)  GHL-style setup snapshot
  GET  /api/clientops/snapshots                   (admin)  list snapshots
  POST /api/clientops/snapshots/{id}/apply        (admin)  apply on target client
  POST /api/clientops/routing                     (admin)  team round-robin config
  GET  /api/clientops/routing                     (admin)  config view
  POST /api/clientops/routing/assign              (admin)  assign lead → member + wa link
  GET  /api/clientops/routing/assignments         (admin)  recent assignments
  POST /api/clientops/track-proposal              (admin)  trackable proposal link
  GET  /api/clientops/p/{token}                   (PUBLIC, 60/60s) view-log + 302/HTML
  GET  /api/clientops/proposal-views              (admin)  views / opened detection

Mount (main session):
    from app.api.clientops import router as clientops_router
    app.include_router(clientops_router, prefix="/api")   # /api/clientops/*

Sab additive + free-stack + never-raise (modules error dicts dete). Koi
ML/KB/LLM/heavy-sync NAHI — public paths pure file-IO light (prod-down lesson).
Koi naya env flag nahi — sab read/draft-safe by design.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/clientops", tags=["ClientOps"])


# ------------------------- F1: speed-to-lead (admin) ----------------------- #
@router.get("/speed-to-lead")
async def speed_to_lead(days: int = Query(30, ge=1, le=365), _user=Depends(require_admin)):
    """Inquiry → first-touch time (alerts/dialer evidence se, READ-only) + verdict."""
    from app.platform import speed_to_lead as stl

    return stl.summary(days)


# ----------------------- F2: content approval loop ------------------------- #
class ApprovalIn(BaseModel):
    client_id: str
    content: dict[str, Any]


@router.post("/approval")
async def submit_approval(body: ApprovalIn, _user=Depends(require_admin)):
    """Content client-approval me daalo — token link + WA share draft milta."""
    from app.marketing import content_approval

    return content_approval.submit(body.client_id, body.content)


@router.get("/approvals")
async def list_approvals(
    client_id: str = Query("", max_length=60),
    status: str = Query("", max_length=12),
    _user=Depends(require_admin),
):
    """Approvals list — ?status=pending se sirf pending."""
    from app.marketing import content_approval

    if status == "pending":
        rows = content_approval.pending(client_id)
    else:
        rows = content_approval.list_all(client_id)
        if status:
            rows = [r for r in rows if r.get("status") == status]
    return {"ok": True, "count": len(rows), "approvals": rows}


class ApprovalDecideIn(BaseModel):
    action: str
    note: str | None = ""


@router.post("/approvals/{approval_id}/decide")
async def admin_decide_approval(
    approval_id: str,
    body: ApprovalDecideIn,
    _user=Depends(require_admin),
):
    """Admin dashboard se content approve/reject — token link ki zaroorat nahi."""
    from app.marketing import content_approval

    act = "reject" if str(body.action or "").strip().lower() == "reject" else "approve"
    return content_approval.decide_by_id(approval_id, act, body.note or "")


@router.get("/approve/{token}", dependencies=[Depends(rate_limit("approval", 10, 60))])
async def public_approve(
    token: str,
    action: str = Query("approve", max_length=10),
    note: str = Query("", max_length=300),
):
    """Client ka 1-click approve/reject (PUBLIC, rate-limited) — Hinglish HTML."""
    from fastapi.responses import HTMLResponse

    from app.marketing import content_approval

    act = "reject" if action == "reject" else "approve"
    if act == "reject":
        result = content_approval.reject(token, note)
    else:
        result = content_approval.approve(token)
    return HTMLResponse(content_approval.decision_html(result, act))


# ----------------------- F3: client snapshots (GHL) ------------------------ #
class SnapshotCaptureIn(BaseModel):
    client_id: str
    name: str | None = ""


@router.post("/snapshots/capture")
async def snapshot_capture(body: SnapshotCaptureIn, _user=Depends(require_admin)):
    """Client ka reusable setup snapshot lo (mini-site/widget/journeys/schedule)."""
    from app.platform import client_snapshots

    return client_snapshots.capture(body.client_id, body.name or "")


@router.get("/snapshots")
async def snapshot_list(_user=Depends(require_admin)):
    from app.platform import client_snapshots

    rows = client_snapshots.list_snapshots()
    return {"ok": True, "count": len(rows), "snapshots": rows}


class SnapshotApplyIn(BaseModel):
    target_client_id: str


@router.post("/snapshots/{snapshot_id}/apply")
async def snapshot_apply(snapshot_id: str, body: SnapshotApplyIn, _user=Depends(require_admin)):
    """Snapshot naye client pe lagao — naye records append, source untouched."""
    from app.platform import client_snapshots

    return client_snapshots.apply(snapshot_id, body.target_client_id)


# --------------------- F4: lead distribution (round-robin) ----------------- #
class RoutingConfigIn(BaseModel):
    client_id: str
    members: list[dict[str, Any]]
    mode: str | None = "round_robin"


@router.post("/routing")
async def routing_set(body: RoutingConfigIn, _user=Depends(require_admin)):
    """Client ki team set karo — leads round-robin me bantenge."""
    from app.platform import lead_distribution

    return lead_distribution.set_config(body.client_id, body.members, body.mode or "round_robin")


@router.get("/routing")
async def routing_get(
    client_id: str = Query(..., min_length=1, max_length=60),
    _user=Depends(require_admin),
):
    from app.platform import lead_distribution

    cfg = lead_distribution.get_config(client_id)
    return {"ok": cfg is not None, "config": cfg}


class AssignIn(BaseModel):
    client_id: str
    lead: dict[str, Any]


@router.post("/routing/assign")
async def routing_assign(body: AssignIn, _user=Depends(require_admin)):
    """Lead next member ko do — assignment log + WA 1-click handoff link."""
    from app.platform import lead_distribution

    return lead_distribution.assign(body.client_id, body.lead)


@router.get("/routing/assignments")
async def routing_assignments(
    client_id: str = Query("", max_length=60), _user=Depends(require_admin)
):
    from app.platform import lead_distribution

    rows = lead_distribution.assignments(client_id)
    return {"ok": True, "count": len(rows), "assignments": rows}


# --------------------- F5: trackable proposals ------------------------------ #
class TrackProposalIn(BaseModel):
    url: str | None = ""
    html: str | None = ""
    phone: str | None = ""
    label: str | None = ""


@router.post("/track-proposal")
async def track_proposal(body: TrackProposalIn, _user=Depends(require_admin)):
    """Proposal ka tracking link banao (url redirect YA stored html)."""
    from app.platform import proposal_tracking

    return proposal_tracking.make_tracked(
        url=body.url or "", html=body.html or "", phone=body.phone or "", label=body.label or ""
    )


@router.get("/p/{token}", dependencies=[Depends(rate_limit("proposal_view", 60, 60))])
async def proposal_open(token: str, request: Request):
    """PUBLIC — view log karke proposal dikhao (302 ya stored HTML).
    Unknown token → homepage redirect (kabhi 404 nahi — purane links graceful)."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    from app.platform import proposal_tracking

    try:
        target = proposal_tracking.resolve(token)
        if target is not None:
            # Sirf REAL proposal open pe view log (unknown tokens log nahi hote).
            ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
                request.client.host if request.client else ""
            )
            proposal_tracking.record_view(token, ua=request.headers.get("user-agent", ""), ip=ip)
            if target.get("html"):
                return HTMLResponse(target["html"])
            if target.get("url"):
                return RedirectResponse(target["url"], status_code=302)
    except Exception as e:  # pragma: no cover - modules defensive hain
        logger.warning(f"[clientops] proposal open failed: {e}")
    return RedirectResponse("https://leadsgenai.in", status_code=302)


@router.get("/proposal-views")
async def proposal_views(token: str = Query("", max_length=64), _user=Depends(require_admin)):
    """?token= se ek proposal ke views; bina token = sab tracked proposals."""
    from app.platform import proposal_tracking

    if token:
        return proposal_tracking.views(token)
    rows = proposal_tracking.list_tracked()
    return {"ok": True, "count": len(rows), "proposals": rows}


__all__ = ["router"]
