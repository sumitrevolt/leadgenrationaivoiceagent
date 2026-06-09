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


@router.post("/tools/missed-call-revenue", tags=["Public Tools"])
async def tool_missed_call(body: MissedCallIn2):
    """PUBLIC lead-magnet: missed-call revenue calculator."""
    from app.marketing import lead_tools

    return lead_tools.missed_call_revenue(body.missed_per_day, body.avg_deal_value, body.close_rate)


class LeadCostIn(BaseModel):
    current_cost_per_lead: float
    leads_per_month: float


@router.post("/tools/lead-cost", tags=["Public Tools"])
async def tool_lead_cost(body: LeadCostIn):
    """PUBLIC: lead-cost savings calculator."""
    from app.marketing import lead_tools

    return lead_tools.lead_cost_savings(body.current_cost_per_lead, body.leads_per_month)


class GoogleScoreIn(BaseModel):
    business_name: str
    city: str | None = ""


@router.post("/tools/google-score", tags=["Public Tools"])
async def tool_google_score(body: GoogleScoreIn):
    """PUBLIC: Google-presence checker."""
    from app.marketing import lead_tools

    return await lead_tools.google_presence_score(body.business_name, body.city or "")


# ---------------- Affiliate / referral program ----------------------- #
class AffiliateIn(BaseModel):
    name: str
    email: str | None = ""
    phone: str | None = ""


@router.post("/affiliate/register", tags=["Public Tools"])
async def affiliate_register(body: AffiliateIn):
    """PUBLIC: koi bhi affiliate ban sakta → referral link + commission."""
    from app.marketing import affiliate

    return affiliate.register_affiliate(body.name, body.email or "", body.phone or "")


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
