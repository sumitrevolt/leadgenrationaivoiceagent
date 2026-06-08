"""
Customer-facing Dashboard API
==============================
Powers frontend/customer_dashboard.html.

The END CUSTOMER here is a small business (the SaaS's client). They want to see
the leads our AI voice agent generated for them and the calls it made on their
behalf.

This module is intentionally import-safe: it only depends on the Python stdlib +
fastapi + pydantic, so it can be mounted without pulling in DB/ML/telephony deps.

TODO: bind to real DB (Lead, CallLog models). Right now every endpoint returns
clearly-marked SAMPLE data shaped EXACTLY like the embedded demo data in
frontend/customer_dashboard.html so the UI works end-to-end today.

Mount in main.py with:
    from app.api.customer_dashboard import router as customer_router
    app.include_router(customer_router)
(Router already carries prefix="/api/customer".)
"""

import logging
import random
from datetime import datetime, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer", tags=["Customer Dashboard"])


# --------------------------------------------------------------------------- #
# Pydantic response models (this is the exact JSON contract the HTML consumes) #
# --------------------------------------------------------------------------- #
class Kpis(BaseModel):
    total_calls: int = Field(..., description="Total calls our agent dialled")
    connected_calls: int = Field(..., description="Calls that actually connected")
    qualified_leads: int = Field(..., description="Leads that passed qualification")
    conversion_pct: float = Field(..., description="qualified / connected * 100")
    est_cost_inr: int = Field(..., description="Estimated telephony cost in Rupees")


class CallRow(BaseModel):
    time: str  # "2026-06-05 14:32"
    business: str  # "Sharma Solar Solutions"
    phone_masked: str  # "+91 98XXXXXX10"
    city: str  # "Mumbai"
    duration: str  # "2m 14s"
    status: str  # connected | no-answer | busy
    outcome: str  # "Interested - qualified" etc.


class LeadRow(BaseModel):
    business: str
    contact: str
    phone: str  # full number (client owns this lead)
    city: str
    niche: str  # solar | dental | real-estate
    score: str  # Hot | Warm | Cold
    qualification: str  # short summary of qualification answers
    date: str  # "2026-06-05"


class SeriesPoint(BaseModel):
    label: str
    value: int


class ChartsData(BaseModel):
    calls_per_day: list[SeriesPoint]
    leads_by_status: list[SeriesPoint]  # Hot / Warm / Cold
    leads_by_city: list[SeriesPoint]


class Campaign(BaseModel):
    id: str
    name: str


class DashboardResponse(BaseModel):
    is_sample_data: bool = Field(
        True, description="True => placeholder data, NOT real client results"
    )
    client_id: str
    generated_at: str
    campaigns: list[Campaign]
    kpis: Kpis
    calls: list[CallRow]
    leads: list[LeadRow]
    charts: ChartsData


# --------------------------------------------------------------------------- #
# SAMPLE data builder (deterministic-ish, realistic for Indian SMBs)          #
# --------------------------------------------------------------------------- #
_CITIES = ["Mumbai", "Pune", "Delhi", "Bangalore"]
_NICHES = ["solar", "dental", "real-estate"]

_BUSINESSES = {
    "solar": [
        "Sharma Solar Solutions",
        "SunVolt Energy",
        "GreenRay Solar",
        "Aditya Solar Power",
        "EcoSun Systems",
        "Surya Renewables",
        "BrightWatt Solar",
        "Tejas Solar Hub",
    ],
    "dental": [
        "Smile Care Dental",
        "Dr. Mehta Dental Clinic",
        "Perfect Smile Studio",
        "DentaWorld Clinic",
        "City Dental Care",
        "Bright Dental Hub",
        "Oral Health Centre",
        "Pearl Dental Clinic",
    ],
    "real-estate": [
        "Gokhale Realty",
        "Prime Properties",
        "Skyline Estates",
        "Urban Nest Realtors",
        "Capital Homes",
        "Greenfield Properties",
        "Metro Realty Group",
        "Anand Estate Agents",
    ],
}

_CONTACTS = [
    "Rajesh Sharma",
    "Priya Mehta",
    "Amit Gokhale",
    "Sneha Iyer",
    "Vikram Singh",
    "Pooja Nair",
    "Rahul Desai",
    "Anita Rao",
    "Suresh Patil",
    "Kavya Reddy",
    "Manish Joshi",
    "Neha Kulkarni",
]

_OUTCOMES_CONNECTED = [
    "Interested - qualified",
    "Interested - callback",
    "Asked to call later",
    "Wants quotation",
    "Not interested",
    "Already has vendor",
]

_QUALIFICATION = {
    "solar": [
        "Owns rooftop, bill > Rs.4000/mo, ready in 30 days",
        "Bill ~Rs.6500/mo, wants subsidy info, hot",
        "Rented place, low intent",
    ],
    "dental": [
        "Needs implants, budget ok, book this week",
        "Routine cleaning, price sensitive",
        "Enquiry for braces, teen patient, warm",
    ],
    "real-estate": [
        "Budget Rs.80L-1Cr, 2BHK, ready to visit",
        "Investment buyer, 3+ units, hot",
        "Just browsing, no timeline",
    ],
}


def _mask_phone(num: str) -> str:
    # +91 98XXXXXX10  -> keep first 2 + last 2 of the 10-digit part
    return f"+91 {num[:2]}XXXXXX{num[-2:]}"


def _build_sample(client_id: str, campaign: str | None) -> DashboardResponse:
    rng = random.Random(42)  # stable sample so the UI looks consistent

    campaigns = [
        Campaign(id="all", name="All Campaigns"),
        Campaign(id="solar-mum", name="Solar - Mumbai (June)"),
        Campaign(id="dental-pune", name="Dental - Pune Clinics"),
        Campaign(id="realty-blr", name="Real Estate - Bangalore"),
    ]

    # ----- calls (40) -----
    calls: list[CallRow] = []
    base = datetime(2026, 6, 5, 18, 0)
    for i in range(40):
        niche = rng.choice(_NICHES)
        biz = rng.choice(_BUSINESSES[niche])
        city = rng.choice(_CITIES)
        status = rng.choices(["connected", "no-answer", "busy"], weights=[62, 26, 12])[0]
        t = base - timedelta(minutes=rng.randint(5, 60) * (i + 1))
        if status == "connected":
            secs = rng.randint(35, 230)
            duration = f"{secs // 60}m {secs % 60:02d}s"
            outcome = rng.choice(_OUTCOMES_CONNECTED)
        else:
            duration = "0m 00s"
            outcome = "No answer" if status == "no-answer" else "Line busy"
        digits = f"{rng.randint(70, 99)}{rng.randint(10000000, 99999999):08d}"[:10]
        calls.append(
            CallRow(
                time=t.strftime("%Y-%m-%d %H:%M"),
                business=biz,
                phone_masked=_mask_phone(digits),
                city=city,
                duration=duration,
                status=status,
                outcome=outcome,
            )
        )

    # ----- leads (26) -----
    leads: list[LeadRow] = []
    for i in range(26):
        niche = rng.choice(_NICHES)
        biz = rng.choice(_BUSINESSES[niche])
        city = rng.choice(_CITIES)
        score = rng.choices(["Hot", "Warm", "Cold"], weights=[34, 44, 22])[0]
        digits = f"{rng.randint(70, 99)}{rng.randint(10000000, 99999999):08d}"[:10]
        d = datetime(2026, 6, 5) - timedelta(days=rng.randint(0, 9))
        leads.append(
            LeadRow(
                business=biz,
                contact=rng.choice(_CONTACTS),
                phone=f"+91 {digits}",
                city=city,
                niche=niche,
                score=score,
                qualification=rng.choice(_QUALIFICATION[niche]),
                date=d.strftime("%Y-%m-%d"),
            )
        )

    # ----- KPIs -----
    total_calls = len(calls)
    connected = sum(1 for c in calls if c.status == "connected")
    qualified = len(leads)
    conv = round((qualified / connected) * 100, 1) if connected else 0.0
    # rough India telephony estimate: ~Rs.0.65/min, assume ~1.5 min avg/connected
    est_cost = int(connected * 1.5 * 0.65)

    kpis = Kpis(
        total_calls=total_calls,
        connected_calls=connected,
        qualified_leads=qualified,
        conversion_pct=conv,
        est_cost_inr=est_cost,
    )

    # ----- charts -----
    days = ["May 30", "May 31", "Jun 01", "Jun 02", "Jun 03", "Jun 04", "Jun 05"]
    calls_per_day = [SeriesPoint(label=d, value=rng.randint(28, 72)) for d in days]
    leads_by_status = [
        SeriesPoint(label="Hot", value=sum(1 for l in leads if l.score == "Hot")),
        SeriesPoint(label="Warm", value=sum(1 for l in leads if l.score == "Warm")),
        SeriesPoint(label="Cold", value=sum(1 for l in leads if l.score == "Cold")),
    ]
    leads_by_city = [
        SeriesPoint(label=c, value=sum(1 for l in leads if l.city == c)) for c in _CITIES
    ]

    return DashboardResponse(
        is_sample_data=True,
        client_id=client_id,
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        campaigns=campaigns,
        kpis=kpis,
        calls=calls,
        leads=leads,
        charts=ChartsData(
            calls_per_day=calls_per_day,
            leads_by_status=leads_by_status,
            leads_by_city=leads_by_city,
        ),
    )


# --------------------------------------------------------------------------- #
# DB-backed builder (real data). Import-safe: all DB imports are local + try/  #
# except so this module still mounts when DB deps/connection are missing.      #
# --------------------------------------------------------------------------- #
def _score_tier(score: int, is_hot: bool) -> str:
    """Map a 0-100 lead_score / is_hot_lead flag to Hot/Warm/Cold."""
    if is_hot or (score or 0) >= 70:
        return "Hot"
    if (score or 0) >= 40:
        return "Warm"
    return "Cold"


def _fmt_duration(seconds: int) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}m {seconds % 60:02d}s"


def _mask_full_phone(num: str | None) -> str:
    digits = "".join(c for c in (num or "") if c.isdigit())[-10:]
    if len(digits) < 4:
        return "+91 XXXXXXXXXX"
    return f"+91 {digits[:2]}XXXXXX{digits[-2:]}"


def _build_from_db(client_id: str, campaign: str | None) -> DashboardResponse | None:
    """
    Build the dashboard payload from the real DB.
    Returns None if the DB is unavailable OR has no rows for this client
    (so the caller can fall back to sample data and keep is_sample_data=True).
    """
    try:
        from app.models.base import get_db_session
        from app.models.call_log import CallLog, CallOutcome
        from app.models.campaign import Campaign as CampaignModel
        from app.models.lead import Lead, LeadStatus
    except Exception as e:  # missing deps / import error
        logger.warning("customer_dashboard: DB models unavailable, using sample (%s)", e)
        return None

    try:
        with get_db_session() as db:
            # ----- campaigns for this client -----
            camp_q = db.query(CampaignModel).filter(CampaignModel.client_id == client_id)
            camp_rows = camp_q.all()

            # ----- leads -----
            lead_q = db.query(Lead).filter(Lead.assigned_to == client_id)
            if campaign and campaign != "all":
                lead_q = lead_q.filter(Lead.campaign_id == campaign)
            lead_rows = lead_q.order_by(Lead.created_at.desc()).limit(200).all()

            # ----- calls -----
            call_q = db.query(CallLog).filter(CallLog.client_id == client_id)
            if campaign and campaign != "all":
                call_q = call_q.filter(CallLog.campaign_id == campaign)
            call_rows = call_q.order_by(CallLog.initiated_at.desc()).limit(200).all()

            # If this client genuinely has no data, fall back to sample.
            if not lead_rows and not call_rows:
                return None

            # ----- campaigns list (always include "All") -----
            campaigns: list[Campaign] = [Campaign(id="all", name="All Campaigns")]
            for c in camp_rows:
                campaigns.append(Campaign(id=str(c.id), name=c.name or "Campaign"))

            # ----- calls -----
            calls: list[CallRow] = []
            connected = 0
            for c in call_rows:
                status_raw = (c.status or "").lower()
                outcome_val = c.outcome.value if c.outcome else None
                if outcome_val == CallOutcome.NO_ANSWER.value:
                    status = "no-answer"
                elif outcome_val == CallOutcome.BUSY.value:
                    status = "busy"
                elif (c.duration_seconds or 0) > 0 or status_raw in (
                    "answered",
                    "completed",
                    "connected",
                ):
                    status = "connected"
                else:
                    status = "no-answer"
                if status == "connected":
                    connected += 1
                when = c.initiated_at or c.created_at or datetime.utcnow()
                calls.append(
                    CallRow(
                        time=when.strftime("%Y-%m-%d %H:%M"),
                        business=(c.lead.company_name if c.lead else None) or "Unknown",
                        phone_masked=_mask_full_phone(c.to_number),
                        city=(c.lead.city if c.lead else None) or "-",
                        duration=_fmt_duration(c.duration_seconds),
                        status=status,
                        outcome=(
                            outcome_val.replace("_", " ").title() if outcome_val else "Pending"
                        ),
                    )
                )

            # ----- leads -----
            leads: list[LeadRow] = []
            for l in lead_rows:
                qual = l.get_qualification_data() if hasattr(l, "get_qualification_data") else {}
                qual_text = ""
                if isinstance(qual, dict) and qual:
                    qual_text = ", ".join(f"{k}: {v}" for k, v in list(qual.items())[:3])
                leads.append(
                    LeadRow(
                        business=l.company_name or "Unknown",
                        contact=l.contact_name or "-",
                        phone=(
                            f"+91 {l.phone}"
                            if l.phone and not str(l.phone).startswith("+")
                            else (l.phone or "-")
                        ),
                        city=l.city or "-",
                        niche=l.niche or "general",
                        score=_score_tier(l.lead_score, l.is_hot_lead),
                        qualification=qual_text or (l.notes or "")[:80] or "-",
                        date=(l.created_at or datetime.utcnow()).strftime("%Y-%m-%d"),
                    )
                )

            # ----- KPIs -----
            total_calls = len(call_rows)
            qualified = sum(
                1
                for l in lead_rows
                if l.status in (LeadStatus.QUALIFIED, LeadStatus.APPOINTMENT, LeadStatus.CONVERTED)
                or l.is_hot_lead
            )
            conv = round((qualified / connected) * 100, 1) if connected else 0.0
            total_talk = sum((c.duration_seconds or 0) for c in call_rows)
            est_cost = int((total_talk / 60.0) * 0.65)

            kpis = Kpis(
                total_calls=total_calls,
                connected_calls=connected,
                qualified_leads=qualified,
                conversion_pct=conv,
                est_cost_inr=est_cost,
            )

            # ----- charts -----
            from collections import defaultdict

            per_day: dict = defaultdict(int)
            for c in call_rows:
                when = c.initiated_at or c.created_at
                if when:
                    per_day[when.strftime("%b %d")] += 1
            calls_per_day = [SeriesPoint(label=k, value=v) for k, v in sorted(per_day.items())]

            tier_counts = {"Hot": 0, "Warm": 0, "Cold": 0}
            city_counts: dict = defaultdict(int)
            for l in lead_rows:
                tier_counts[_score_tier(l.lead_score, l.is_hot_lead)] += 1
                if l.city:
                    city_counts[l.city] += 1
            leads_by_status = [SeriesPoint(label=k, value=v) for k, v in tier_counts.items()]
            leads_by_city = [
                SeriesPoint(label=c, value=n)
                for c, n in sorted(city_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
            ]

            return DashboardResponse(
                is_sample_data=False,
                client_id=client_id,
                generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                campaigns=campaigns,
                kpis=kpis,
                calls=calls,
                leads=leads,
                charts=ChartsData(
                    calls_per_day=calls_per_day,
                    leads_by_status=leads_by_status,
                    leads_by_city=leads_by_city,
                ),
            )
    except Exception as e:
        logger.warning("customer_dashboard: DB query failed, using sample (%s)", e)
        return None


# --------------------------------------------------------------------------- #
# Real top-line counts (cheap overlay for the sample fallback)                 #
# --------------------------------------------------------------------------- #
def _real_topline_counts(client_id: str) -> dict:
    """
    Cheapest real bindings when the per-client rows are missing:
      - leads:     Lead count for this client (assigned_to); falls back to the
                   platform-wide Lead total if the client has none.
      - inquiries: line count of data/inquiries.jsonl (no client mapping yet,
                   so platform totals — used as a leads fallback).
      - calls:     agent_events count for swara (every placed/finished call +
                   web demo is logged there).
    All best-effort; returns {} when nothing real is available. Never raises.
    """
    out: dict = {}
    try:
        from app.models.agent_event import AgentEvent
        from app.models.base import get_db_session
        from app.models.lead import Lead

        with get_db_session() as db:
            try:
                n = db.query(Lead).filter(Lead.assigned_to == client_id).count()
                if not n:
                    n = db.query(Lead).count()
                if n:
                    out["leads"] = int(n)
            except Exception:
                pass
            try:
                c = db.query(AgentEvent).filter(AgentEvent.member == "swara").count()
                if c:
                    out["calls"] = int(c)
            except Exception:
                pass
    except Exception as e:
        logger.debug("customer_dashboard: topline DB counts unavailable (%s)", e)

    try:
        import os

        path = os.path.join("data", "inquiries.jsonl")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                n = sum(1 for ln in f if ln.strip())
            if n:
                out["inquiries"] = n
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_model=DashboardResponse)
def get_customer_dashboard(
    client_id: str = Query("demo", description="The client/business identifier"),
    campaign: str | None = Query(None, description="Optional campaign id to filter by"),
) -> DashboardResponse:
    """
    Return the full dashboard payload for a customer.

    Sources data from the real DB (Lead, CallLog, Campaign) keyed by
    client_id + campaign. Falls back to clearly-marked SAMPLE data
    (is_sample_data=True) when the DB is unavailable or has no rows — but the
    top-level KPI counts get overlaid with real platform numbers (leads /
    inquiries / swara calls) whenever those exist, so the headline figures are
    never pure fiction.
    """
    real = _build_from_db(client_id=client_id, campaign=campaign)
    if real is not None:
        return real

    sample = _build_sample(client_id=client_id, campaign=campaign)
    # SURGICAL real-count overlay: sirf top-level KPIs bind hote hain; detail
    # rows sample hi rehti hain (is_sample_data=True flag waisa hi).
    try:
        topline = _real_topline_counts(client_id)
        if topline:
            k = sample.kpis
            if topline.get("calls"):
                k.total_calls = topline["calls"]
                k.connected_calls = min(k.connected_calls, k.total_calls)
            real_leads = topline.get("leads") or topline.get("inquiries")
            if real_leads:
                k.qualified_leads = real_leads
            if topline.get("calls") or real_leads:
                k.conversion_pct = (
                    min(round((k.qualified_leads / k.connected_calls) * 100, 1), 100.0)
                    if k.connected_calls
                    else 0.0
                )
    except Exception as e:
        logger.debug("customer_dashboard: topline overlay skipped (%s)", e)
    return sample


@router.get("/health")
def customer_dashboard_health() -> dict:
    """Lightweight liveness probe for the customer dashboard API."""
    return {"status": "ok", "service": "customer-dashboard", "sample_data": True}
