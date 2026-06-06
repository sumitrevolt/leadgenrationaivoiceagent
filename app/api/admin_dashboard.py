"""
Admin Dashboard API
Owner/operator overview + control view for the AI voice-agent lead-gen SaaS.

Provides GET /api/admin/dashboard which returns a single JSON payload consumed
by frontend/admin_dashboard.html. Shape is intentionally identical to the demo
data embedded in that HTML so the page works online OR offline.

Import-safe: depends only on fastapi + pydantic + stdlib.

TODO: bind to real DB (replace the SAMPLE_* builders below with queries against
clients / campaigns / agents / calls tables).
"""
import logging
from typing import List
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])


# ----------------------------------------------------------------------------
# Pydantic models (the contract the HTML expects)
# ----------------------------------------------------------------------------
class KPIs(BaseModel):
    total_clients: int
    active_campaigns: int
    calls_today: int
    qualified_leads_month: int
    revenue_month: int          # ₹
    telephony_cost_month: int   # ₹
    net_margin_pct: float       # %


class Client(BaseModel):
    company: str
    niche: str
    plan: str
    leads_delivered: int
    status: str                 # active | paused
    mrr: int                    # ₹


class Agent(BaseModel):
    id: str
    name: str
    current_client: str
    status: str                 # idle | calling | scraping | error
    calls_made: int
    leads_found: int


class Campaign(BaseModel):
    campaign: str
    client: str
    niche: str
    sources: List[str]
    calls_done: int
    calls_target: int
    leads: int
    status: str                 # active | paused | completed


class Health(BaseModel):
    api: str                    # up | down
    db: str
    telephony: str
    scrapers: str


class RevenueCostSeries(BaseModel):
    labels: List[str]
    revenue: List[int]
    cost: List[int]


class LeadsByNiche(BaseModel):
    labels: List[str]
    values: List[int]


class CallsPerDay(BaseModel):
    labels: List[str]
    values: List[int]


class Charts(BaseModel):
    revenue_cost: RevenueCostSeries
    leads_by_niche: LeadsByNiche
    calls_per_day: CallsPerDay


class DashboardResponse(BaseModel):
    is_sample_data: bool = True
    generated_at: str
    kpis: KPIs
    clients: List[Client]
    agents: List[Agent]
    campaigns: List[Campaign]
    health: Health
    charts: Charts


# ----------------------------------------------------------------------------
# SAMPLE data builders  (TODO: bind to real DB)
# ----------------------------------------------------------------------------
def _sample_kpis() -> KPIs:
    return KPIs(
        total_clients=10,
        active_campaigns=8,
        calls_today=1284,
        qualified_leads_month=742,
        revenue_month=1865000,        # ₹18.65 L
        telephony_cost_month=312000,  # ₹3.12 L
        net_margin_pct=83.3,
    )


def _sample_clients() -> List[Client]:
    return [
        Client(company="SunVolt Solar Pvt Ltd", niche="Solar", plan="Growth", leads_delivered=128, status="active", mrr=45000),
        Client(company="Prestige Realty Group", niche="Real Estate", plan="Scale", leads_delivered=212, status="active", mrr=85000),
        Client(company="SmileCare Dental", niche="Dental", plan="Starter", leads_delivered=64, status="active", mrr=18000),
        Client(company="CoolBreeze HVAC", niche="HVAC", plan="Growth", leads_delivered=97, status="paused", mrr=42000),
        Client(company="UrbanNest Interiors", niche="Interior Design", plan="Growth", leads_delivered=143, status="active", mrr=48000),
        Client(company="GlobalEdu Abroad", niche="Study Abroad", plan="Scale", leads_delivered=305, status="active", mrr=92000),
        Client(company="FitLife Gyms", niche="Fitness", plan="Starter", leads_delivered=51, status="active", mrr=16000),
        Client(company="LegalEase Associates", niche="Legal", plan="Growth", leads_delivered=78, status="paused", mrr=38000),
        Client(company="QuickLoan Finserv", niche="Finance", plan="Scale", leads_delivered=189, status="active", mrr=78000),
        Client(company="GreenScape Landscaping", niche="Landscaping", plan="Starter", leads_delivered=44, status="active", mrr=15000),
    ]


def _sample_agents() -> List[Agent]:
    return [
        Agent(id="AG-01", name="Aarav", current_client="Prestige Realty Group", status="calling", calls_made=342, leads_found=58),
        Agent(id="AG-02", name="Diya", current_client="GlobalEdu Abroad", status="calling", calls_made=298, leads_found=71),
        Agent(id="AG-03", name="Kabir", current_client="SunVolt Solar Pvt Ltd", status="scraping", calls_made=156, leads_found=33),
        Agent(id="AG-04", name="Anaya", current_client="UrbanNest Interiors", status="idle", calls_made=204, leads_found=41),
        Agent(id="AG-05", name="Vivaan", current_client="QuickLoan Finserv", status="calling", calls_made=271, leads_found=49),
        Agent(id="AG-06", name="Ishaan", current_client="CoolBreeze HVAC", status="error", calls_made=88, leads_found=12),
    ]


def _sample_campaigns() -> List[Campaign]:
    return [
        Campaign(campaign="Solar Q2 Push", client="SunVolt Solar Pvt Ltd", niche="Solar", sources=["Google Maps", "JustDial"], calls_done=620, calls_target=1000, leads=88, status="active"),
        Campaign(campaign="Premium Homes Drive", client="Prestige Realty Group", niche="Real Estate", sources=["IndiaMart", "LinkedIn"], calls_done=910, calls_target=1200, leads=142, status="active"),
        Campaign(campaign="Smile Bookings", client="SmileCare Dental", niche="Dental", sources=["Google Maps"], calls_done=300, calls_target=300, leads=64, status="completed"),
        Campaign(campaign="Cooling Season Leads", client="CoolBreeze HVAC", niche="HVAC", sources=["JustDial", "Google Maps"], calls_done=410, calls_target=800, leads=53, status="paused"),
        Campaign(campaign="Home Makeover", client="UrbanNest Interiors", niche="Interior Design", sources=["Instagram", "Google Maps"], calls_done=560, calls_target=900, leads=97, status="active"),
        Campaign(campaign="Study Abroad Intake", client="GlobalEdu Abroad", niche="Study Abroad", sources=["LinkedIn", "Meta Ads"], calls_done=1180, calls_target=1500, leads=205, status="active"),
        Campaign(campaign="Personal Loan Blitz", client="QuickLoan Finserv", niche="Finance", sources=["IndiaMart", "JustDial"], calls_done=740, calls_target=1100, leads=121, status="active"),
        Campaign(campaign="New Member Hunt", client="FitLife Gyms", niche="Fitness", sources=["Google Maps"], calls_done=180, calls_target=400, leads=29, status="active"),
    ]


def _sample_health() -> Health:
    return Health(api="up", db="up", telephony="up", scrapers="down")


def _sample_charts() -> Charts:
    return Charts(
        revenue_cost=RevenueCostSeries(
            labels=["Jan", "Feb", "Mar", "Apr", "May", "Jun"],
            revenue=[980000, 1150000, 1320000, 1480000, 1690000, 1865000],
            cost=[210000, 238000, 256000, 274000, 298000, 312000],
        ),
        leads_by_niche=LeadsByNiche(
            labels=["Solar", "Real Estate", "Dental", "HVAC", "Interior", "Study Abroad", "Finance", "Other"],
            values=[128, 212, 64, 97, 143, 305, 189, 95],
        ),
        calls_per_day=CallsPerDay(
            labels=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            values=[1120, 1340, 1280, 1410, 1284, 760, 410],
        ),
    )


# ----------------------------------------------------------------------------
# DB-backed builder (real data). Import-safe: DB imports are local + guarded so
# this module still mounts when DB deps/connection are missing.
# ----------------------------------------------------------------------------
def _build_from_db() -> "DashboardResponse | None":
    """
    Aggregate the admin dashboard from the real DB.
    Returns None when the DB is unavailable OR has no clients (so the caller
    falls back to sample data with is_sample_data=True).
    """
    try:
        from collections import defaultdict
        from app.models.base import get_db_session
        from app.models.client import Client as ClientModel
        from app.models.campaign import Campaign as CampaignModel, CampaignStatus
        from app.models.agent import Agent as AgentModel
        from app.models.lead import Lead as LeadModel, LeadStatus
        from app.models.call_log import CallLog as CallLogModel
        from app.models.billing_record import BillingRecord, BillingRecordType
    except Exception as e:
        logger.warning("admin_dashboard: DB models unavailable, using sample (%s)", e)
        return None

    try:
        with get_db_session() as db:
            client_rows = db.query(ClientModel).all()
            if not client_rows:
                return None

            campaign_rows = db.query(CampaignModel).all()
            agent_rows = db.query(AgentModel).all()

            now = datetime.utcnow()
            today = now.date()

            # ----- clients panel + MRR -----
            clients: List[Client] = []
            total_mrr = 0
            for c in client_rows:
                leads_delivered = db.query(LeadModel).filter(
                    LeadModel.assigned_to == c.id
                ).count()
                mrr = int((c.monthly_amount or 0) / 100)
                total_mrr += mrr if (c.status and c.status.value == "active") else 0
                clients.append(Client(
                    company=c.business_name or "Unknown",
                    niche=c.industry or "-",
                    plan=(c.plan.value.title() if c.plan else "Starter"),
                    leads_delivered=leads_delivered,
                    status=(c.status.value if c.status else "active"),
                    mrr=mrr,
                ))

            # ----- agents panel -----
            agents: List[Agent] = []
            for a in agent_rows:
                agents.append(Agent(
                    id=a.agent_code or str(a.id)[:8],
                    name=a.name or "Agent",
                    current_client=a.current_client_name or "-",
                    status=(a.status.value if a.status else "idle"),
                    calls_made=a.calls_made or 0,
                    leads_found=a.leads_found or 0,
                ))

            # ----- campaigns panel -----
            campaigns: List[Campaign] = []
            active_campaigns = 0
            for cp in campaign_rows:
                st = cp.status.value if cp.status else "draft"
                if st in ("running", "scheduled"):
                    active_campaigns += 1
                ui_status = "active" if st == "running" else st
                campaigns.append(Campaign(
                    campaign=cp.name or "Campaign",
                    client=cp.client_name or "-",
                    niche=cp.niche or "-",
                    sources=[],
                    calls_done=cp.leads_called or 0,
                    calls_target=cp.target_lead_count or 0,
                    leads=cp.leads_qualified or 0,
                    status=ui_status,
                ))

            # ----- KPIs -----
            calls_today = db.query(CallLogModel).filter(
                CallLogModel.initiated_at >= datetime(today.year, today.month, today.day)
            ).count()
            qualified_month = db.query(LeadModel).filter(
                LeadModel.created_at >= datetime(now.year, now.month, 1),
                LeadModel.status.in_([
                    LeadStatus.QUALIFIED, LeadStatus.APPOINTMENT, LeadStatus.CONVERTED
                ]),
            ).count()

            # revenue + telephony cost this month (from billing records, in paise)
            br = db.query(BillingRecord).filter(
                BillingRecord.period_year == now.year,
                BillingRecord.period_month == now.month,
            ).all()
            revenue_month = sum(
                (r.amount or 0) for r in br
                if r.record_type != BillingRecordType.TELEPHONY
            )
            telephony_cost_month = sum(
                (r.cost or 0) for r in br
            ) + sum((c.call_cost or 0) for c in db.query(CallLogModel).filter(
                CallLogModel.initiated_at >= datetime(now.year, now.month, 1)
            ).all())
            revenue_inr = int(revenue_month / 100) or total_mrr
            cost_inr = int(telephony_cost_month / 100)
            net_margin = round(((revenue_inr - cost_inr) / revenue_inr) * 100, 1) if revenue_inr else 0.0

            kpis = KPIs(
                total_clients=len(client_rows),
                active_campaigns=active_campaigns,
                calls_today=calls_today,
                qualified_leads_month=qualified_month,
                revenue_month=revenue_inr,
                telephony_cost_month=cost_inr,
                net_margin_pct=net_margin,
            )

            # ----- charts -----
            # leads by niche
            niche_counts: dict = defaultdict(int)
            for l in db.query(LeadModel).all():
                niche_counts[(l.niche or "Other").title()] += 1
            niche_items = sorted(niche_counts.items(), key=lambda kv: kv[1], reverse=True)
            leads_by_niche = LeadsByNiche(
                labels=[k for k, _ in niche_items] or ["Other"],
                values=[v for _, v in niche_items] or [0],
            )

            # calls per day (last 7 days)
            from datetime import timedelta
            day_labels, day_values = [], []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                start = datetime(d.year, d.month, d.day)
                end = start + timedelta(days=1)
                cnt = db.query(CallLogModel).filter(
                    CallLogModel.initiated_at >= start,
                    CallLogModel.initiated_at < end,
                ).count()
                day_labels.append(d.strftime("%a"))
                day_values.append(cnt)
            calls_per_day = CallsPerDay(labels=day_labels, values=day_values)

            # revenue vs cost by month (last 6 months from billing records)
            rc_labels, rc_rev, rc_cost = [], [], []
            for i in range(5, -1, -1):
                m = now.month - i
                y = now.year
                while m <= 0:
                    m += 12
                    y -= 1
                month_br = [r for r in db.query(BillingRecord).filter(
                    BillingRecord.period_year == y,
                    BillingRecord.period_month == m,
                ).all()]
                rev = int(sum((r.amount or 0) for r in month_br
                              if r.record_type != BillingRecordType.TELEPHONY) / 100)
                cst = int(sum((r.cost or 0) for r in month_br) / 100)
                rc_labels.append(datetime(y, m, 1).strftime("%b"))
                rc_rev.append(rev)
                rc_cost.append(cst)
            revenue_cost = RevenueCostSeries(labels=rc_labels, revenue=rc_rev, cost=rc_cost)

            charts = Charts(
                revenue_cost=revenue_cost,
                leads_by_niche=leads_by_niche,
                calls_per_day=calls_per_day,
            )

            health = Health(api="up", db="up", telephony="up", scrapers="up")

            return DashboardResponse(
                is_sample_data=False,
                generated_at=now.isoformat() + "Z",
                kpis=kpis,
                clients=clients,
                agents=agents,
                campaigns=campaigns,
                health=health,
                charts=charts,
            )
    except Exception as e:
        logger.warning("admin_dashboard: DB query failed, using sample (%s)", e)
        return None


# ----------------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardResponse)
async def get_admin_dashboard() -> DashboardResponse:
    """
    Owner/operator dashboard payload.

    Aggregates clients, campaigns, agents, calls and billing from the real DB.
    Falls back to clearly-marked SAMPLE data (is_sample_data=True) when the DB
    is unavailable or empty.
    """
    real = _build_from_db()
    if real is not None:
        return real

    return DashboardResponse(
        is_sample_data=True,
        generated_at=datetime.utcnow().isoformat() + "Z",
        kpis=_sample_kpis(),
        clients=_sample_clients(),
        agents=_sample_agents(),
        campaigns=_sample_campaigns(),
        health=_sample_health(),
        charts=_sample_charts(),
    )
