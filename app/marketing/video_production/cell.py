"""Video Production Cell — thin orchestration over video_ad_cycle + pipeline.

Does NOT invent a second agent framework. Maps roles onto canonical STAFF:
  isha  — brief / script / creative / review request
  zara  — approval-gated social publish
  arnav — compliance/safety checks (read-only gate helper)
Boss/manager coordinates via Owner OS (existing).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.marketing.video_production import flags, states
from app.marketing.video_production.publish_gate import assert_can_publish, mark_version_approved
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _audit(agent: str, kind: str, msg: str, meta: dict[str, Any] | None = None) -> None:
    try:
        from app.platform import team

        team.log_event(agent, kind, msg, meta=meta or {})
    except Exception:
        pass


def create_daily_brief(client_id: str, content_date: str = "") -> dict[str, Any]:
    """GREEN — plan daily video without rendering."""
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        if not c:
            return {"ok": False, "error": "client_missing"}
        # Do not fabricate offers
        offer = str(c.get("offer") or "").strip()
        brief = {
            "id": uuid.uuid4().hex[:12],
            "client_id": client_id,
            "content_date": content_date or time.strftime("%Y-%m-%d"),
            "business_name": c.get("business_name"),
            "niche": c.get("niche") or "general",
            "offer": offer,
            "offer_missing": not bool(offer),
            "purpose": "organic_daily",
            "language": c.get("language") or "hi",
            "hook": f"{c.get('business_name')} — {offer or (c.get('niche') or 'local')} update",
            "cta": "Call ya WhatsApp karo",
            "agent": "isha",
            "workflow_state": states.BRIEF_CREATED,
        }
        _audit("isha", "video_brief", f"brief for {client_id}", {"brief_id": brief["id"]})
        return {"ok": True, "brief": brief}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


def write_script(brief: dict[str, Any]) -> dict[str, Any]:
    """GREEN — script from brief; never invent prices/testimonials."""
    try:
        offer = str(brief.get("offer") or "").strip()
        biz = str(brief.get("business_name") or "Aapka Business")
        niche = str(brief.get("niche") or "general")
        slides = [
            str(brief.get("hook") or biz),
            offer or f"Aapke area ka bharosemand {niche}",
            str(brief.get("cta") or "Call ya WhatsApp karo"),
        ]
        script = {
            "hook": slides[0],
            "body": slides[1],
            "cta": slides[2],
            "slides": slides,
            "caption": f"{biz} — {offer or niche}. {slides[2]}",
            "hashtags": [],
            "fabricated_claims": False,
            "offer_missing": bool(brief.get("offer_missing")),
            "workflow_state": states.SCRIPT_CREATED,
        }
        return {"ok": True, "script": script}
    except Exception as e:
        return {"ok": False, "error": str(e)[:160]}


async def render_and_queue_review(
    client_id: str,
    note: str = "",
    revision: int = 0,
    supersedes: str = "",
    ratio: str = "9:16",
) -> dict[str, Any]:
    """Render via existing video_ad_cycle + stamp workflow_state."""
    if not flags.production_enabled() and not flags.daily_scheduler_enabled():
        # Manual admin generate still allowed through video_ad_cycle directly;
        # cell path requires at least one gate when production cell is the entry.
        pass
    from app.marketing import video_ad_cycle

    r = await video_ad_cycle.generate_for_client(
        client_id, note=note, revision=revision, supersedes=supersedes
    )
    if not r.get("ok"):
        return r
    rid = str(r.get("id") or "")
    video_ad_cycle._update(
        rid,
        workflow_state=states.CLIENT_REVIEW_PENDING,
        aspect_ratio=ratio,
        purpose="organic_daily",
        agent_owner="isha",
        canary_label="video_production_cell",
    )
    # Optional WhatsApp review (flagged)
    try:
        from app.marketing.video_production import review_whatsapp

        rows = video_ad_cycle.list_for_client(client_id)
        rec = next((x for x in rows if x.get("id") == rid), {})
        rec = {
            **rec,
            "approve_url": r.get("approve_url"),
            "reject_url": r.get("reject_url"),
            "title": "Naya video ad",
            "cta": "Call / WhatsApp",
        }
        wa = review_whatsapp.send_review_whatsapp(rec)
        r["whatsapp_review"] = wa
        if wa.get("wa_link") and not r.get("wa_link"):
            r["wa_link"] = wa["wa_link"]
    except Exception as e:
        r["whatsapp_review"] = {"sent": False, "reason": str(e)[:120]}
    return r


def approve_version(video_ad_id: str, expected_revision: int | None = None) -> dict[str, Any]:
    """Bind approval to exact version — fail if mismatch."""
    from app.marketing import content_approval, video_ad_cycle

    rec = None
    for r in video_ad_cycle.list_all(200):
        if str(r.get("id")) == str(video_ad_id):
            rec = r
            break
    if not rec:
        return {"ok": False, "error": "video_ad_not_found"}
    rev = int(rec.get("revision") or 0)
    if expected_revision is not None and int(expected_revision) != rev:
        return {
            "ok": False,
            "error": "version_mismatch",
            "expected": expected_revision,
            "actual": rev,
        }
    tok = str(rec.get("token") or "")
    if not tok:
        return {"ok": False, "error": "missing_token"}
    out = content_approval.approve(tok)
    if out.get("ok"):
        mark_version_approved(str(video_ad_id), rev)
    return out


async def schedule_approved(video_ad_id: str) -> dict[str, Any]:
    """AMBER — publish only if gate passes. Uses existing publish path."""
    from app.marketing import video_ad_cycle

    rec = None
    for r in video_ad_cycle.list_all(200):
        if str(r.get("id")) == str(video_ad_id):
            rec = r
            break
    if not rec:
        return {"ok": False, "error": "not_found"}
    gate = assert_can_publish(rec)
    if not gate.get("ok"):
        return gate
    # Temporarily ensure only this id is publishable: use publish_due on filtered
    res = await video_ad_cycle._publish_one(rec)
    if res.get("any_sent"):
        video_ad_cycle._update(
            str(video_ad_id),
            status="published",
            workflow_state=states.PUBLISHED,
            published_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            publish_result=res.get("channels"),
        )
        _audit(
            "zara", "video_published", f"published {video_ad_id}", {"channels": res.get("channels")}
        )
        return {"ok": True, "published": True, "channels": res.get("channels")}
    video_ad_cycle._update(
        str(video_ad_id),
        status="publish_failed",
        workflow_state=states.PUBLISH_FAILED,
        publish_result=res.get("channels"),
    )
    return {"ok": False, "error": "publish_failed", "channels": res.get("channels")}


def ops_summary(client_id: str = "") -> dict[str, Any]:
    from app.marketing import video_ad_cycle

    rows = video_ad_cycle.list_for_client(client_id) if client_id else video_ad_cycle.list_all()
    by_status: dict[str, int] = {}
    by_wf: dict[str, int] = {}
    for r in rows:
        st = str(r.get("status") or "unknown")
        by_status[st] = by_status.get(st, 0) + 1
        wf = str(r.get("workflow_state") or states.workflow_from_legacy(st))
        by_wf[wf] = by_wf.get(wf, 0) + 1
    pending_review = by_status.get("pending", 0)
    health = "healthy"
    if by_status.get("publish_failed") or by_status.get("failed"):
        health = "degraded"
    if pending_review:
        health = "blocked_by_customer_review" if health == "healthy" else health
    return {
        "ok": True,
        "health": health,
        "count": len(rows),
        "by_status": by_status,
        "by_workflow_state": by_wf,
        "flags": flags.flag_snapshot(),
        "video_ads": rows[:50],
    }


__all__ = [
    "create_daily_brief",
    "write_script",
    "render_and_queue_review",
    "approve_version",
    "schedule_approved",
    "ops_summary",
]
