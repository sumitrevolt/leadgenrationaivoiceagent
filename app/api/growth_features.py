"""Growth feature endpoints — marketing-AI upgrades (feedback/trends/reel/personalize),
loyalty/coupons, client reports, client API keys, NPS, IndexNow.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit

router = APIRouter(tags=["Growth"])


# ------------- Marketing AI upgrades: feedback loop / trends / reel / KB-post ------------- #
class FeedbackIn(BaseModel):
    theme: str
    worked: bool
    format: str = "post"
    niche: str = ""
    post_id: str = ""
    channel: str = ""
    note: str = ""


@router.post("/content/feedback")
async def content_feedback_record(body: FeedbackIn, _user=Depends(require_admin)):
    """1-click 'post chala/nahi' — theme-level learning + channel bandit credit."""
    from app.marketing import content_feedback

    return content_feedback.record_feedback(
        body.theme, body.worked, body.format, body.niche, body.post_id, body.channel, body.note
    )


@router.get("/content/feedback/stats")
async def content_feedback_stats(niche: str = "", _user=Depends(require_admin)):
    from app.marketing import content_feedback

    return content_feedback.theme_stats(niche)


@router.get("/content/trends")
async def content_trends(
    niche: str = "general", business_name: str = "", _user=Depends(require_admin)
):
    """Google Trends (IN) → niche ke liye fresh Hinglish content angles."""
    from app.marketing import trends

    return await trends.trend_angles(niche, business_name)


class ReelIn(BaseModel):
    business_name: str
    niche: str = "general"
    slides: list[str] | None = None
    offer: str = ""
    client_id: str = ""


@router.post("/content/reel-video")
async def content_reel_video(body: ReelIn, _user=Depends(require_admin)):
    """Faceless reel MP4 (PIL+EdgeTTS+ffmpeg) — heavy, human upload karta hai."""
    from app.marketing import reel_video

    return await reel_video.build_reel(
        body.business_name, body.niche, body.slides, body.offer, body.client_id
    )


class PersonalizeIn(BaseModel):
    client_id: str
    occasion: str = ""
    offer: str = ""


@router.post("/content/personalize")
async def content_personalize(body: PersonalizeIn, _user=Depends(require_admin)):
    """Client-KB facts ke saath personalized post (AUTO_ONBOARD seeded KB reuse)."""
    from app.marketing import kb_personalize

    return await kb_personalize.personalized_post(body.client_id, body.occasion, body.offer)


# ------------- Competitor-parity batch-2: templates / loyalty / reports / client API keys ------------- #
@router.get("/content/templates")
async def content_templates(niche: str = "", occasion: str = "", _user=Depends(require_admin)):
    """Curated template gallery (AdBanao-style) — studio prefill ke liye."""
    from app.marketing import template_library

    return template_library.list_templates(niche, occasion)


class CouponIn(BaseModel):
    client_id: str
    title: str
    kind: str = "percent"
    value: int = 10
    expiry_days: int = 30
    max_redemptions: int = 100


@router.post("/loyalty/campaign")
async def loyalty_create(body: CouponIn, _user=Depends(require_admin)):
    """SMB ke end-customers ke liye coupon campaign (share_text 1-click WA)."""
    from app.marketing import loyalty

    return loyalty.create_campaign(
        body.client_id, body.title, body.kind, body.value, body.expiry_days, body.max_redemptions
    )


@router.get("/loyalty")
async def loyalty_stats(client_id: str = "", _user=Depends(require_admin)):
    from app.marketing import loyalty

    return loyalty.stats(client_id)


@router.get("/loyalty/check/{code}", dependencies=[Depends(rate_limit("loycheck", 30, 60))])
async def loyalty_check(code: str):
    """PUBLIC: counter pe staff coupon-code verify kare."""
    from app.marketing import loyalty

    return loyalty.check_code(code)


class RedeemIn(BaseModel):
    code: str
    customer_phone: str = ""
    referrer_phone: str = ""
    note: str = ""


@router.post("/loyalty/redeem", dependencies=[Depends(rate_limit("loyredeem", 20, 60))])
async def loyalty_redeem(body: RedeemIn):
    """PUBLIC (rate-limited): redemption record."""
    from app.marketing import loyalty

    return loyalty.redeem(body.code, body.customer_phone, body.referrer_phone, body.note)


class ReportIn(BaseModel):
    client_id: str
    month: str = ""
    send: bool | None = None


@router.post("/revenue/client-report")
async def client_report_build(body: ReportIn, _user=Depends(require_admin)):
    """White-label monthly client report (HTML + optional email, CLIENT_REPORTS gate)."""
    from app.marketing import client_report

    return await client_report.build_report(body.client_id, body.month, body.send)


@router.post("/revenue/client-reports/run")
async def client_reports_run(send: bool | None = None, _user=Depends(require_admin)):
    from app.marketing import client_report

    return await client_report.run_monthly(send)


class KeyIn(BaseModel):
    client_id: str
    name: str = "default"


@router.post("/client-keys")
async def client_key_issue(body: KeyIn, _user=Depends(require_admin)):
    """Client-facing API key issue (plain key sirf is response me)."""
    from app.platform import client_api_keys

    return client_api_keys.issue(body.client_id, body.name)


@router.get("/client-keys")
async def client_keys_list(client_id: str = "", _user=Depends(require_admin)):
    from app.platform import client_api_keys

    return {"keys": client_api_keys.list_keys(client_id)}


@router.delete("/client-keys/{hash_prefix}")
async def client_key_revoke(hash_prefix: str, _user=Depends(require_admin)):
    from app.platform import client_api_keys

    return client_api_keys.revoke(hash_prefix)


@router.get("/client-data/summary", dependencies=[Depends(rate_limit("clientdata", 30, 60))])
async def client_data_summary(key: str):
    """PUBLIC key-authed (Zapier-style): client apna data pull kare apni API key se."""
    from app.marketing import client_report, clients_store
    from app.platform import client_api_keys

    cid = client_api_keys.verify(key)
    if not cid:
        raise HTTPException(status_code=401, detail="invalid api key")
    client = clients_store.get_client(cid) or {}
    return {
        "client_id": cid,
        "business_name": client.get("business_name"),
        "stats": client_report.collect_stats(client),
    }


# ------------- Prod-batch 2026-06-10: NPS + payment recon + IndexNow ------------- #
class NPSIn(BaseModel):
    score: int
    comment: str | None = ""
    name: str | None = ""
    phone: str | None = ""
    client_slug: str | None = ""


@router.post(
    "/nps/submit", tags=["Public Tools"], dependencies=[Depends(rate_limit("nps", 10, 60))]
)
async def nps_submit(body: NPSIn):
    """PUBLIC: NPS/CSAT response (0-10). Detractor alert gated NPS_ALERTS=1."""
    from app.platform import nps

    return await nps.submit(
        body.score, body.comment or "", body.name or "", body.phone or "", body.client_slug or ""
    )


@router.get("/nps/stats")
async def nps_stats(client_slug: str = "", days: int = 90, _user=Depends(require_admin)):
    """NPS score + recent responses (overall ya per-client)."""
    from app.platform import nps

    return nps.stats(client_slug, days)


@router.get("/nps/request-drafts")
async def nps_request_drafts(limit: int = 20, _user=Depends(require_admin)):
    """Har client ke liye 1-click WhatsApp survey draft (ban-safe, manual send)."""
    from app.platform import nps

    return {"drafts": nps.request_drafts(limit)}


# /revenue/recon + /revenue/recon/run routes removed 2026-06-18 — Razorpay gateway
# gone, so there is no payment rail to reconcile against (payments via manual UPI).


class IndexNowIn(BaseModel):
    urls: list[str] | None = None  # khali = poora sitemap sweep


@router.post("/seo/indexnow")
async def seo_indexnow(body: IndexNowIn, _user=Depends(require_admin)):
    """Bing/Yandex IndexNow submit — urls do ya khali chodo (sitemap sweep)."""
    from app.marketing import indexnow

    if body.urls:
        return await indexnow.submit_urls(body.urls)
    return await indexnow.submit_sitemap_if_enabled(force=True)  # admin manual = flag bypass
