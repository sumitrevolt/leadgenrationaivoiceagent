"""ClientOps API — agency client-operations batch (speed-to-lead, approvals,
snapshots, lead routing, proposal tracking).

  GET  /api/clientops/speed-to-lead               (admin)  first-touch metric + verdict
  POST /api/clientops/approval                    (admin)  content approval submit
  GET  /api/clientops/approvals                   (admin)  list (pending/all)
  GET  /api/clientops/approve/{token}             (PUBLIC, 10/60s) client 1-click
                                                  approve|reject — Hinglish HTML
  POST /api/clientops/snapshots/capture           (admin)  GHL-style setup snapshot
  POST /api/clientops/snapshots/capture-niche     (admin)  niche template snapshot
  GET  /api/clientops/snapshots                   (admin)  list snapshots
  GET  /api/clientops/snapshots/{id}              (admin)  snapshot detail
  POST /api/clientops/snapshots/{id}/apply        (admin)  apply on target client
  POST /api/clientops/snapshots/apply-niche       (admin)  1-click niche → client
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

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
    """Approvals list — ?status=pending se sirf pending.

    ADR-104 (2026-07-15, Priority 3): each row now also carries
    ``business_name`` (and ``client_status``) so the admin Approvals table
    can show a readable business name instead of the raw opaque client id.
    One bulk ``list_clients()`` call builds an id→name map (single file
    read, not a per-row lookup) — deleted/missing clients degrade to the
    raw id, never raise. Only the public business name is exposed here,
    never phone/email/other client fields.
    """
    from app.marketing import content_approval
    from app.marketing.clients_store import list_clients

    if status == "pending":
        rows = content_approval.pending(client_id)
    else:
        rows = content_approval.list_all(client_id)
        if status:
            rows = [r for r in rows if r.get("status") == status]

    try:
        name_by_id = {
            str(c.get("id")): str(c.get("business_name") or "").strip()
            for c in list_clients()
            if c.get("id")
        }
    except Exception as _e:  # pragma: no cover — never let enrichment break the list
        logger.debug("approvals business_name enrichment skipped: %s", _e)
        name_by_id = {}

    for r in rows:
        cid = str(r.get("client_id") or "")
        name = name_by_id.get(cid, "")
        r["business_name"] = name or None  # None = deleted/unknown client, UI falls back to id
        r["client_status"] = "unknown" if cid and cid not in name_by_id else "ok"

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


@router.post("/approvals/retire-orphans")
async def retire_orphaned_approvals(
    dry_run: bool = Query(True),
    limit: int = Query(1000, ge=1, le=5000),
    _user=Depends(require_admin),
):
    """321 dead approval rows ko retire karo (PR #297 logic).

    dry_run=True (default) -> sirf counts dikhata hai, kuch mutate nahi.
    dry_run=False -> actual retire (terminal 'expired' status).
    Live client approvals are NEVER touched.
    """
    from app.marketing import content_approval

    return content_approval.retire_orphaned_pending(
        dry_run=dry_run,
        limit=limit,
    )


@router.get("/video/daily-status")
async def video_daily_status(_user=Depends(require_admin)):
    """Daily video producer status - pending/approved/failed counts + config."""
    try:
        from app.marketing import daily_video

        return daily_video.status_summary()
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@router.get("/approve/{token}", dependencies=[Depends(rate_limit("approval", 10, 60))])
async def public_approve(
    token: str,
    action: str = Query("approve", max_length=10),
    note: str = Query("", max_length=300),
):
    """Client ka 1-click approve/reject (PUBLIC, rate-limited) — Hinglish HTML.

    CONTAINMENT (Stage 3B-close): a VIDEO approval may no longer be decided
    here. This route is unauthenticated and the token carries no binding to
    tenant, record, revision or content hash, so possession of a URL used to be
    enough to mark a video finally approved and publishable.

    The refusal happens BEFORE any decision is persisted — not after — so the
    approval record and the video record are left byte-identical.
    """
    from fastapi.responses import HTMLResponse

    from app.marketing import content_approval

    act = "reject" if action == "reject" else "approve"

    if act == "approve":
        rec = content_approval.get_by_token(token) or {}
        if str((rec.get("content") or {}).get("type") or "") == "video_ad":
            refusal = {
                "ok": False,
                "error": "approval_token_regeneration_required",
                "detail": (
                    "Is video ka approval link purana hai. Dashboard se approve "
                    "karein — hum naya secure link bhej rahe hain."
                ),
            }
            return HTMLResponse(
                content_approval.decision_html(refusal, act),
                status_code=409,
            )

    if act == "reject":
        result = content_approval.reject(token, note)
    else:
        result = content_approval.approve(token)
    return HTMLResponse(content_approval.decision_html(result, act))


# ----------------------- F3: client snapshots (GHL) ------------------------ #
class SnapshotCaptureIn(BaseModel):
    client_id: str
    name: str | None = ""


class SnapshotNicheCaptureIn(BaseModel):
    niche: str
    name: str | None = ""


@router.post("/snapshots/capture")
async def snapshot_capture(body: SnapshotCaptureIn, _user=Depends(require_admin)):
    """Client ka reusable setup snapshot lo (mini-site/widget/journeys/schedule)."""
    from app.platform import client_snapshots

    return client_snapshots.capture(body.client_id, body.name or "")


@router.post("/snapshots/capture-niche")
async def snapshot_capture_niche(body: SnapshotNicheCaptureIn, _user=Depends(require_admin)):
    """Niche se GHL-style template snapshot — golden client ki zaroorat nahi."""
    from app.platform import client_snapshots

    return client_snapshots.capture_from_niche(body.niche, body.name or "")


@router.get("/snapshots")
async def snapshot_list(
    niche: str = Query("", max_length=60),
    _user=Depends(require_admin),
):
    from app.platform import client_snapshots

    rows = client_snapshots.list_snapshots()
    if niche:
        nk = niche.strip().lower()
        rows = [r for r in rows if str(r.get("niche_key") or "").lower() == nk]
    return {"ok": True, "count": len(rows), "snapshots": rows}


@router.get("/snapshots/{snapshot_id}")
async def snapshot_get(snapshot_id: str, _user=Depends(require_admin)):
    from app.platform import client_snapshots

    snap = client_snapshots.get_snapshot(snapshot_id)
    if snap is None:
        return {"ok": False, "error": "snapshot nahi mila."}
    return {"ok": True, "snapshot": snap}


class SnapshotApplyIn(BaseModel):
    target_client_id: str


@router.post("/snapshots/{snapshot_id}/apply")
async def snapshot_apply(snapshot_id: str, body: SnapshotApplyIn, _user=Depends(require_admin)):
    """Snapshot naye client pe lagao — naye records append, source untouched."""
    from app.platform import client_snapshots

    return client_snapshots.apply(snapshot_id, body.target_client_id)


class SnapshotApplyNicheIn(BaseModel):
    target_client_id: str
    niche: str | None = ""


@router.post("/snapshots/apply-niche")
async def snapshot_apply_niche(body: SnapshotApplyNicheIn, _user=Depends(require_admin)):
    """1-click: client ke niche ka template lagao (auto-capture agar missing)."""
    from app.platform import client_snapshots

    return client_snapshots.apply_niche_to_client(body.target_client_id, body.niche or None)


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


# ----------------------- F6: AI video-ad cycle (every-N-day) ---------------- #
@router.get("/video-ads")
async def video_ads_list(client_id: str = Query("", max_length=60), _user=Depends(require_admin)):
    """AI video ads list (admin) — ?client_id= filter. Status: pending/approved/
    published/changes_requested/held_max_revisions."""
    from app.marketing import video_ad_cycle

    rows = video_ad_cycle.list_for_client(client_id) if client_id else video_ad_cycle.list_all()
    return {"ok": True, "count": len(rows), "video_ads": rows}


class VideoAdGenIn(BaseModel):
    client_id: str


@router.post("/video-ads/generate")
async def video_ads_generate(body: VideoAdGenIn, _user=Depends(require_admin)):
    """Admin manual: ek client ka video ad banao + approval bhejo. HEAVY build_reel
    background THREAD me (web event-loop block na ho); ~30-60s me approval link aata."""
    import asyncio

    from app.marketing import video_ad_cycle

    cid = (body.client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id zaroori hai."}
    asyncio.create_task(
        asyncio.to_thread(lambda: asyncio.run(video_ad_cycle.generate_for_client(cid)))
    )
    return {"ok": True, "queued": True, "client_id": cid}


class VideoAdChangesIn(BaseModel):
    note: str | None = ""


@router.post("/video-ads/{approval_id}/request-changes")
async def video_ads_request_changes(
    approval_id: str, body: VideoAdChangesIn, _user=Depends(require_admin)
):
    """Client ne change maanga (admin/support entry) — reject + naya version queue."""
    from app.marketing import video_ad_cycle

    return await video_ad_cycle.request_changes(approval_id, body.note or "")


@router.get("/video-production/ops")
async def video_production_ops(
    client_id: str = Query("", max_length=60), _user=Depends(require_admin)
):
    """Admin Video Production Cell queue + flag snapshot (extends video-ads list)."""
    from app.marketing.video_production import cell

    return cell.ops_summary(client_id)


@router.get("/video-production/daily-status")
async def video_production_daily_status(_user=Depends(require_admin)):
    """Why is (or isn't) the DAILY video producer generating?

    One call answers the whole question: master flag, engine preference, the
    fail-closed tenant allowlist, and per-client engine choice + open-review
    backlog + last generated date. Without this the only symptom of a stalled
    daily video is "no new file appeared", which is what let a 15-day generation
    gap sit unnoticed in prod.
    """
    from app.marketing import daily_video

    return daily_video.status()


@router.post("/video-production/daily-run")
async def video_daily_run(_user=Depends(require_admin)):
    """Manually fire one daily-video producer pass (enqueue-only, no ffmpeg here).

    Safe to call from the web process precisely because the producer never
    renders — it dispatches to the video Celery queue. Same-day duplicates are
    refused by the producer's state file and the task's Redis idempotency key.
    """
    from app.marketing import daily_video

    return await daily_video.run_daily()


@router.post("/video-production/daily-clear-block")
async def video_daily_clear_block(
    client_id: str = Query("", max_length=60), _user=Depends(require_admin)
):
    """Un-park a tenant whose ADVANCED engine was blocked by a brief refusal.

    A `needs_customer_input` / `blocked` refusal from Creative OS will not fix
    itself, and retrying it daily burns CREATIVE_TENANT_DAILY_BUDGET on records
    that never render — so the producer parks the tenant on the classic engine.
    Call this after completing the customer's offer/brand facts. Blocks also
    auto-expire after DAILY_VIDEO_ADVANCED_BLOCK_DAYS.
    """
    from app.marketing import daily_video

    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id zaroori hai."}
    return daily_video.clear_advanced_block(cid)


class VideoCellGenIn(BaseModel):
    client_id: str
    note: str | None = ""
    ratio: str | None = "9:16"


@router.post("/video-production/generate")
async def video_production_generate(body: VideoCellGenIn, _user=Depends(require_admin)):
    """Governed generate via Video Production Cell (HEAVY — background)."""
    import asyncio

    from app.marketing.video_production import cell

    cid = (body.client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id zaroori hai."}
    from app.marketing.video_production.allowlist import assert_own_brand_allowlist

    allow = assert_own_brand_allowlist(cid)
    if not allow.get("ok"):
        return allow
    ratio = (body.ratio or "9:16").strip()

    async def _run() -> None:
        await cell.render_and_queue_review(cid, note=body.note or "", ratio=ratio)

    asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(_run())))
    return {"ok": True, "queued": True, "client_id": cid, "ratio": ratio}


class VideoApproveIn(BaseModel):
    expected_revision: int | None = None
    #: The admin must have previewed the exact bytes, same as a customer.
    expected_content_sha256: str = ""


@router.post("/video-production/{video_ad_id}/approve")
async def video_production_approve(
    video_ad_id: str, body: VideoApproveIn, user=Depends(require_admin)
):
    """Version-bound approve (admin/support).

    Previously this discarded the authenticated ``User`` and approved as the
    literal string ``"admin"``, so the ledger could not say WHICH admin acted.
    The User row carries a stable ``User.id``, so a real principal is built from
    it. No caller-supplied actor is accepted.
    """
    import re as _re

    from app.marketing import video_ad_cycle
    from app.marketing.video_production import cell
    from app.marketing.video_production.approval_principal import PrincipalRefused, from_admin_user

    expected_hash = str(body.expected_content_sha256 or "").strip().lower()
    if not _re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise HTTPException(status_code=400, detail="expected_content_sha256 required (64-hex)")

    rec = (video_ad_cycle._latest() or {}).get(str(video_ad_id)) or {}
    if not rec:
        raise HTTPException(status_code=404, detail="video_ad_not_found")
    try:
        principal = from_admin_user(user, tenant_id=str(rec.get("client_id") or ""))
    except PrincipalRefused as exc:
        raise HTTPException(status_code=exc.status, detail=exc.code) from None

    return cell.approve_version(
        video_ad_id,
        body.expected_revision,
        principal=principal,
        expected_sha256=expected_hash,
    )


# --------------- Creative Automation OS (ADR-143, flag-gated) --------------- #
@router.get("/creative-os/ops")
async def creative_os_ops(client_id: str = Query("", max_length=60), _user=Depends(require_admin)):
    """Admin Creative Production cockpit queue + flag snapshot."""
    from app.marketing.creative_os import list_cockpit

    return list_cockpit(client_id)


class CreativeOsGenIn(BaseModel):
    client_id: str
    business_name: str | None = ""
    recipe: str | None = "offer_announcement"
    offer: str | None = ""
    niche: str | None = "general"
    language: str | None = "hinglish"
    platform: str | None = "instagram"
    ratio: str | None = "9:16"
    provider: str | None = "deterministic"
    cta: str | None = ""


@router.post("/creative-os/generate")
async def creative_os_generate(body: CreativeOsGenIn, _user=Depends(require_admin)):
    """Enqueue deterministic preview (Celery video worker). No in-process FFmpeg."""
    from app.marketing.creative_os import enqueue_generate

    cid = (body.client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id zaroori hai."}
    biz = (body.business_name or cid).strip()
    return enqueue_generate(
        tenant_id=cid,
        business_name=biz,
        recipe=(body.recipe or "offer_announcement").strip(),
        offer=body.offer or "",
        niche=body.niche or "general",
        language=body.language or "hinglish",
        platform=body.platform or "instagram",
        aspect_ratio=(body.ratio or "9:16").strip(),
        provider=(body.provider or "deterministic").strip(),
        cta=body.cta or "",
    )


class CreativeOsIdIn(BaseModel):
    client_id: str
    note: str | None = ""


@router.post("/creative-os/{creative_id}/approve")
async def creative_os_approve(creative_id: str, body: CreativeOsIdIn, _user=Depends(require_admin)):
    from app.marketing.creative_os import approve_exact

    return approve_exact((body.client_id or "").strip(), creative_id, actor="admin")


@router.post("/creative-os/{creative_id}/changes")
async def creative_os_changes(creative_id: str, body: CreativeOsIdIn, _user=Depends(require_admin)):
    from app.marketing.creative_os import request_changes

    return request_changes((body.client_id or "").strip(), creative_id, note=body.note or "")


@router.post("/creative-os/{creative_id}/quarantine")
async def creative_os_quarantine(
    creative_id: str, body: CreativeOsIdIn, _user=Depends(require_admin)
):
    from app.marketing.creative_os import quarantine

    return quarantine(
        (body.client_id or "").strip(), creative_id, reason=body.note or "quarantined"
    )


@router.get("/creative-os/{creative_id}/publish-gate")
async def creative_os_publish_gate(
    creative_id: str,
    client_id: str = Query(..., max_length=60),
    _user=Depends(require_admin),
):
    """Exact-hash + VIDEO_SOCIAL_PUBLISH gate — never auto-publishes."""
    from app.marketing.creative_os.service import publish_gate

    return publish_gate(client_id, creative_id)


@router.get("/creative-os/{creative_id}/customer-view")
async def creative_os_customer_view(
    creative_id: str,
    client_id: str = Query(..., max_length=60),
    _user=Depends(require_admin),
):
    """Customer-safe projection (admin preview of what customer sees)."""
    from app.marketing.creative_os.service import customer_view

    return customer_view(client_id, creative_id)


@router.get("/gsc/overview")
async def gsc_overview(_user=Depends(require_admin)):
    """Google Search Console rank snapshot overview — latest aggregates +
    30-day trend for the admin control surface. No-op/empty if GSC_ENABLED=0
    ya creds nahi hain (integration INERT by design — app/integrations/gsc.py)."""
    from app.integrations import gsc

    return {
        "enabled": gsc.enabled(),
        "site": gsc.site_url(),
        "latest": gsc.latest_state(),
        "trend": gsc.trend(30),
    }


@router.get("/posthog/funnel")
async def posthog_funnel_overview(
    create: int = Query(0, ge=0, le=1),
    payload: int = Query(0, ge=0, le=1),
    _user=Depends(require_admin),
):
    """Inquiry → paid funnel insight (PostHog) — business_type/niche split.

    - capture_enabled: lead_captured/payment_activated events dono ab business_type
      + niche properties carry karte hain (PostHog me funnel breakdown chalta hai).
    - payload=1: exact FUNNELS filters JSON — PostHog UI me paste karne ke liye
      (jab personal API key nahi hai).
    - create=1: PostHog API se insight banao (POSTHOG_PERSONAL_API_KEY phx_
      chahiye; phc_ key private endpoints pe nahi chalta — INERT by design).
    """
    from app.analytics import posthog_client as _ph
    from app.integrations import posthog_funnel as pf

    out: dict[str, Any] = {
        "capture_enabled": _ph.enabled(),
        "insight": pf.ensure_insight(create=bool(create)),
    }
    if payload:
        out["payload"] = pf.insight_payload()
    return out


__all__ = ["router"]
