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

from app.api.auth_deps import require_admin, require_super_admin
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


# ------------- GST invoicing (gst_invoice.py — Rule 46, sequential FY numbering) ------------- #
@router.get("/revenue/invoices")
async def revenue_invoices(limit: int = 50, _user=Depends(require_admin)):
    """Invoice list + FY stats (latest first)."""
    from app.billing import gst_invoice

    return {"stats": gst_invoice.stats(), "invoices": gst_invoice.list_invoices(limit)}


@router.post("/revenue/invoice")
async def revenue_invoice_create(payload: dict, _user=Depends(require_admin)):
    """Manual invoice banao: {client_id, plan, amount_inr?, payment_ref?, gateway?}."""
    from app.billing import gst_invoice

    inv = await gst_invoice.on_payment_success(
        str(payload.get("client_id") or ""),
        str(payload.get("plan") or ""),
        payment_ref=str(payload.get("payment_ref") or ""),
        gateway=str(payload.get("gateway") or ""),
        amount_inr=payload.get("amount_inr"),
    )
    return inv or {"error": "invoice nahi bana — client_id/plan/amount check karo"}


@router.get("/revenue/invoices.csv")
async def revenue_invoices_csv(fy: str = "", _user=Depends(require_admin)):
    """GSTR-friendly CSV export (?fy=2026-27 optional filter) — accounting/CA ke liye."""
    import csv
    import io

    from fastapi.responses import PlainTextResponse

    from app.billing import gst_invoice

    rows = gst_invoice.list_invoices(5000)
    if fy.strip():
        rows = [r for r in rows if r.get("fy") == fy.strip()]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["number", "date", "fy", "client_id", "recipient", "recipient_gstin", "plan",
                "description", "sac_code", "taxable_value", "cgst", "sgst", "igst",
                "gross_inr", "place_of_supply", "tax_mode", "payment_ref", "gateway"])
    for r in rows:
        rec = r.get("recipient", {}) or {}
        w.writerow([r.get("number"), r.get("date"), r.get("fy"), r.get("client_id"),
                    rec.get("name"), rec.get("gstin"), r.get("plan"), r.get("description"),
                    r.get("sac_code"), r.get("taxable_value"), r.get("cgst"), r.get("sgst"),
                    r.get("igst"), r.get("gross_inr"), r.get("place_of_supply"),
                    r.get("tax_mode"), r.get("payment_ref"), r.get("gateway")])
    return PlainTextResponse(buf.getvalue(), media_type="text/csv")


@router.post("/revenue/topup-link")
async def revenue_topup_link(payload: dict, _user=Depends(require_admin)):
    """Voice-minute top-up payment link banao: {client_id, pack: topup_100|topup_250|topup_500}.

    Payment hone par webhook AUTO minutes credit + invoice karta (plan untouched).
    """
    from app.billing import payment_links
    from app.marketing.packages import get_topup_packs, topup_pack

    cid = str(payload.get("client_id") or "").strip()
    pack = topup_pack(str(payload.get("pack") or "topup_100"))
    if not cid or not pack:
        return {"ok": False, "error": "client_id + valid pack chahiye", "packs": get_topup_packs()}
    res = await payment_links.create_payment_link(
        cid,
        pack["price_inr"],
        f"{pack['label']} — AI voice minutes",
        business_name="LeadsGenAI",
        extra_notes={"plan_id": pack["key"]},
    )
    res["pack"] = pack
    return res


@router.get("/revenue/topup-packs")
async def revenue_topup_packs(_user=Depends(require_admin)):
    from app.marketing.packages import get_topup_packs

    return {"packs": get_topup_packs()}


@router.get("/revenue/invoice-html")
async def revenue_invoice_html(number: str, _user=Depends(require_admin)):
    """Printable HTML invoice (?number=INV/2026-27/0001 — number me '/' isliye query param)."""
    from fastapi.responses import HTMLResponse

    from app.billing import gst_invoice

    inv = gst_invoice.get_by_number(number)
    if not inv:
        return {"error": "invoice not found"}
    return HTMLResponse(gst_invoice.invoice_html(inv))


# ------------- Usage upsell alerts (usage_alerts.py — 80%/100% minute triggers) ------------- #
@router.post("/revenue/usage-alerts/run")
async def usage_alerts_run(_user=Depends(require_admin)):
    """Usage-threshold sweep abhi chalao (send gated USAGE_ALERTS=1; record hamesha)."""
    from app.billing import usage_alerts

    return await usage_alerts.run_check()


@router.get("/revenue/usage-alerts")
async def usage_alerts_recent(limit: int = 50, _user=Depends(require_admin)):
    """Recent usage alerts (latest first)."""
    from app.billing import usage_alerts

    return {"alerts": usage_alerts.recent(limit)}


# ------------- Email warmup ramp + bounce guard (email_warmup.py) ------------- #
@router.get("/outreach/warmup")
async def outreach_warmup_status(_user=Depends(require_admin)):
    """Warmup state: day/week, aaj ka ramp cap, 7d bounce-rate, paused?"""
    from app.platform import email_warmup

    return email_warmup.status()


@router.post("/outreach/warmup/bounce")
async def outreach_warmup_bounce(payload: dict | None = None, _user=Depends(require_admin)):
    """Bounce record karo: {email?, reason?} — threshold (1.8%) cross pe auto-pause."""
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


@router.get("/infra/integrations")
async def infra_integrations(hours: int = 24, _user=Depends(require_admin)):
    """Integration silent-failure counters: per-integration fail/ok/last-error
    (email/exotel/telegram...). Alert gated INTEGRATION_ALERTS=1."""
    from app.platform import integration_health

    return integration_health.snapshot(hours=hours)


@router.get("/infra/dlq")
async def infra_dlq(limit: int = 50, key: str = "failed", _user=Depends(require_admin)):
    """Failed Celery tasks inspect karo. key=failed (dlq:failed_tasks) ya
    key=dead (dlq:dead — auto-retry exhausted/unknown, dlq_retry sweep)."""
    redis_key = "dlq:dead" if key == "dead" else "dlq:failed_tasks"
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
    unknown/exhausted → dlq:dead. Manual trigger = flag-independent."""
    from app.platform import dlq_retry

    return await dlq_retry.run_sweep(max_items=limit, force=True)


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
    "AUTO_INVOICE", "EMAIL_WARMUP", "USAGE_ALERTS",
    "REVIEW_MONITOR", "BOOKING_REMINDERS", "DELIVERABILITY_MONITOR", "AUTOMATION_HEALTH_ALERTS",
    "WHATSAPP_AUTO_SEND", "MISSED_CALL_CALLBACK", "SMS_DLT_ENABLED", "USE_SILERO_VAD",
    "USE_SMART_TURN", "USE_LIGHTRAG", "ENABLE_OTEL", "ENABLE_LEGACY_BEAT", "FESTIVALS_LIVE_HOLIDAYS",
    "TELEGRAM_AUTO_PUBLISH", "CLIENT_REPORTS", "CUSTOMER_WISHES", "RANK_TRACKER",
    "MEMORY_VAULT", "LIVE_NOTES", "DLQ_AUTO_RETRY", "INTEGRATION_ALERTS",
    "NPS_ALERTS", "PAYMENT_RECON", "INDEXNOW", "SALES_TEAM", "SELF_IMPROVE_LOOP", "LEAD_HARVESTER",
    "CALL_TRANSFER", "OUTREACH_AB", "SERVICE_REMINDERS",
    "NEWSLETTER_ENGINE", "WINBACK_ENGINE", "BRAND_PULSE", "TEAM_REPORT",
    "SKILL_PACK", "CODE_UPGRADER",
]


# ------------- Apollo-inspired: prospect search/lists/import + email finder ------------- #
@router.get("/prospects/search")
async def prospects_search(
    niche: str = "",
    city: str = "",
    status: str = "",
    has_email: bool | None = None,
    q: str = "",
    min_score: int = 0,
    limit: int = 100,
    _user=Depends(require_admin),
):
    """Apollo-style filter search apne prospects pe (live score ke saath)."""
    from app.platform import prospect_lists

    return prospect_lists.search(niche, city, status, has_email, q, min_score, limit)


class ListIn(BaseModel):
    name: str
    prospect_ids: list[str] | None = None
    filters: dict | None = None


@router.post("/prospects/lists")
async def prospects_create_list(body: ListIn, _user=Depends(require_admin)):
    """Saved list banao (explicit ids ya filters-snapshot)."""
    from app.platform import prospect_lists

    return prospect_lists.create_list(body.name, body.prospect_ids, body.filters)


@router.get("/prospects/lists")
async def prospects_lists(_user=Depends(require_admin)):
    from app.platform import prospect_lists

    return prospect_lists.get_lists()


@router.post("/prospects/lists/{list_id}/enroll-cadence")
async def prospects_list_enroll(list_id: str, _user=Depends(require_admin)):
    """Poori list ko omnichannel cadence me daalo (ban-safe drafts)."""
    from app.platform import prospect_lists

    return prospect_lists.enroll_list_to_cadence(list_id)


class ImportIn(BaseModel):
    rows: list[dict] | None = None
    csv_text: str | None = None
    source: str | None = "apollo_import"


@router.post("/prospects/import")
async def prospects_import(body: ImportIn, _user=Depends(require_admin)):
    """Apollo CSV/rows import → dedupe → prospector store + DB + scoring pipeline."""
    from app.platform import prospect_lists

    if body.csv_text:
        return prospect_lists.import_csv_text(body.csv_text, body.source or "apollo_import")
    return prospect_lists.import_rows(body.rows or [], body.source or "apollo_import")


class EmailFindIn(BaseModel):
    website: str
    owner_name: str | None = ""


@router.post("/prospects/find-email")
async def prospects_find_email(body: EmailFindIn, _user=Depends(require_admin)):
    """Email-finder waterfall: site-extract → pattern-guess → MX verify (Apollo-free)."""
    from app.platform import email_finder

    return await email_finder.find(body.website, body.owner_name or "")


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


# ------------- Marketing AI upgrades: feedback loop / trends / reel / KB-post / telegram ------------- #
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
async def content_trends(niche: str = "general", business_name: str = "", _user=Depends(require_admin)):
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


class TelegramIn(BaseModel):
    chat_id: str = ""
    text: str = ""
    image_url: str = ""
    client_id: str = ""
    occasion: str = ""
    offer: str = ""


@router.post("/content/telegram-send")
async def content_telegram_send(body: TelegramIn, _user=Depends(require_admin)):
    """Telegram channel pe publish — TRUE auto channel (TELEGRAM_BOT_TOKEN gated)."""
    from app.marketing import telegram_publish

    if body.client_id and not body.text:
        return await telegram_publish.send_for_client(body.client_id, body.occasion, body.offer)
    return await telegram_publish.send_post(body.chat_id, body.text, body.image_url)


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

    return loyalty.create_campaign(body.client_id, body.title, body.kind, body.value, body.expiry_days, body.max_redemptions)


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
    return {"client_id": cid, "business_name": client.get("business_name"), "stats": client_report.collect_stats(client)}


# ------------- Prod-batch 2026-06-10: NPS + payment recon + IndexNow ------------- #
class NPSIn(BaseModel):
    score: int
    comment: str | None = ""
    name: str | None = ""
    phone: str | None = ""
    client_slug: str | None = ""


@router.post("/nps/submit", tags=["Public Tools"], dependencies=[Depends(rate_limit("nps", 10, 60))])
async def nps_submit(body: NPSIn):
    """PUBLIC: NPS/CSAT response (0-10). Detractor alert gated NPS_ALERTS=1."""
    from app.platform import nps

    return await nps.submit(body.score, body.comment or "", body.name or "", body.phone or "", body.client_slug or "")


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


@router.get("/revenue/recon")
async def payment_recon_last(_user=Depends(require_admin)):
    """Last payment-reconciliation report (Razorpay vs invoices)."""
    from app.billing import payment_recon

    return payment_recon.last_report()


@router.post("/revenue/recon/run")
async def payment_recon_run(days: int = 3, _user=Depends(require_admin)):
    """Razorpay captured payments vs internal invoices — READ-only recon sweep."""
    from app.billing import payment_recon

    return await payment_recon.run(days)


class IndexNowIn(BaseModel):
    urls: list[str] | None = None  # khali = poora sitemap sweep


@router.post("/seo/indexnow")
async def seo_indexnow(body: IndexNowIn, _user=Depends(require_admin)):
    """Bing/Yandex IndexNow submit — urls do ya khali chodo (sitemap sweep)."""
    from app.marketing import indexnow

    if body.urls:
        return await indexnow.submit_urls(body.urls)
    return await indexnow.submit_sitemap_if_enabled(force=True)  # admin manual = flag bypass


# ------------- Sales team: 5-agent prospect deep-dive (ai-sales-team adapt) ------------- #
class ProspectAnalysisIn(BaseModel):
    prospect: dict | None = None  # direct record do...
    phone: str | None = None      # ...ya phone se prospects me dhundo


@router.post("/sales/prospect-analysis")
async def sales_prospect_analysis(body: ProspectAnalysisIn, _user=Depends(require_admin)):
    """5 parallel agents (research/BANT/competitive/outreach/objections) ek prospect pe —
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
    """Auto-pilot sweep abhi chalao (top hot leads pe deep-dive) — manual trigger."""
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
        return {"ok": True, "analyzed": leads_done, "note": "flag OFF — one-shot manual run"}
    return await sales_team.run_auto(limit)


# ------------- Self-improve continuous loop + skill library + naye channels ------------- #
@router.get("/selfimprove/status")
async def selfimprove_status(_user=Depends(require_admin)):
    """Continuous loop ka live status: heartbeat, runs, queue, skill summary."""
    from app.agents import self_improve

    return self_improve.status()


@router.post("/selfimprove/run")
async def selfimprove_run(_user=Depends(require_admin)):
    """Loop tick ABHI enqueue karo (Celery worker me chalega — web process block
    nahi hota). Flag OFF ho to bhi one-shot enqueue ho jata (tick khud gate check
    karta, requeue sirf flag ON pe)."""
    try:
        from app.tasks.staff_jobs import self_improve_tick

        r = self_improve_tick.delay()
        return {"ok": True, "queued": True, "task_id": str(getattr(r, "id", ""))}
    except Exception as e:
        return {"ok": False, "queued": False, "error": str(e)[:200], "hint": "celery worker chal raha hai?"}


class SelfImproveTaskIn(BaseModel):
    task: str
    action: str = ""


@router.post("/selfimprove/task")
async def selfimprove_add_task(body: SelfImproveTaskIn, _user=Depends(require_admin)):
    """Manual task queue me daalo — loop agle tick pe ise pehle uthayega.
    Valid actions: self_improve.ACTIONS keys (khali = auto-pick)."""
    from app.agents import self_improve

    return self_improve.add_task(body.task, body.action, source="manual")


@router.get("/selfimprove/actions")
async def selfimprove_actions(_user=Depends(require_admin)):
    """Available loop actions + descriptions."""
    from app.agents import self_improve

    return {"actions": [{"key": k, "llm_heavy": v[0], "desc": v[1]} for k, v in self_improve.ACTIONS.items()]}


@router.get("/skills/library")
async def skills_library(_user=Depends(require_admin)):
    """Auto-learn skill library: per-tactic success-rates + recent lessons."""
    from app.platform import skill_library

    return skill_library.summary()


class LessonIn(BaseModel):
    topic: str = "general"
    lesson: str


@router.post("/skills/lesson")
async def skills_add_lesson(body: LessonIn, _user=Depends(require_admin)):
    """Manual lesson add (human coaching → agents agle runs me use karte)."""
    from app.platform import skill_library

    return skill_library.record_lesson(body.topic, body.lesson, source="manual", agent="sumit")


# ------------- Skill pack (Claude project skills → VPS agents) + code upgrader ------------- #
@router.get("/skills/pack")
async def skills_pack_list(q: str = "", _user=Depends(require_admin)):
    """35+ project skills (+agent-authored extras) — list ya keyword search."""
    from app.platform import skill_pack

    if q:
        return {"query": q, "matches": skill_pack.find(q, k=5)}
    return {"enabled": skill_pack.enabled(), "skills": skill_pack.list_skills()}


@router.get("/skills/pack/{name}")
async def skills_pack_get(name: str, _user=Depends(require_admin)):
    from app.platform import skill_pack

    s = skill_pack.load(name)
    if not s:
        raise HTTPException(status_code=404, detail="skill not found")
    return s


@router.post("/skills/pack/ingest")
async def skills_pack_ingest(_user=Depends(require_admin)):
    """Saari skills KB namespace 'skills' me (Qdrant semantic recall)."""
    from app.platform import skill_pack

    return skill_pack.ingest_to_kb()


class SkillAuthorIn(BaseModel):
    name: str
    text: str


@router.post("/skills/pack/author")
async def skills_pack_author(body: SkillAuthorIn, _user=Depends(require_admin)):
    """Tier-1 SAFE write — naya/updated skill data/skills_extra/ me (runtime-live)."""
    from app.platform import skill_pack

    return skill_pack.author(body.name, body.text)


@router.post("/upgrader/scan")
async def upgrader_scan(_user=Depends(require_admin)):
    """Vikram: observability signals → code-upgrade proposals (flag-independent manual run)."""
    from app.agents import code_upgrader

    return await code_upgrader.scan_and_propose()


@router.get("/upgrader/patches")
async def upgrader_patches(status: str | None = None, limit: int = 50, _user=Depends(require_admin)):
    from app.agents import code_upgrader

    return {"patches": code_upgrader.list_patches(status, limit)}


class PatchStatusIn(BaseModel):
    status: str  # approved | rejected | applied
    note: str = ""


@router.post("/upgrader/patches/{patch_id}/status")
async def upgrader_patch_status(patch_id: str, body: PatchStatusIn, _user=Depends(require_super_admin)):
    """Hybrid gate: core-code patch approve/reject — SUPER_ADMIN only (RBAC design)."""
    from app.agents import code_upgrader

    return code_upgrader.set_status(patch_id, body.status, body.note)


@router.get("/social/channels")
async def social_channels_list(_user=Depends(require_admin)):
    """Naye customer-approach channels (sab ban-safe drafts)."""
    from app.marketing import social_channels

    return {"channels": social_channels.list_channels()}


class SocialDraftIn(BaseModel):
    channel: str
    niche: str = "general"
    city: str = ""
    business_name: str = ""


@router.post("/social/draft")
async def social_draft(body: SocialDraftIn, _user=Depends(require_admin)):
    """Ek naye channel ka ready-to-post Hinglish draft (manual 1-click post)."""
    from app.marketing import social_channels

    return await social_channels.draft(body.channel, body.niche, body.city, body.business_name)


class SocialBatchIn(BaseModel):
    niche: str = "general"
    city: str = ""
    business_name: str = ""
    channels: list[str] | None = None
    limit: int = 4


@router.post("/social/batch")
async def social_batch(body: SocialBatchIn, _user=Depends(require_admin)):
    """Multiple naye channels ka draft pack."""
    from app.marketing import social_channels

    return await social_channels.draft_batch(body.niche, body.city, body.business_name, body.channels, body.limit)


# ------------- Lead harvester (multi-source, legal-only, automated loop) ------------- #
class HarvestIn(BaseModel):
    niche: str = ""
    city: str = ""
    limit: int = 10
    sources: list[str] | None = None


@router.post("/harvest/run")
async def harvest_run(body: HarvestIn, _user=Depends(require_admin)):
    """Multi-source lead harvest abhi chalao (manual = flag-independent).
    Sources: prospector (Places/OSM), websearch (BRAVE_API_KEY), opendata
    (DATA_GOV_IN_API_KEY) + email-enrich. Directory/social scraping NAHI (ToS)."""
    from app.platform import lead_harvester

    return await lead_harvester.run_harvest(body.niche, body.city, body.limit, body.sources)


@router.get("/harvest/runs")
async def harvest_runs(limit: int = 15, _user=Depends(require_admin)):
    """Recent harvest runs (per-source stats)."""
    from app.platform import lead_harvester

    return {"runs": lead_harvester.recent_runs(limit)}


@router.get("/harvest/sources")
async def harvest_sources(_user=Depends(require_admin)):
    """Source readiness (kaunse keys armed) + blocked-domains policy."""
    from app.platform import lead_harvester

    return lead_harvester.source_status()


@router.post("/harvest/enrich")
async def harvest_enrich(limit: int = 10, _user=Depends(require_admin)):
    """Email-less prospects pe enrich waterfall abhi chalao."""
    from app.platform import lead_harvester

    return await lead_harvester.enrich_missing_emails(limit)


# ------------- Process engine (babysitter-pattern: deterministic + breakpoints) ------------- #
@router.get("/process/definitions")
async def process_definitions(_user=Depends(require_admin)):
    """Available process-as-code workflows (steps + gates + breakpoints)."""
    from app.agents import process_library

    return {"processes": process_library.list_processes()}


class ProcessStartIn(BaseModel):
    process: str
    inputs: dict = {}


@router.post("/process/start")
async def process_start(body: ProcessStartIn, _user=Depends(require_admin)):
    """Run start + Celery worker me advance enqueue (web kabhi inline nahi)."""
    from app.agents import process_engine

    r = process_engine.start_run(body.process, body.inputs)
    if r.get("ok"):
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(r["run_id"])
            r["queued"] = True
        except Exception as e:
            r["queued"] = False
            r["hint"] = f"worker enqueue fail: {str(e)[:100]}"
    return r


@router.get("/process/runs")
async def process_runs(limit: int = 20, _user=Depends(require_admin)):
    """Recent runs + journal-derived live status."""
    from app.agents import process_engine

    return {"runs": process_engine.list_runs(limit)}


@router.get("/process/run/{run_id}")
async def process_run_detail(run_id: str, _user=Depends(require_admin)):
    """Run state (replay) + full immutable journal."""
    from app.agents import process_engine

    return {"state": process_engine.replay(run_id), "journal": process_engine.journal(run_id)}


class ProcessApproveIn(BaseModel):
    note: str = ""


@router.post("/process/run/{run_id}/approve")
async def process_approve(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint APPROVE → run resume (Celery tick)."""
    from app.agents import process_engine

    r = process_engine.approve(run_id, approved_by=getattr(_user, "email", "admin") or "admin", note=body.note)
    if r.get("ok"):
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            r["queued"] = False
    return r


@router.post("/process/run/{run_id}/reject")
async def process_reject(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint REJECT → run failed (audit trail)."""
    from app.agents import process_engine

    return process_engine.reject(run_id, by=getattr(_user, "email", "admin") or "admin", reason=body.note)
