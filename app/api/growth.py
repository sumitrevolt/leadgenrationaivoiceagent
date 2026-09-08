"""Growth API â€” naye 2026 growth features ka surface (admin).

- Lead scoring / hot-leads (app/platform/lead_scoring.py)
- Review generation engine, sentiment-gated (app/marketing/review_engine.py)
- WhatsApp Flows send (app/marketing/whatsapp_flows.py â€” Meta-gated)
- Missed-call -> AI callback (app/telephony/missed_call.py â€” Vobiz-gated)

Sab additive + free + gated. Writes admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin, require_super_admin
from app.api.ratelimit import rate_limit
from app.security.turnstile import verify_turnstile
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
    return {
        "score": s,
        "is_hot": lead_scoring.is_hot(s),
        "components": lead_scoring.score_components(body.lead),
    }


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
    """Saare niches overview â€” keywords (scraping) + content_focus (marketing)."""
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
async def niche_pack_one(
    niche_key: str, count: int = 4, city: str = "", _user=Depends(require_admin)
):
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
    agent: str | None = "neo"  # isha_fde | veer | aarav | neo
    brief: str | None = ""  # NL brief â€” FDE plan isi se banata


@router.post("/fde/deploy")
async def fde_deploy(body: FdeDeployIn, _user=Depends(require_admin)):
    """FDE agent ko ek client ke liye automation+marketing+website 'deploy' karne bolo.

    Brief do (e.g. 'naye solar client ka full marketing setup') â†’ FDE plan banata +
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
    from_prospects: int = 0  # >0 â†’ top N prospects auto-enroll


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

    return {
        "stats": cadence.stats(),
        "cadence": cadence.DEFAULT_CADENCE,
        "recent_runs": cadence.list_runs(30),
    }


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

    return await linkedin_assist.draft_outreach(
        body.target_name, body.company or "", body.niche or "general"
    )


class SeoPageIn(BaseModel):
    niche: str
    city: str = "Pune"


@router.post("/seo/page")
async def seo_page(body: SeoPageIn, _user=Depends(require_admin)):
    """Ek nicheÃ—city SEO landing page generate karo (inbound)."""
    from app.marketing import seo_pages

    return await seo_pages.generate_page(body.niche, body.city)


class SeoBatchIn(BaseModel):
    tier: str | None = None
    limit: int = 6


@router.post("/seo/batch")
async def seo_batch(body: SeoBatchIn, _user=Depends(require_admin)):
    """Multiple nicheÃ—city SEO pages (LLM-heavy; limit)."""
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

    return await partnerships.draft_partnership(
        body.partner_type, body.partner_name or "", body.city or ""
    )


@router.post("/partnership/batch")
async def partnership_batch(city: str = "", _user=Depends(require_admin)):
    from app.marketing import partnerships

    return await partnerships.draft_batch(city=city)


# ---------------- Free lead-magnet tools (PUBLIC, inbound) ------------ #
class MissedCallIn2(BaseModel):
    missed_per_day: float
    avg_deal_value: float
    close_rate: float = 0.2


@router.post(
    "/tools/missed-call-revenue",
    tags=["Public Tools"],
    dependencies=[Depends(rate_limit("tools", 20, 60))],
)
async def tool_missed_call(body: MissedCallIn2):
    """PUBLIC lead-magnet: missed-call revenue calculator."""
    from app.marketing import lead_tools

    return lead_tools.missed_call_revenue(body.missed_per_day, body.avg_deal_value, body.close_rate)


class LeadCostIn(BaseModel):
    current_cost_per_lead: float
    leads_per_month: float


@router.post(
    "/tools/lead-cost", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))]
)
async def tool_lead_cost(body: LeadCostIn):
    """PUBLIC: lead-cost savings calculator."""
    from app.marketing import lead_tools

    return lead_tools.lead_cost_savings(body.current_cost_per_lead, body.leads_per_month)


class GoogleScoreIn(BaseModel):
    business_name: str
    city: str | None = ""


@router.post(
    "/tools/google-score",
    tags=["Public Tools"],
    dependencies=[Depends(rate_limit("tools", 20, 60))],
)
async def tool_google_score(body: GoogleScoreIn):
    """PUBLIC: Google-presence checker."""
    from app.marketing import lead_tools

    return await lead_tools.google_presence_score(body.business_name, body.city or "")


# ---------------- Affiliate / referral program ----------------------- #
class AffiliateIn(BaseModel):
    name: str
    email: str | None = ""
    phone: str | None = ""


@router.post(
    "/affiliate/register",
    tags=["Public Tools"],
    dependencies=[Depends(rate_limit("tools", 20, 60))],
)
async def affiliate_register(body: AffiliateIn):
    """PUBLIC: koi bhi affiliate ban sakta â†’ referral link + commission."""
    from app.marketing import affiliate

    return affiliate.register_affiliate(body.name, body.email or "", body.phone or "")


@router.get(
    "/weather-angle", tags=["Public Tools"], dependencies=[Depends(rate_limit("tools", 20, 60))]
)
async def weather_angle_ep(city: str = "Mumbai"):
    """PUBLIC: city ka aaj ka mausam â†’ marketing content angle (Open-Meteo, free, no key, India)."""
    from app.marketing import weather_angle as wa

    return await wa.weather_angle(city)


@router.get("/affiliate/stats")
async def affiliate_stats(code: str | None = None, _user=Depends(require_admin)):
    from app.marketing import affiliate

    return {"stats": affiliate.stats(code), "affiliates": affiliate.list_affiliates(50)}


@router.post("/affiliate/kit")
async def affiliate_kit(body: AffiliateIn, _user=Depends(require_admin)):
    """ADMIN: affiliate register/update + shareable kit (link + WhatsApp-ready
    text) ek hi call me â€” Jiya jaisi referral pakdo (owner 1-tap send)."""
    from app.marketing import affiliate

    return affiliate.referral_kit(body.name, body.email or "", body.phone or "")


# ---------------- Community / Q&A content drafter -------------------- #
class CommunityIn(BaseModel):
    platform: str = "quora"
    topic: str | None = ""
    niche: str | None = "general"


@router.post("/community/draft")
async def community_draft(body: CommunityIn, _user=Depends(require_admin)):
    from app.marketing import community_content

    return await community_content.draft_content(
        body.platform, body.topic or "", body.niche or "general"
    )


@router.post("/community/batch")
async def community_batch(body: CommunityIn, _user=Depends(require_admin)):
    from app.marketing import community_content

    return await community_content.draft_batch(
        topic=body.topic or "", niche=body.niche or "general"
    )


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

    return {
        "stats": sales_pipeline.stats(),
        "deals": sales_pipeline.list_deals(stage),
        "recent_actions": sales_pipeline.list_actions(30),
    }


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

    return await proposal.generate_proposal(
        body.business_name, body.niche or "general", body.city or "", body.plan or "growth"
    )


class SalesMsgIn(BaseModel):
    message: str
    business_name: str | None = ""
    niche: str | None = "general"


@router.post("/sales/assistant")
async def sales_assistant_reply(body: SalesMsgIn, _user=Depends(require_admin)):
    """AI sales-closer: prospect message â†’ objection-aware reply + CTA."""
    from app.marketing import sales_assistant

    return await sales_assistant.handle_message(
        body.message, body.business_name or "", body.niche or "general"
    )


# Revenue/GST/usage-alerts endpoints extracted to app/api/growth_revenue.py (2026-06-20);
# included below so /api/growth/revenue/* paths stay unchanged.
from app.api.growth_revenue import router as _revenue_router  # noqa: E402

router.include_router(_revenue_router)


# ------------- Email warmup ramp + bounce guard (email_warmup.py) ------------- #
@router.get("/outreach/warmup")
async def outreach_warmup_status(_user=Depends(require_admin)):
    """Warmup state: day/week, aaj ka ramp cap, 7d bounce-rate, paused?"""
    from app.platform import email_warmup

    return email_warmup.status()


@router.post("/outreach/warmup/bounce")
async def outreach_warmup_bounce(payload: dict | None = None, _user=Depends(require_admin)):
    """Bounce record karo: {email?, reason?} â€” threshold (1.8%) cross pe auto-pause."""
    from app.platform import email_warmup

    p = payload or {}
    return email_warmup.record_bounce(str(p.get("email") or ""), str(p.get("reason") or ""))


@router.post("/outreach/warmup/resume")
async def outreach_warmup_resume(_user=Depends(require_admin)):
    """Auto-pause manually hatao (lists saaf karne ke baad)."""
    from app.platform import email_warmup

    return {"resumed": email_warmup.resume()}


# ------------- Self-healing growth optimizer + channel experiments ------------- #
@router.get("/optimizer/analysis")
async def optimizer_analysis(_user=Depends(require_admin)):
    """Funnel snapshot + weakest-stage diagnosis (read-only, koi action nahi)."""
    from app.agents import growth_optimizer

    snap = await growth_optimizer.funnel_snapshot()
    return {"snapshot": snap, "weakest": growth_optimizer.weakest_stage(snap)}


@router.post("/optimizer/run")
async def optimizer_run(_user=Depends(require_admin)):
    """Self-healing profit loop abhi chalao (gated GROWTH_OPTIMIZER â€” off = no-op)."""
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
    """Channel outcome record karo (inquiry/reply/signup attribution) â€” bandit seekhta."""
    from app.marketing import channel_experiments

    return channel_experiments.record_outcome(
        body.channel, body.kind or "inquiry", body.value or 1, body.note or ""
    )


# ------------- Campaign Optimization Agent (Kiran) ------------- #
@router.get("/campaign/optimize/status")
async def campaign_optimize_status(_user=Depends(require_admin)):
    from app.agents import campaign_optimizer

    return campaign_optimizer.status()


@router.get("/campaign/optimize/runs")
async def campaign_optimize_runs(limit: int = 20, _user=Depends(require_admin)):
    from app.agents import campaign_optimizer

    return {
        "runs": campaign_optimizer.recent_runs(limit),
        "proposals": campaign_optimizer.recent_proposals(30),
    }


@router.get("/campaign/optimize/proposals")
async def campaign_optimize_proposals(limit: int = 30, _user=Depends(require_admin)):
    from app.agents import campaign_optimizer

    return {"proposals": campaign_optimizer.recent_proposals(limit)}


@router.post("/campaign/optimize/proposals/{proposal_id}/approve")
async def campaign_optimize_approve(proposal_id: str, _user=Depends(require_admin)):
    """Approve Kiran proposal â†’ challenger variant (human gate before outreach use)."""
    from app.agents import campaign_optimizer

    return await campaign_optimizer.approve_proposal(proposal_id)


@router.post("/campaign/optimize")
async def campaign_optimize_run(force: bool = False, _user=Depends(require_admin)):
    """Kiran optimization cycle â€” proposals only, never auto-deploy globally."""
    from app.agents import campaign_optimizer

    return await campaign_optimizer.optimize(force=force)


# ------------- Identity + interactions (enterprise flywheel) ------------- #
@router.get("/identity/duplicates")
async def identity_duplicates(_user=Depends(require_admin)):
    from app.platform import identity_resolver

    return {"groups": identity_resolver.find_duplicate_groups()}


@router.post("/identity/merge")
async def identity_merge(group_id: str, target_key: str = "", _user=Depends(require_admin)):
    from app.platform import identity_resolver

    return await identity_resolver.merge_group(group_id, target_key)


@router.post("/identity/backfill")
async def identity_backfill(limit: int = 500, _user=Depends(require_admin)):
    from app.platform import identity_resolver

    return await identity_resolver.backfill_accounts_contacts(limit)


@router.get("/interactions/timeline")
async def interactions_timeline(phone: str, limit: int = 50, _user=Depends(require_admin)):
    from app.platform import interaction_log

    return {"phone": phone, "interactions": interaction_log.list_for_phone(phone, limit)}


@router.get("/attribution/summary")
async def attribution_summary(_user=Depends(require_admin)):
    from app.platform import revenue_attribution

    return revenue_attribution.summary()


@router.post("/icp/generate")
async def icp_generate(
    client_id: str = "",
    business_name: str = "",
    niche: str = "general",
    city: str = "",
    brief: str = "",
    _user=Depends(require_admin),
):
    from app.platform import icp_generator

    return await icp_generator.generate(
        client_id=client_id,
        business_name=business_name,
        niche=niche,
        city=city,
        brief=brief,
    )


@router.get("/campaign/variants")
async def campaign_variants_list(script_id: str = "", _user=Depends(require_admin)):
    from app.platform import campaign_variants

    return {"variants": await campaign_variants.list_variants(script_id)}


@router.get("/campaign/variants/summary")
async def campaign_variants_summary(script_id: str = "cold_email", _user=Depends(require_admin)):
    from app.platform import campaign_variants

    return await campaign_variants.promotion_summary(script_id)


@router.post("/campaign/variants/promote")
async def campaign_variants_promote(script_id: str, _user=Depends(require_admin)):
    from app.platform import campaign_variants

    return await campaign_variants.try_promote_challenger(script_id)


@router.post("/objections/scan")
async def objections_scan(limit: int = 20, _user=Depends(require_admin)):
    from app.platform import objection_extractor

    return await objection_extractor.scan_recent_transcripts(limit)


@router.get("/objections/recent")
async def objections_recent(limit: int = 20, niche: str = "", _user=Depends(require_admin)):
    from app.platform import objection_extractor

    return {"objections": objection_extractor.recent_patterns(limit, niche=niche)}


@router.post("/crm/pull")
async def crm_pull_status(
    phone: str = "",
    email: str = "",
    client_id: str = "",
    _user=Depends(require_admin),
):
    from app.platform import crm_sync

    return await crm_sync.pull_lead_status(phone=phone, email=email, client_id=client_id)


# content endpoints extracted to app/api/growth_content.py (2026-06-20); paths unchanged.
from app.api.growth_content import router as _content_router  # noqa: E402

router.include_router(_content_router)


# deliverability endpoints extracted to app/api/growth_deliverability.py (2026-06-20); paths unchanged.
from app.api.growth_deliverability import router as _deliverability_router  # noqa: E402

router.include_router(_deliverability_router)


# ---------------- PUBLIC: AI website audit (lead magnet) ---------------- #
class SiteAuditIn(BaseModel):
    url: str


@router.post(
    "/tools/website-audit",
    dependencies=[Depends(rate_limit("site_audit", 10, 60)), Depends(verify_turnstile)],
)
async def website_audit_public(body: SiteAuditIn):
    """PUBLIC lead magnet: website URL â†’ score + Hinglish tips + CTA."""
    from app.marketing import website_auditor

    return await website_auditor.audit_url(body.url)


# ---------------- AI-automation infra (observability/health/DLQ/flags) ---------------- #
@router.get("/infra/llm")
async def infra_llm_metrics(window: int = 2000, _user=Depends(require_admin)):
    """LLM observability: per-provider calls/ok-rate/latency/fallback-rate."""
    from app.platform import llm_metrics

    return llm_metrics.stats(max(100, min(window, 10000)))


@router.get("/infra/explorer-drift")
async def infra_explorer_drift(_user=Depends(require_admin)):
    """Architecture-graph drift â€” how much of the codebase the /app/explorer
    graph reflects (for the explorer's live coverage HUD). Self-contained +
    never-raises (frontend/explorer.html + app/ are baked into the image)."""
    try:
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parent.parent.parent
        html = (root / "frontend" / "explorer.html").read_text(encoding="utf-8", errors="replace")
        sched = (root / "app" / "platform" / "team_scheduler.py").read_text(
            encoding="utf-8", errors="replace"
        )
        blob = html.lower()
        drop = {
            "os",
            "json",
            "asyncio",
            "datetime",
            "timezone",
            "time",
            "random",
            "typing",
            "annotations",
            "contextlib",
            "io",
            "logging",
            "math",
            "uuid",
            "re",
            "logger",
            "settings",
            "config",
            "models",
            "base",
        }
        mods: set[str] = set()
        for m in re.finditer(r"from\s+(app[\w.]+)\s+import\s+([\w_, ]+)", sched):
            path, names = m.group(1), m.group(2)
            parts = path.split(".")
            if len(parts) >= 3:
                mods.add(parts[-1])
            else:
                for n in names.split(","):
                    n = n.strip().split(" as ")[0].strip()
                    if n and n[0].islower():
                        mods.add(n)
        mods = {x for x in mods if x not in drop and len(x) > 2}
        miss = sorted(x for x in mods if x.lower() not in blob)
        total = len(mods) or 1
        drawn = total - len(miss)
        return {
            "nodes": len(re.findall(r"\{id:'", html)),
            "edges": len(re.findall(r"\{f:'", html)),
            "engine_total": total,
            "engine_drawn": drawn,
            "coverage_pct": round(100 * drawn / total),
            "missing": miss[:50],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:120], "coverage_pct": None}


@router.get("/infra/automation-health")
async def infra_automation_health(_user=Depends(require_admin)):
    """Dead-man switch: har scheduled job ka last-run + overdue status."""
    from app.platform import automation_health

    return automation_health.health()


@router.get("/voice/qualifications")
async def voice_qualifications_list(limit: int = 50, _user=Depends(require_admin)):
    """Post-call AI qualifier results (AUTO_QUALIFY_CALLS hook â†’ jsonl)."""
    from app.platform import call_insights

    stats = call_insights.quick_stats()
    return {
        "ok": True,
        "qualifications": call_insights.list_qualifications(limit),
        "stats": stats.get("calls_qualified") or {},
        "flag": "AUTO_QUALIFY_CALLS",
    }


@router.post("/voice/qualifications/ask")
async def voice_qualifications_ask(body: dict, _user=Depends(require_admin)):
    """NL question over call qualification + dialer data."""
    from app.platform import call_insights

    q = str((body or {}).get("question") or "").strip()
    return await call_insights.ask(q)


@router.get("/overview/today")
async def overview_today(_user=Depends(require_admin)):
    """'Aaj kya hua?' â€” PLAIN-HINGLISH admin snapshot (staff + jobs + problems +
    flags) ek hi call me. /app/automation ke 'ðŸ  Aaj' default tab ka payload.
    No LLM, instant, kabhi raise nahi (2026-06-12 admin-friendly upgrade)."""
    from app.platform import today_overview

    return today_overview.build()


@router.get("/infra/hermes")
async def infra_hermes(_user=Depends(require_admin)):
    """Hermes ðŸ›°ï¸ Infrastructure Handler: full infra snapshot â€” readiness, disk,
    memory, dead-man jobs, queue, LLM chain, backups â†’ score + Hinglish actions."""
    from app.platform import infra_handler

    return await infra_handler.snapshot()


@router.get("/infra/hermes/scans")
async def infra_hermes_scans(limit: int = 20, _user=Depends(require_admin)):
    """Hermes ke recent hourly scans (gated INFRA_HANDLER=1 se aate hain)."""
    from app.platform import infra_handler

    return {"scans": infra_handler.recent_scans(max(1, min(limit, 100)))}


@router.get("/infra/integrations")
async def infra_integrations(hours: int = 24, _user=Depends(require_admin)):
    """Integration silent-failure counters: per-integration fail/ok/last-error
    (smtp/places/qdrant...). Alert gated INTEGRATION_ALERTS=1."""
    from app.platform import integration_health

    return integration_health.snapshot(hours=hours)


@router.get("/infra/dlq")
async def infra_dlq(limit: int = 50, key: str = "failed", _user=Depends(require_admin)):
    """Failed Celery tasks inspect karo.

    key=failed (dlq:failed_tasks) | dead (dlq:dead) | resolved (dlq:resolved).
    """
    which = (key or "failed").strip().lower()
    redis_key = {
        "failed": "dlq:failed_tasks",
        "dead": "dlq:dead",
        "resolved": "dlq:resolved",
    }.get(which, "dlq:failed_tasks")
    out: dict = {"count": 0, "items": [], "key": redis_key}
    try:
        import json as _json

        import redis as _redis

        from app.config import settings

        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        out["count"] = int(r.llen(redis_key) or 0)
        for raw in r.lrange(redis_key, 0, max(0, min(limit, 200)) - 1) or []:
            try:
                out["items"].append(_json.loads(raw))
            except Exception:
                pass
    except Exception as e:
        out["error"] = str(e)[:120]
    return out


@router.post("/infra/dlq/sweep")
async def infra_dlq_sweep(limit: int = 20, _user=Depends(require_admin)):
    """Smart DLQ sweep (dlq_retry): staff-jobs retry w/ backoff+attempt-cap,
    unknown/exhausted â†’ dlq:dead. Manual trigger = flag-independent."""
    from app.platform import dlq_retry

    return await dlq_retry.run_sweep(max_items=limit, force=True)


@router.post("/infra/dlq/resolve")
async def infra_dlq_resolve(
    source: str = "dead",
    resolution: str = "STALE_EXPIRED",
    job: str | None = None,
    note: str = "",
    limit: int = 50,
    _user=Depends(require_admin),
):
    """Audited DLQ resolution â€” move matching records to dlq:resolved (no blind purge).

    source=failed|dead Â· resolution=RECOVERED|ALREADY_COMPLETED|SUPERSEDED|
    STALE_EXPIRED|NON_RETRYABLE|MANUAL_REVIEW_REQUIRED Â· optional job filter.
    """
    from app.platform import dlq_retry

    which = (source or "dead").strip().lower()
    source_key = {
        "failed": dlq_retry.DLQ_KEY,
        "dead": dlq_retry.DEAD_KEY,
    }.get(which)
    if not source_key:
        return {"error": "source must be failed|dead", "moved": 0}
    return dlq_retry.resolve_from_list(
        source_key=source_key,
        resolution=(resolution or "").strip().upper(),
        job=(job or None),
        note=note or "",
        max_items=max(1, min(int(limit or 50), 200)),
    )


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
                job = next(
                    (j for j in STAFF_JOBS if f"'{j}'" in args_s or f'"{j}"' in args_s), None
                )
            except Exception:
                pass
            if job:
                try:
                    from app.worker import celery_app

                    celery_app.send_task(
                        "app.tasks.staff_jobs.run_staff_job", args=[job], ignore_result=True
                    )  # fire-and-forget; avoid result-backend pre-subscribe block
                    retried.append(job)
                    continue
                except Exception:
                    pass
            skipped += 1
    except Exception as e:
        return {"error": str(e)[:120], "retried": retried, "skipped": skipped}
    return {"retried": retried, "skipped": skipped}


@router.delete("/infra/dlq")
async def infra_dlq_purge(key: str = "failed", _user=Depends(require_admin)):
    """Purge DLQ lists. key=failed (default) | dead | all.

    `dead` = retry-exhausted (`dlq:dead`) â€” admin must clear stale deploy SIGKILL /
    intentional-skip poison after root-cause fix. Also clears `dlq:retry_counts`
    when dead/all so exhausted jobs can retry cleanly next time.
    """
    try:
        import redis as _redis

        from app.config import settings

        which = (key or "failed").strip().lower()
        if which not in ("failed", "dead", "all"):
            return {"error": "key must be failed|dead|all", "purged": 0}
        r = _redis.Redis.from_url(str(settings.redis_url), socket_timeout=3)
        purged: dict[str, int] = {}
        if which in ("failed", "all"):
            n = int(r.llen("dlq:failed_tasks") or 0)
            r.delete("dlq:failed_tasks")
            purged["dlq:failed_tasks"] = n
        if which in ("dead", "all"):
            n = int(r.llen("dlq:dead") or 0)
            r.delete("dlq:dead")
            purged["dlq:dead"] = n
            try:
                r.delete("dlq:retry_counts")
                purged["dlq:retry_counts"] = 1
            except Exception:
                pass
        return {"purged": purged, "key": which}
    except Exception as e:
        return {"error": str(e)[:120]}


from app.api.automation_flags import (  # noqa: E402,F401  (registry moved out; re-export)
    AUTOMATION_FLAGS,
)

# crm endpoints extracted to app/api/growth_crm.py (2026-06-20); paths unchanged.
from app.api.growth_crm import router as _crm_router  # noqa: E402

router.include_router(_crm_router)


# ------------- Self-hosted tools: free web research (SearXNG) ------------- #
@router.get("/research/search")
async def research_search(q: str, count: int = 10, user=Depends(require_admin)):
    """FREE web search via self-hosted SearXNG (gated SEARXNG_URL).

    Agents/UI ke liye research primitive â€” paid search API ki zaroorat nahi.
    """
    from app.integrations import searxng

    if not searxng.enabled():
        return {
            "enabled": False,
            "hint": "SEARXNG_URL env set karo (deploy/compose/docker-compose.tools.yml)",
            "results": [],
        }
    results = await searxng.search(q, count=count)
    return {"enabled": True, "query": q, "count": len(results), "results": results}


@router.post("/notify/test")
async def notify_test(user=Depends(require_admin)):
    """ntfy phone-push test (gated NTFY_URL+NTFY_TOPIC)."""
    from app.integrations import ntfy

    if not ntfy.enabled():
        return {"enabled": False, "hint": "NTFY_URL + NTFY_TOPIC env set karo"}
    ok = await ntfy.push(
        "Test ðŸ””",
        "LeadGen AI ntfy push kaam kar raha hai!",
        priority="default",
        tags=["white_check_mark"],
    )
    return {"enabled": True, "sent": ok}


# Prospecting endpoints extracted to app/api/growth_prospects.py (2026-06-20);
# included below so /api/growth/prospects/* paths stay unchanged.
from app.api.growth_prospects import router as _prospects_router  # noqa: E402

router.include_router(_prospects_router)


class ReplyFeedbackIn(BaseModel):
    reply_id: str
    correct_intent: str


@router.post("/reply/feedback")
async def reply_feedback(
    body: ReplyFeedbackIn,
    _rl=Depends(rate_limit("reply_feedback", 30, 60)),
    _user=Depends(require_admin),
):
    """Mark reply intent correct/wrong -> training signal for 63/79 'other' classifier fix."""
    import json as _json
    import os as _os
    import time as _time

    _DRAFTS = "data/reply_drafts.jsonl"
    _FEEDBACK = "data/reply_feedback.jsonl"
    _VALID = {
        "interested",
        "question",
        "objection",
        "not_interested",
        "unsubscribe",
        "ooo",
        "other",
    }

    if body.correct_intent not in _VALID:
        raise HTTPException(400, f"intent must be one of {sorted(_VALID)}")

    draft = None
    if _os.path.exists(_DRAFTS):
        with open(_DRAFTS, encoding="utf-8") as f:
            for line in f:
                try:
                    row = _json.loads(line)
                    if str(row.get("id") or "") == str(body.reply_id):
                        draft = row
                        break
                except Exception:
                    pass

    if not draft:
        raise HTTPException(404, "reply_id not found in reply_drafts.jsonl")

    old_intent = draft.get("intent") or "unknown"
    fb = {
        "id": body.reply_id,
        "old_intent": old_intent,
        "correct_intent": body.correct_intent,
        "subject": draft.get("subject", ""),
        "body_snippet": str(draft.get("body") or "")[:200],
        "ts": _time.time(),
    }
    try:
        _os.makedirs("data", exist_ok=True)
        with open(_FEEDBACK, "a", encoding="utf-8") as f:
            f.write(_json.dumps(fb) + "\n")
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

    # Update draft intent in-place
    try:
        lines = []
        with open(_DRAFTS, encoding="utf-8") as f:
            for line in f:
                try:
                    row = _json.loads(line)
                    if str(row.get("id") or "") == str(body.reply_id):
                        row["intent"] = body.correct_intent
                    lines.append(_json.dumps(row))
                except Exception:
                    lines.append(line.rstrip())
        with open(_DRAFTS, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except Exception:
        pass

    return {
        "ok": True,
        "reply_id": body.reply_id,
        "old_intent": old_intent,
        "correct_intent": body.correct_intent,
        "feedback_recorded": True,
    }


@router.get("/reply/feedback/stats")
async def reply_feedback_stats(_user=Depends(require_admin)):
    """Feedback distribution â€” misclassified intents from reply_drafts corrections."""
    import json as _json
    import os as _os
    from collections import Counter

    _FEEDBACK = "data/reply_feedback.jsonl"
    corrections: Counter = Counter()
    total = 0
    if _os.path.exists(_FEEDBACK):
        with open(_FEEDBACK, encoding="utf-8") as f:
            for line in f:
                try:
                    row = _json.loads(line)
                    corrections[f"{row.get('old_intent')}-->{row.get('correct_intent')}"] += 1
                    total += 1
                except Exception:
                    pass
    return {
        "ok": True,
        "total_corrections": total,
        "corrections": dict(corrections.most_common(20)),
    }


@router.get("/reply/hot-queue")
async def reply_hot_queue(
    limit: int = 50,
    scope: str = "boss",
    _user=Depends(require_admin),
):
    """Hot Queue (GTM): interested/question replies â€” dedupe + prospect
    phone-join + freshness sort. Roz subah isse kaam karo (call/WhatsApp/send).

    scope=boss (default) | admin (parked) | all."""
    from app.platform import reply_agent

    scope_n = str(scope or "boss").strip().lower()
    if scope_n not in ("boss", "admin", "all"):
        scope_n = "boss"
    rows = reply_agent.hot_queue(limit=max(1, min(200, limit)), scope=scope_n)
    summary = reply_agent.hot_queue_summary(rows, scope=scope_n)
    return {
        "ok": True,
        "count": len(rows),
        "scope": scope_n,
        "summary": summary,
        "items": rows,
    }


class HotQueueDoneIn(BaseModel):
    hq_id: str


class HotQueueParkIn(BaseModel):
    hq_id: str
    note: str = ""


class HotQueueCouncilIn(BaseModel):
    hq_id: str
    apply: bool = True


@router.post("/reply/hot-queue/done")
async def reply_hot_queue_done(
    body: HotQueueDoneIn,
    _rl=Depends(rate_limit("hot_queue_done", 60, 60)),
    _user=Depends(require_admin),
):
    """1-click Done â€” queue se hatao (draft row pe hq_status=done)."""
    from app.platform import reply_agent

    ok = reply_agent.mark_handled(body.hq_id)
    if not ok:
        raise HTTPException(404, "hq_id not found (ya already done)")
    return {"ok": True, "hq_id": body.hq_id}


@router.post("/reply/hot-queue/park")
async def reply_hot_queue_park(
    body: HotQueueParkIn,
    _rl=Depends(rate_limit("hot_queue_park", 60, 60)),
    _user=Depends(require_admin),
):
    """Manual park for admin â€” boss unclear without running council."""
    from app.platform import reply_agent

    ok = reply_agent.park_for_admin(body.hq_id, note=body.note or "")
    if not ok:
        raise HTTPException(404, "hq_id not found (ya already done)")
    return {"ok": True, "hq_id": body.hq_id, "hq_status": "admin_pending"}


@router.post(
    "/reply/hot-queue/council-decide", dependencies=[Depends(rate_limit("hq_council", 8, 60))]
)
async def reply_hot_queue_council_decide(
    body: HotQueueCouncilIn,
    _user=Depends(require_admin),
):
    """Boss samajh nahi aaya â†’ LLM Council decide (DONE/PARK_ADMIN/KEEP/CALL)."""
    from app.platform import boss_council

    out = await boss_council.decide_hot_queue(body.hq_id, apply=bool(body.apply))
    if not out.get("ok") and "nahi mila" in str(out.get("error") or "").lower():
        raise HTTPException(404, out.get("error") or "not found")
    return out


@router.post("/reply/hot-queue/quick-done/{token}")
async def reply_hot_queue_quick_done(
    token: str,
    _rl=Depends(rate_limit("hq_quickdone", 30, 60)),
):
    """PUBLIC 1-tap Done â€” fired by the ntfy push-notification action button
    (2026-07-03 GTM fix). No login: ntfy's http action can't do interactive
    auth, so the HMAC-signed token (app.platform.reply_agent.make_hq_done_token)
    scopes this call to exactly one hq_id â€” same trust model as the email
    one-click-unsubscribe links. Same effect as the admin dashboard's Done button."""
    from app.platform import reply_agent

    hq_id = reply_agent.verify_hq_done_token(token)
    if not hq_id:
        raise HTTPException(400, "invalid or expired token")
    ok = reply_agent.mark_handled(hq_id)
    return {"ok": ok, "hq_id": hq_id}


@router.get("/speed-to-lead/summary")
async def speed_to_lead_summary(
    days: int = 7,
    _user=Depends(require_admin),
):
    """Speed-to-lead metric: avg/median response time + Hinglish verdict.
    dashboard badge + ops page ke liye."""
    from app.platform import speed_to_lead

    return speed_to_lead.summary(days)


@router.get("/speed-to-lead/breakdown")
async def speed_to_lead_breakdown(
    days: int = 30,
    _user=Depends(require_admin),
):
    """Per-inquiry breakdown: kitne seconds me pehla touch hua."""
    from app.platform import speed_to_lead

    rows = speed_to_lead.per_inquiry(days)
    return {"ok": True, "days": days, "inquiries": rows, "count": len(rows)}


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
    """Saare automation flags ka live status (on/off/unset) + typed kind/lifecycle.

    ``on_count`` remains the legacy truthy-env tally (mixed kinds). Prefer
    ``boolean_on_count`` / per-flag ``switch_on`` for switch semantics.
    """
    import os as _os

    from app.platform.automation_flag_manifest import (
        FlagValueKind,
        build_manifest,
        enrich_flag_row,
        is_secret_name,
    )

    out = {}
    for f in AUTOMATION_FLAGS:
        v = _os.environ.get(f)
        # Never leak secret-valued flags (DR_REPLICA_URL w/ password, LITELLM_MASTER_KEY,
        # *_TOKEN/*_SECRET/*_KEY, TOTP_CHALLENGE_KEYâ€¦) â€” mask the value; plain on/off
        # toggles still show their "1"/"true". `set`/`on` stay visible for both.
        _is_secret = is_secret_name(f) or f.upper().endswith(("_URL", "_DSN"))
        row = {
            "set": v is not None,
            "on": (v or "").strip().lower() in ("1", "true", "yes"),
            "value": ("***" if (_is_secret and v is not None) else v),
        }
        out[f] = enrich_flag_row(f, row)

    # Effective-runtime honesty: REPLY_AUTO_SEND can be live via Redis
    # `reply_auto_send` even when env is 0 (HARD_OFF still wins). Env-only
    # `on`/`switch_on` alone mislead operators â€” surface effective_on too.
    if "REPLY_AUTO_SEND" in out:
        try:
            from app.platform.reply_agent import _reply_auto_send_enabled

            _eff = bool(await _reply_auto_send_enabled())
        except Exception:
            _eff = bool(out["REPLY_AUTO_SEND"].get("on"))
        out["REPLY_AUTO_SEND"]["effective_on"] = _eff
        _eff_note = "env OR Redis runtime reply_auto_send; REPLY_AUTO_SEND_HARD_OFF wins"
        out["REPLY_AUTO_SEND"]["effective_note"] = _eff_note

    on = [k for k, d in out.items() if d["on"]]
    boolean_on = [
        k
        for k, d in out.items()
        if d.get("kind") == FlagValueKind.BOOLEAN.value and d.get("switch_on")
    ]
    effective_overrides = [
        k
        for k, d in out.items()
        if "effective_on" in d and bool(d.get("effective_on")) != bool(d.get("on"))
    ]
    manifest = build_manifest(list(AUTOMATION_FLAGS))
    return {
        "on_count": len(on),
        "on": on,
        "boolean_on_count": len(boolean_on),
        "boolean_on": boolean_on,
        "effective_overrides": effective_overrides,
        "by_kind": manifest["by_kind"],
        "by_lifecycle": manifest["by_lifecycle"],
        "by_governance": manifest.get("by_governance") or manifest["by_lifecycle"],
        "manifest_note": manifest["note"],
        "flags": out,
    }


@router.get("/infra/judge-calibration")
async def infra_judge_calibration(_user=Depends(require_admin)):
    """Per-judge agreement + Cohen's kappa vs human approve/reject ground-truth.
    Offline read of data/*.jsonl; verdict = reliable | advisory | insufficient-data."""
    try:
        from app.agents import judge_calibration

        return judge_calibration.calibrate()
    except Exception as e:  # never break the cockpit
        return {"ok": False, "error": str(e)[:200], "judges": []}


# Per-tenant feature-flags endpoints extracted to app/api/growth_feature_flags.py
# (2026-06-20); included below so paths stay unchanged.
from app.api.growth_feature_flags import router as _feature_flags_router  # noqa: E402

router.include_router(_feature_flags_router)


# ------------- Sales team: 5-agent prospect deep-dive (ai-sales-team adapt) ------------- #
class ProspectAnalysisIn(BaseModel):
    prospect: dict | None = None  # direct record do...
    phone: str | None = None  # ...ya phone se prospects me dhundo


@router.post("/sales/prospect-analysis")
async def sales_prospect_analysis(body: ProspectAnalysisIn, _user=Depends(require_admin)):
    """5 parallel agents (research/BANT/competitive/outreach/objections) ek prospect pe â€”
    ready-to-act analysis + 1-click drafts. Manual run (flag-independent)."""
    from app.agents import sales_team

    p = body.prospect
    if not p and body.phone:
        from app.platform import prospect_lists

        hits = prospect_lists.search("", "", "", None, body.phone, 0, 3) or []
        rows = hits.get("results") if isinstance(hits, dict) else hits
        p = (rows or [{}])[0] if rows else None
    if not p:
        raise HTTPException(status_code=400, detail="prospect dict ya phone do")
    return await sales_team.analyze(p)


@router.get("/sales/prospect-analyses")
async def sales_prospect_analyses(limit: int = 20, _user=Depends(require_admin)):
    """Recent deep-dive analyses (markdown path + score/grade)."""
    from app.agents import sales_team

    return {"analyses": sales_team.list_analyses(limit)}


@router.post("/sales/team-run")
async def sales_team_run(limit: int = 3, _user=Depends(require_admin)):
    """Auto-pilot sweep abhi chalao (top hot leads pe deep-dive) â€” manual trigger."""
    import os as _os

    from app.agents import sales_team

    if _os.environ.get("SALES_TEAM", "0").strip().lower() not in ("1", "true", "yes"):
        # manual admin run = gate bypass karke ek baar chala do
        leads_done = 0
        from app.platform import lead_scoring

        res = await lead_scoring.top_hot_leads(10)
        leads = (res.get("leads") if isinstance(res, dict) else res) or []
        for lead in leads[: max(1, min(limit, 5))]:
            r = await sales_team.analyze(lead if isinstance(lead, dict) else {})
            if r.get("ok"):
                leads_done += 1
        return {"ok": True, "analyzed": leads_done, "note": "flag OFF â€” one-shot manual run"}
    return await sales_team.run_auto(limit)


# Agent automation-ops endpoints extracted to app/api/growth_automation.py (2026-06-20);
# included below so /api/growth/* paths stay unchanged (also mounts /process via chain).
from app.api.growth_automation import router as _automation_router  # noqa: E402

router.include_router(_automation_router)


from app.api.growth_persona import router as _persona_router  # noqa: E402

router.include_router(_persona_router)


from app.api.growth_triage import router as _triage_router  # noqa: E402

router.include_router(_triage_router)
