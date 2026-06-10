"""Growth API — naye 2026 growth features ka surface (admin).

- Lead scoring / hot-leads (app/platform/lead_scoring.py)
- Review generation engine, sentiment-gated (app/marketing/review_engine.py)
- WhatsApp Flows send (app/marketing/whatsapp_flows.py — Meta-gated)
- Missed-call -> AI callback (app/telephony/missed_call.py — Vobiz-gated)

Sab additive + free + gated. Writes admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.api.ratelimit import rate_limit
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/growth", tags=["Growth"])


# ----------------------------- Lead scoring ----------------------------- #
@router.get("/leads/hot")
async def hot_leads(limit: int = 25, _user=Depends(require_admin)):
    """Top hot leads (0-100 scored, in-market prospects pe focus)."""
    from app.platform import lead_scoring

    return await lead_scoring.top_hot_leads(limit)


@router.post("/leads/rescore")
async def rescore_leads(limit: int = 500, _user=Depends(require_admin)):
    """Saare leads ko rescore karke lead_score + is_hot_lead DB me update karo."""
    from app.platform import lead_scoring

    return await lead_scoring.rescore_db(limit)


class ScoreOneIn(BaseModel):
    lead: dict


@router.post("/leads/score")
async def score_one(body: ScoreOneIn, _user=Depends(require_admin)):
    """Ek lead-dict ka live score + breakdown (debug/preview)."""
    from app.platform import lead_scoring

    s = lead_scoring.score_lead(body.lead)
    return {"score": s, "is_hot": lead_scoring.is_hot(s), "components": lead_scoring.score_components(body.lead)}


# ----------------------------- Review engine ---------------------------- #
class ReviewReqIn(BaseModel):
    business_name: str
    place_query: str | None = None
    customer_name: str | None = ""
    customer_phone: str | None = ""
    sentiment_score: int | None = None  # 1-5; <4 => private feedback
    auto_send: bool | None = None


@router.post("/review/request")
async def review_request(body: ReviewReqIn, _user=Depends(require_admin)):
    """Sentiment-gated review request banao (happy->Google, unhappy->private)."""
    from app.marketing import review_engine

    return await review_engine.request_review(
        business_name=body.business_name,
        place_query=body.place_query,
        customer_name=body.customer_name or "",
        customer_phone=body.customer_phone or "",
        sentiment_score=body.sentiment_score,
        auto_send=body.auto_send,
    )


@router.get("/review/requests")
async def review_requests(limit: int = 100, _user=Depends(require_admin)):
    from app.marketing import review_engine

    return {"requests": review_engine.list_requests(limit)}


# --------------------------- WhatsApp Flows ----------------------------- #
class FlowSendIn(BaseModel):
    to_number: str
    cta: str | None = "Enquiry karein"


@router.post("/whatsapp/flow/send")
async def whatsapp_flow_send(body: FlowSendIn, _user=Depends(require_admin)):
    """In-chat lead-capture Flow bhejo (Meta-gated; flow_id/creds na ho -> inert)."""
    from app.marketing import whatsapp_flows

    return await whatsapp_flows.send_flow(body.to_number, flow_cta=body.cta or "Enquiry karein")


# --------------------------- Missed-call callback ----------------------- #
class MissedCallIn(BaseModel):
    from_number: str
    niche: str | None = "general"
    business: str | None = ""


@router.post("/missed-call")
async def missed_call(body: MissedCallIn, _user=Depends(require_admin)):
    """Missed-call -> lead capture + (gated) instant AI callback. Telephony webhook
    isi ko call karega; abhi admin test endpoint."""
    if not (body.from_number or "").strip():
        raise HTTPException(status_code=422, detail="from_number chahiye.")
    from app.telephony.missed_call import handle_missed_call

    return await handle_missed_call(body.from_number, body.niche or "general", body.business or "")


# ---------------------- Niche-driven automation ------------------------- #
@router.get("/niches")
async def list_niches(tier: str | None = None, _user=Depends(require_admin)):
    """Saare niches overview — keywords (scraping) + content_focus (marketing)."""
    try:
        from app.niches import NICHES
    except Exception:
        return {"niches": []}
    out = []
    for k, c in NICHES.items():
        if not isinstance(c, dict):
            continue
        if tier and str(c.get("tier", "")).upper() != tier.upper():
            continue
        out.append(
            {
                "id": k,
                "name": c.get("name"),
                "tier": c.get("tier"),
                "category": c.get("category"),
                "keywords": c.get("keywords") or [],
                "content_focus": c.get("content_focus") or [],
            }
        )
    return {"count": len(out), "niches": out}


class NicheScrapeIn(BaseModel):
    tier: str | None = None
    batch: int = 8
    limit_per_query: int = 6


@router.post("/niche/scrape")
async def niche_scrape(body: NicheScrapeIn, _user=Depends(require_admin)):
    """Next niche-batch scrape karo (all-niche rotation, existing prospector se)."""
    from app.platform import niche_prospector

    return await niche_prospector.run(
        tier=body.tier, batch=body.batch, limit_per_query=body.limit_per_query
    )


@router.get("/niche/pack/{niche_key}")
async def niche_pack_one(niche_key: str, count: int = 4, city: str = "", _user=Depends(require_admin)):
    """Ek niche ka poora marketing pack (content_focus posts + hashtags + offer)."""
    from app.marketing import niche_pack

    return await niche_pack.build_pack(niche_key, city=city, count=count)


class NichePacksIn(BaseModel):
    tier: str | None = None
    limit: int = 6


@router.post("/niche/packs")
async def niche_packs(body: NichePacksIn, _user=Depends(require_admin)):
    """Multiple niches ke marketing packs (LLM-heavy; tier filter + limit)."""
    from app.marketing import niche_pack

    return await niche_pack.build_all(tier=body.tier, limit=body.limit)


# ------------------- Forward Deployed Engineer (FDE) agents ------------- #
@router.get("/fde/agents")
async def fde_agents(_user=Depends(require_admin)):
    """FDE personas (Isha/Veer/Aarav/Neo) + unke skills (automation/marketing/website)."""
    from app.agents import fde

    return {"agents": fde.list_agents(), "skills": fde.list_skills()}


class FdeDeployIn(BaseModel):
    business_name: str | None = None
    niche: str | None = "general"
    city: str | None = ""
    slug: str | None = None
    client_id: str | None = None
    agent: str | None = "neo"   # isha_fde | veer | aarav | neo
    brief: str | None = ""      # NL brief — FDE plan isi se banata


@router.post("/fde/deploy")
async def fde_deploy(body: FdeDeployIn, _user=Depends(require_admin)):
    """FDE agent ko ek client ke liye automation+marketing+website 'deploy' karne bolo.

    Brief do (e.g. 'naye solar client ka full marketing setup') → FDE plan banata +
    skills chalata (existing capabilities). Ban-safe (drafts/setup, auto-publish nahi).
    """
    from app.agents import fde

    ctx = {
        "business_name": body.business_name,
        "niche": body.niche,
        "city": body.city,
        "slug": body.slug,
        "client_id": body.client_id,
    }
    return await fde.deploy(ctx, agent=body.agent or "neo", brief=body.brief or "")


# ---------------- Omnichannel Cadence Orchestrator --------------------- #
class CadenceEnrollIn(BaseModel):
    leads: list[dict] | None = None
    from_prospects: int = 0   # >0 → top N prospects auto-enroll


@router.post("/cadence/enroll")
async def cadence_enroll(body: CadenceEnrollIn, _user=Depends(require_admin)):
    """Leads ko omnichannel cadence pe daalo (ya top-N prospects auto)."""
    from app.marketing import cadence

    leads = list(body.leads or [])
    if body.from_prospects and body.from_prospects > 0:
        try:
            from app.platform import prospector

            rows = [r for r in prospector._read_all() if r.get("phone")][: body.from_prospects]
            leads.extend(rows)
        except Exception:
            pass
    n = cadence.enroll_many(leads)
    return {"ok": True, "enrolled": n, "stats": cadence.stats()}


@router.post("/cadence/run")
async def cadence_run(_user=Depends(require_admin)):
    """Due cadence steps advance karo (drafts/sends). GATED CADENCE_ENGINE=1."""
    from app.marketing import cadence

    return await cadence.run_due()


@router.get("/cadence")
async def cadence_status(_user=Depends(require_admin)):
    from app.marketing import cadence

    return {"stats": cadence.stats(), "cadence": cadence.DEFAULT_CADENCE, "recent_runs": cadence.list_runs(30)}


# ---------------- SMS (DLT) / LinkedIn / SEO channels ------------------ #
class SmsIn(BaseModel):
    to: str
    template: str = "intro"
    business_name: str | None = ""


@router.post("/sms/send")
async def sms_send(body: SmsIn, _user=Depends(require_admin)):
    """DLT SMS bhejo (creds/flag na ho -> inert). Ready-to-flip."""
    from app.integrations import sms_dlt

    return await sms_dlt.send_template(body.to, body.template, biz=body.business_name or "ji")


class LinkedInIn(BaseModel):
    target_name: str
    company: str | None = ""
    niche: str | None = "general"


@router.post("/linkedin/draft")
async def linkedin_draft(body: LinkedInIn, _user=Depends(require_admin)):
    """LinkedIn comment + connect-note + DM drafts (ban-safe, manual send)."""
    from app.marketing import linkedin_assist

    return await linkedin_assist.draft_outreach(body.target_name, body.company or "", body.niche or "general")


class SeoPageIn(BaseModel):
    niche: str
    city: str = "Pune"


@router.post("/seo/page")
async def seo_page(body: SeoPageIn, _user=Depends(require_admin)):
    """Ek niche×city SEO landing page generate karo (inbound)."""
    from app.marketing import seo_pages

    return await seo_pages.generate_page(body.niche, body.city)


class SeoBatchIn(BaseModel):
    tier: str | None = None
    limit: int = 6


@router.post("/seo/batch")
async def seo_batch(body: SeoBatchIn, _user=Depends(require_admin)):
    """Multiple niche×city SEO pages (LLM-heavy; limit)."""
    from app.marketing import seo_pages

    return await seo_pages.generate_batch(tier=body.tier, limit=body.limit)


# ---------------- Partnerships / reseller (B2B2B) --------------------- #
class PartnerIn(BaseModel):
    partner_type: str = "ca"
    partner_name: str | None = ""
    city: str | None = ""


@router.get("/partnership/types")
async def partnership_types(_user=Depends(require_admin)):
    from app.marketing import partnerships

    return {"types": partnerships.list_partner_types()}


@router.post("/partnership/draft")
async def partnership_draft(body: PartnerIn, _user=Depends(require_admin)):
    from app.marketing import partnerships

    return await partnerships.draft_partnership(body.partner_type, body.partner_name or "", body.city or "")


@router.post("/partnership/batch")
async def partnership_batch(city: str = "", _user=Depends(require_admin)):
    from app.marketing import partnerships

    return await partnerships.draft_batch(city=city)


# ---------------- Free lead-magnet tools (PUBLIC, inbound) ------------ #
class MissedCallIn2(BaseModel):
    missed_per_day: float
    avg_deal_value: float
    close_rate: float = 0.2


@router.post("/tools/missed-call-revenue", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))])
async def tool_missed_call(body: MissedCallIn2):
    """PUBLIC lead-magnet: missed-call revenue calculator."""
    from app.marketing import lead_tools

    return lead_tools.missed_call_revenue(body.missed_per_day, body.avg_deal_value, body.close_rate)


class LeadCostIn(BaseModel):
    current_cost_per_lead: float
    leads_per_month: float


@router.post("/tools/lead-cost", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))])
async def tool_lead_cost(body: LeadCostIn):
    """PUBLIC: lead-cost savings calculator."""
    from app.marketing import lead_tools

    return lead_tools.lead_cost_savings(body.current_cost_per_lead, body.leads_per_month)


class GoogleScoreIn(BaseModel):
    business_name: str
    city: str | None = ""


@router.post("/tools/google-score", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))])
async def tool_google_score(body: GoogleScoreIn):
    """PUBLIC: Google-presence checker."""
    from app.marketing import lead_tools

    return await lead_tools.google_presence_score(body.business_name, body.city or "")


# ---------------- Affiliate / referral program ----------------------- #
class AffiliateIn(BaseModel):
    name: str
    email: str | None = ""
    phone: str | None = ""


@router.post("/affiliate/register", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))])
async def affiliate_register(body: AffiliateIn):
    """PUBLIC: koi bhi affiliate ban sakta → referral link + commission."""
    from app.marketing import affiliate

    return affiliate.register_affiliate(body.name, body.email or "", body.phone or "")


@router.get("/weather-angle", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))])
async def weather_angle_ep(city: str = "Mumbai"):
    """PUBLIC: city ka aaj ka mausam → marketing content angle (Open-Meteo, free, no key, India)."""
    from app.marketing import weather_angle as wa

    return await wa.weather_angle(city)


@router.get("/affiliate/stats")
async def affiliate_stats(code: str | None = None, _user=Depends(require_admin)):
    from app.marketing import affiliate

    return {"stats": affiliate.stats(code), "affiliates": affiliate.list_affiliates(50)}


# ---------------- Community / Q&A content drafter -------------------- #
class CommunityIn(BaseModel):
    platform: str = "quora"
    topic: str | None = ""
    niche: str | None = "general"


@router.post("/community/draft")
async def community_draft(body: CommunityIn, _user=Depends(require_admin)):
    from app.marketing import community_content

    return await community_content.draft_content(body.platform, body.topic or "", body.niche or "general")


@router.post("/community/batch")
async def community_batch(body: CommunityIn, _user=Depends(require_admin)):
    from app.marketing import community_content

    return await community_content.draft_batch(topic=body.topic or "", niche=body.niche or "general")


# ==================== SALES AUTOMATION (conversion) =================== #
class DealIn(BaseModel):
    lead: dict
    stage: str = "interested"


@router.post("/sales/deal")
async def sales_deal(body: DealIn, _user=Depends(require_admin)):
    """Interested lead ko deal banao (pipeline me daalo)."""
    from app.marketing import sales_pipeline

    return {"ok": True, "deal": sales_pipeline.upsert_deal(body.lead, body.stage)}


class StageIn(BaseModel):
    stage: str


@router.post("/sales/deal/{deal_id}/stage")
async def sales_stage(deal_id: str, body: StageIn, _user=Depends(require_admin)):
    from app.marketing import sales_pipeline

    if not sales_pipeline.set_stage(deal_id, body.stage):
        raise HTTPException(status_code=404, detail="deal/stage invalid")
    return {"ok": True}


@router.get("/sales/deals")
async def sales_deals(stage: str | None = None, _user=Depends(require_admin)):
    from app.marketing import sales_pipeline

    return {"stats": sales_pipeline.stats(), "deals": sales_pipeline.list_deals(stage),
            "recent_actions": sales_pipeline.list_actions(30)}


@router.post("/sales/run")
async def sales_run(_user=Depends(require_admin)):
    """Pipeline advance: active deals ke auto next-actions generate karo. GATED SALES_ENGINE."""
    from app.marketing import sales_pipeline

    return await sales_pipeline.run_pipeline()


class ProposalIn(BaseModel):
    business_name: str
    niche: str | None = "general"
    city: str | None = ""
    plan: str | None = "growth"


@router.post("/sales/proposal")
async def sales_proposal(body: ProposalIn, _user=Depends(require_admin)):
    """Auto personalized proposal + payment/demo links."""
    from app.marketing import proposal

    return await proposal.generate_proposal(body.business_name, body.niche or "general", body.city or "", body.plan or "growth")


class SalesMsgIn(BaseModel):
    message: str
    business_name: str | None = ""
    niche: str | None = "general"


@router.post("/sales/assistant")
async def sales_assistant_reply(body: SalesMsgIn, _user=Depends(require_admin)):
    """AI sales-closer: prospect message → objection-aware reply + CTA."""
    from app.marketing import sales_assistant

    return await sales_assistant.handle_message(body.message, body.business_name or "", body.niche or "general")


# ------------------- Revenue automation (dunning/health/lifecycle/digest) ------------------- #
class DunningCaseIn(BaseModel):
    client_id: str
    amount: float | None = None
    gateway: str | None = ""
    reason: str | None = ""


@router.post("/revenue/dunning/case")
async def dunning_open_case(body: DunningCaseIn, _user=Depends(require_admin)):
    """Manual dunning case (webhook ke bahar se) — recovery sequence shuru."""
    from app.billing import dunning

    return await dunning.on_payment_failed(body.client_id, body.amount, body.gateway or "", body.reason or "")


@router.post("/revenue/dunning/run")
async def dunning_run(_user=Depends(require_admin)):
    """Dunning sweep abhi chalao (gated DUNNING_ENGINE — off = no-op)."""
    from app.billing import dunning

    return await dunning.run_due()


@router.get("/revenue/dunning")
async def dunning_overview(_user=Depends(require_admin)):
    """Dunning stats + open cases."""
    from app.billing import dunning

    return dunning.stats()


@router.get("/revenue/health/clients")
async def client_health_report(_user=Depends(require_admin)):
    """Saare clients ka churn-risk health score (red pehle)."""
    from app.platform import client_health

    return await client_health.health_report()


@router.post("/revenue/health/run")
async def client_health_run(_user=Depends(require_admin)):
    """Health check + (gated CLIENT_HEALTH_ALERTS) red-client email alert."""
    from app.platform import client_health

    return await client_health.run_check()


class LifecycleEnrollIn(BaseModel):
    email: str
    business_name: str | None = ""
    client_id: str | None = ""
    plan: str | None = "starter"


@router.post("/revenue/lifecycle/enroll")
async def lifecycle_enroll(body: LifecycleEnrollIn, _user=Depends(require_admin)):
    """Manually kisi signup ko nurture sequence me daalo."""
    from app.marketing import lifecycle_nurture

    return lifecycle_nurture.enroll(body.email, body.business_name or "", body.client_id or "", body.plan or "starter")


@router.post("/revenue/lifecycle/run")
async def lifecycle_run(_user=Depends(require_admin)):
    """Nurture sweep abhi chalao (gated LIFECYCLE_NURTURE — off = no-op)."""
    from app.marketing import lifecycle_nurture

    return await lifecycle_nurture.run_due()


@router.get("/revenue/lifecycle")
async def lifecycle_overview(_user=Depends(require_admin)):
    """Nurture funnel stats."""
    from app.marketing import lifecycle_nurture

    return lifecycle_nurture.stats()


@router.post("/revenue/digest/run")
async def revenue_digest_run(_user=Depends(require_admin)):
    """Revenue digest abhi banao+bhejo (force — gate/dedupe skip)."""
    from app.platform import revenue_digest

    return await revenue_digest.run(force=True)


# ------------- Self-healing growth optimizer + channel experiments ------------- #
@router.get("/optimizer/analysis")
async def optimizer_analysis(_user=Depends(require_admin)):
    """Funnel snapshot + weakest-stage diagnosis (read-only, koi action nahi)."""
    from app.agents import growth_optimizer

    snap = await growth_optimizer.funnel_snapshot()
    return {"snapshot": snap, "weakest": growth_optimizer.weakest_stage(snap)}


@router.post("/optimizer/run")
async def optimizer_run(_user=Depends(require_admin)):
    """Self-healing profit loop abhi chalao (gated GROWTH_OPTIMIZER — off = no-op)."""
    from app.agents import growth_optimizer

    return await growth_optimizer.optimize()


@router.get("/optimizer/runs")
async def optimizer_runs(limit: int = 20, _user=Depends(require_admin)):
    """Recent optimizer runs + ideas."""
    from app.agents import growth_optimizer

    return {"runs": growth_optimizer.recent_runs(limit), "ideas": growth_optimizer.recent_ideas(30)}


@router.post("/experiments/run")
async def experiments_run(n: int = 3, _user=Depends(require_admin)):
    """Channel experiments abhi launch karo (gated CHANNEL_EXPERIMENTS)."""
    from app.marketing import channel_experiments

    return await channel_experiments.run_daily(max(1, min(n, 5)))


@router.get("/experiments")
async def experiments_overview(_user=Depends(require_admin)):
    """Per-channel bandit stats + recent experiments."""
    from app.marketing import channel_experiments

    return {"stats": channel_experiments.stats(), "recent": channel_experiments.recent(30)}


class OutcomeIn(BaseModel):
    channel: str
    kind: str | None = "inquiry"
    value: int | None = 1
    note: str | None = ""


@router.post("/experiments/outcome")
async def experiments_outcome(body: OutcomeIn, _user=Depends(require_admin)):
    """Channel outcome record karo (inquiry/reply/signup attribution) — bandit seekhta."""
    from app.marketing import channel_experiments

    return channel_experiments.record_outcome(body.channel, body.kind or "inquiry", body.value or 1, body.note or "")


# ---------------- Competitor-parity content (carousel/meme/multilang) ---------------- #
class CarouselIn(BaseModel):
    business_name: str
    niche: str | None = "general"
    topic: str | None = ""
    slides: int | None = 4


@router.post("/content/carousel")
async def content_carousel(body: CarouselIn, _user=Depends(require_admin)):
    """Predis-style carousel pack: 3-5 branded SVG slides + caption."""
    from app.marketing import carousel

    return await carousel.generate_carousel(body.business_name, body.niche or "general", body.topic or "", body.slides or 4)


class MemeIn(BaseModel):
    business_name: str | None = ""
    niche: str | None = "general"
    topic: str | None = ""


@router.post("/content/meme")
async def content_meme(body: MemeIn, _user=Depends(require_admin)):
    """Desi business meme (SVG + caption + hashtags)."""
    from app.marketing import meme_gen

    return await meme_gen.generate_meme(body.business_name or "", body.niche or "general", body.topic or "")


class MultilangIn(BaseModel):
    caption: str
    langs: list[str] | None = None


@router.post("/content/multilang")
async def content_multilang(body: MultilangIn, _user=Depends(require_admin)):
    """Caption → Hindi/Marathi/Hinglish versions (local reach 2-3x)."""
    from app.marketing import multilang_post

    return await multilang_post.translate_post(body.caption, body.langs)


# ---------------- Deliverability / bookings / reviews / webhooks ---------------- #
@router.get("/deliverability")
async def deliverability_check(_user=Depends(require_admin)):
    """SPF/DMARC + IP blacklist check abhi chalao (Smartlead-pattern)."""
    from app.platform import deliverability_monitor

    return await deliverability_monitor.run_check()


@router.get("/bookings/upcoming")
async def bookings_upcoming(_user=Depends(require_admin)):
    from app.platform import booking_reminders

    return booking_reminders.upcoming(30)


@router.post("/bookings/remind-run")
async def bookings_remind_run(_user=Depends(require_admin)):
    """Booking reminders sweep (gated BOOKING_REMINDERS)."""
    from app.platform import booking_reminders

    return await booking_reminders.run_due()


@router.post("/reviews/monitor-run")
async def reviews_monitor_run(_user=Depends(require_admin)):
    """Naye Google reviews check + AI reply drafts (gated REVIEW_MONITOR)."""
    from app.marketing import review_monitor

    return await review_monitor.run_check()


@router.get("/reviews/drafts")
async def reviews_drafts(_user=Depends(require_admin)):
    from app.marketing import review_monitor

    return review_monitor.recent_drafts(30)


class WebhookIn(BaseModel):
    url: str
    events: list[str] | None = None
    client_id: str | None = ""
    secret: str | None = ""


@router.post("/webhooks/register")
async def webhooks_register(body: WebhookIn, _user=Depends(require_admin)):
    """Zapier-style outbound webhook register (https only, HMAC-signed)."""
    from app.platform import outbound_webhooks

    return outbound_webhooks.register(body.url, body.events, body.client_id or "", body.secret or "")


@router.get("/webhooks")
async def webhooks_list(_user=Depends(require_admin)):
    from app.platform import outbound_webhooks

    return {"webhooks": outbound_webhooks.list_webhooks(), "deliveries": outbound_webhooks.recent_deliveries(20)}


@router.delete("/webhooks/{webhook_id}")
async def webhooks_remove(webhook_id: str, _user=Depends(require_admin)):
    from app.platform import outbound_webhooks

    return {"removed": outbound_webhooks.remove(webhook_id)}


# ---------------- PUBLIC: AI website audit (lead magnet) ---------------- #
class SiteAuditIn(BaseModel):
    url: str


@router.post("/tools/website-audit", dependencies=[Depends(rate_limit("site_audit", 10, 60))])
async def website_audit_public(body: SiteAuditIn):
    """PUBLIC lead magnet: website URL → score + Hinglish tips + CTA."""
    from app.marketing import website_auditor

    return await website_auditor.audit_url(body.url)


# ---------------- AI-automation infra (observability/health/DLQ/flags) ---------------- #
@router.get("/infra/llm")
async def infra_llm_metrics(window: int = 2000, _user=Depends(require_admin)):
    """LLM observability: per-provider calls/ok-rate/latency/fallback-rate."""
    from app.platform import llm_metrics

    return llm_metrics.stats(max(100, min(window, 10000)))


@router.get("/infra/automation-health")
async def infra_automation_health(_user=Depends(require_admin)):
    """Dead-man switch: har scheduled job ka last-run + overdue status."""
    from app.platform import automation_health

    return automation_health.health()


@router.get("/infra/dlq")
async def infra_dlq(limit: int = 50, _user=Depends(require_admin)):
    """Failed Celery tasks (Redis dlq:failed_tasks) inspect karo."""
    out: dict = {"count": 0, "items": []}
    try:
        import json as _json

        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        out["count"] = int(r.llen("dlq:failed_tasks") or 0)
        for raw in r.lrange("dlq:failed_tasks", 0, max(0, min(limit, 200)) - 1) or []:
            try:
                out["items"].append(_json.loads(raw))
            except Exception:
                pass
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


@router.post("/infra/dlq/retry")
async def infra_dlq_retry(limit: int = 10, _user=Depends(require_admin)):
    """DLQ se staff-jobs dobara dispatch karo (jo parse ho sakein); baaki skip."""
    retried, skipped = [], 0
    try:
        import json as _json

        import redis as _redis

        from app.config import settings
        from app.tasks.staff_jobs import STAFF_JOBS

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        for _ in range(max(1, min(limit, 50))):
            raw = r.rpop("dlq:failed_tasks")
            if not raw:
                break
            job = None
            try:
                rec = _json.loads(raw)
                args_s = str(rec.get("args") or "")
                job = next((j for j in STAFF_JOBS if f"'{j}'" in args_s or f'"{j}"' in args_s), None)
            except Exception:
                pass
            if job:
                try:
                    from app.worker import celery_app

                    celery_app.send_task("app.tasks.staff_jobs.run_staff_job", args=[job])
                    retried.append(job)
                    continue
                except Exception:
                    pass
            skipped += 1
    except Exception as e:
        return {"error": str(e)[:120], "retried": retried, "skipped": skipped}
    return {"retried": retried, "skipped": skipped}


@router.delete("/infra/dlq")
async def infra_dlq_purge(_user=Depends(require_admin)):
    """DLQ poora khali karo."""
    try:
        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        n = int(r.llen("dlq:failed_tasks") or 0)
        r.delete("dlq:failed_tasks")
        return {"purged": n}
    except Exception as e:
        return {"error": str(e)[:120]}


# Saare gated automation flags ka registry — live env status ek jagah.
AUTOMATION_FLAGS = [
    "TEAM_AUTOMATION", "RUN_IN_PROCESS_SCHEDULER", "NICHE_ROTATION", "AUTO_EMAIL_OUTREACH",
    "JOURNEY_ENGINE", "AUTO_QUALIFY_CALLS", "REPLY_AGENT", "OPS_WATCHDOG", "AUTO_ONBOARD",
    "USE_STRUCTURED_CONTENT", "USE_AGENTIC_RAG", "USE_LANGGRAPH_SUPERVISOR", "AGENT_STANDUP",
    "SALES_ENGINE", "CADENCE_ENGINE", "DUNNING_ENGINE", "LIFECYCLE_NURTURE",
    "CLIENT_HEALTH_ALERTS", "REVENUE_DIGEST", "GROWTH_OPTIMIZER", "CHANNEL_EXPERIMENTS",
    "REVIEW_MONITOR", "BOOKING_REMINDERS", "DELIVERABILITY_MONITOR", "AUTOMATION_HEALTH_ALERTS",
    "WHATSAPP_AUTO_SEND", "MISSED_CALL_CALLBACK", "SMS_DLT_ENABLED", "USE_SILERO_VAD",
    "USE_SMART_TURN", "USE_LIGHTRAG", "ENABLE_OTEL", "ENABLE_LEGACY_BEAT", "FESTIVALS_LIVE_HOLIDAYS",
]


@router.get("/revenue/summary")
async def revenue_summary(_user=Depends(require_admin)):
    """Ops-dashboard ke liye compact revenue snapshot (digest ka collect reuse)."""
    from app.platform import revenue_digest

    stats = await revenue_digest._collect()
    return stats


@router.get("/inbox")
async def action_inbox(_user=Depends(require_admin)):
    """Aaj ke 1-click actions ek jagah: hot leads + reply drafts + review drafts +
    pending experiments. Sumit ka roz ka manual kaam = sirf approvals."""
    out: dict = {"hot_leads": [], "reply_drafts": [], "review_drafts": [], "recent_experiments": []}
    try:
        from app.platform import lead_scoring

        out["hot_leads"] = (await lead_scoring.top_hot_leads(5)) or []
    except Exception:
        pass
    try:
        import json as _json
        import os as _os

        p = _os.path.join("data", "reply_drafts.jsonl")
        if _os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                rows = [_json.loads(x) for x in f.readlines()[-5:] if x.strip()]
            out["reply_drafts"] = rows[::-1]
    except Exception:
        pass
    try:
        from app.marketing import review_monitor

        out["review_drafts"] = review_monitor.recent_drafts(5)
    except Exception:
        pass
    try:
        from app.marketing import channel_experiments

        out["recent_experiments"] = channel_experiments.recent(5)
    except Exception:
        pass
    return out


@router.get("/infra/telephony-readiness")
async def infra_telephony_readiness(_user=Depends(require_admin)):
    """Tara: calling-launch readiness score + missing checklist + next-actions."""
    from app.telephony import telephony_readiness

    return telephony_readiness.run_checks()


@router.get("/infra/flags")
async def infra_flags(_user=Depends(require_admin)):
    """Saare automation flags ka live status (on/off/unset) ek nazar me."""
    import os as _os

    out = {}
    for f in AUTOMATION_FLAGS:
        v = _os.environ.get(f)
        out[f] = {"set": v is not None, "on": (v or "").strip().lower() in ("1", "true", "yes"), "value": v}
    on = [k for k, d in out.items() if d["on"]]
    return {"on_count": len(on), "on": on, "flags": out}
