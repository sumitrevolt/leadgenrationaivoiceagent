"""ContentAuto API — content/intel tools batch (agent R).

  POST /api/contentauto/repurpose          (admin)  1 topic/URL → 7 formats
  POST /api/contentauto/pulse              (admin)  brand mention scan (news+reddit)
  GET  /api/contentauto/pulse/runs         (admin)  weekly brand-pulse run records
  POST /api/contentauto/month-plan         (admin)  30-din calendar (dry_run default; commit=true → content_schedule)
  GET  /api/contentauto/team-report        (admin)  weekly AI-staff narrative (?client_id=)
  POST /api/contentauto/team-report/run    (admin)  gated TEAM_REPORT weekly sweep
  POST /api/contentauto/push/subscribe     (public, 30/60s)  browser push sub save
  GET  /api/contentauto/push/subscribe.js  (public)  vanilla JS snippet (?slug=)
  POST /api/contentauto/push/send          (admin)  web push (keys absent = draft-only)
  GET  /api/contentauto/push/status        (admin)  availability + sub counts

Mount (main.py):
    from app.api.contentauto import router as contentauto_router
    app.include_router(contentauto_router, prefix="/api")   # /api/contentauto/*

Flags: BRAND_PULSE / TEAM_REPORT (default OFF); webpush = VAPID keys presence.
PROD lessons baked in: har LLM/network call asyncio.wait_for; sync/file work
asyncio.to_thread; modules never-raise (error dicts).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(
    prefix="/contentauto",
    tags=["ContentAuto"],
    dependencies=[Depends(rate_limit("contentauto", 60, 60))],
)


# ------------------------------ 1) Repurpose --------------------------------- #
class RepurposeIn(BaseModel):
    topic_or_url: str
    niche: str = "general"
    slug: str = ""
    business_name: str = ""


@router.post("/repurpose")
async def repurpose_pack(body: RepurposeIn, _user=Depends(require_admin)):
    """1 input → 7 formats (post/carousel/reel/GBP/WA-status/email/hashtags)."""
    from app.marketing import repurpose

    try:
        return await asyncio.wait_for(
            repurpose.repurpose(
                body.topic_or_url,
                niche=body.niche,
                slug=body.slug or None,
                business_name=body.business_name,
            ),
            timeout=40,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


# ------------------------------ 2) Brand pulse ------------------------------- #
class PulseIn(BaseModel):
    business_name: str
    city: str = ""
    niche: str = ""


@router.post("/pulse")
async def brand_pulse_scan(body: PulseIn, _user=Depends(require_admin)):
    """Brand24-lite mention scan (Google News + Reddit, 6hr cache, drafts only)."""
    from app.platform import brand_pulse

    try:
        return await asyncio.wait_for(
            brand_pulse.scan(body.business_name, city=body.city or None, niche=body.niche or None),
            timeout=25,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


@router.get("/pulse/runs")
async def brand_pulse_runs(limit: int = Query(30, ge=1, le=200), _user=Depends(require_admin)):
    """Weekly brand-pulse sweep records (gated BRAND_PULSE=1 sweep)."""
    from app.platform import brand_pulse

    return {"ok": True, "runs": await asyncio.to_thread(brand_pulse.runs, limit)}


# ------------------------------ 3) Month planner ----------------------------- #
class MonthPlanIn(BaseModel):
    niche: str = "general"
    client_id: str = ""
    slug: str = ""
    business_name: str = ""
    start: str = ""  # YYYY-MM-DD (default: kal)
    days: int = 30
    offer: str = ""
    channel: str = "instagram"
    commit: bool = False  # default DRY-RUN preview


@router.post("/month-plan")
async def month_plan(body: MonthPlanIn, _user=Depends(require_admin)):
    """30-din content calendar — preview default; commit=true → content_schedule queue."""
    from app.marketing import month_planner

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                month_planner.plan_month,
                niche=body.niche,
                client_id=body.client_id,
                slug=body.slug,
                business_name=body.business_name,
                start=body.start or None,
                days=body.days,
                offer=body.offer,
                channel=body.channel,
                dry_run=not body.commit,
                commit=body.commit,
            ),
            timeout=25,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


# ------------------------------ 4) Team report ------------------------------- #
@router.get("/team-report")
async def team_report(client_id: str = Query("", max_length=64), _user=Depends(require_admin)):
    """'Aapki AI team ne is hafte yeh kiya' — Hinglish narrative HTML."""
    from app.platform import team_report as tr

    try:
        return await asyncio.wait_for(tr.weekly_narrative(client_id or None), timeout=25)
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


@router.post("/team-report/run")
async def team_report_run(_user=Depends(require_admin)):
    """Gated TEAM_REPORT=1 weekly sweep — active clients ke report files (+email)."""
    from app.platform import team_report as tr

    try:
        return await asyncio.wait_for(tr.run_weekly_if_enabled(), timeout=60)
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


# ------------------------------ 5) Web push ---------------------------------- #
class PushSubscribeIn(BaseModel):
    slug: str = "default"
    subscription: dict[str, Any]


@router.post("/push/subscribe", dependencies=[Depends(rate_limit("pushsub", 30, 60))])
async def push_subscribe(body: PushSubscribeIn):
    """PUBLIC — browser PushSubscription save (dedupe endpoint)."""
    from app.platform import webpush

    return await asyncio.to_thread(webpush.save_subscription, body.slug, body.subscription)


@router.get("/push/subscribe.js")
async def push_subscribe_js(slug: str = Query("default", max_length=64)):
    """PUBLIC — vanilla JS snippet (mini-site/widget me <script src=> se lagao)."""
    from app.platform import webpush

    return Response(webpush.subscribe_js(slug), media_type="application/javascript")


class PushSendIn(BaseModel):
    slug: str = "default"
    title: str
    body: str = ""
    url: str = ""


@router.post("/push/send")
async def push_send(body: PushSendIn, _user=Depends(require_admin)):
    """Web push to slug subscribers — keys/pywebpush absent = DRAFT-only (inert)."""
    from app.platform import webpush

    try:
        return await asyncio.wait_for(
            asyncio.to_thread(webpush.send_push, body.slug, body.title, body.body, body.url),
            timeout=30,
        )
    except asyncio.TimeoutError:
        return {"ok": False, "reason": "timeout"}


@router.get("/push/status")
async def push_status(_user=Depends(require_admin)):
    """Availability (pywebpush+VAPID), subscription counts, pending drafts."""
    from app.platform import webpush

    return await asyncio.to_thread(webpush.status)
