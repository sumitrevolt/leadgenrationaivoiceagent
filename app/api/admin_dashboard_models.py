"""Admin dashboard response models — Pydantic schemas for app/api/admin_dashboard.py.

Extracted from admin_dashboard.py (2026-06-20 refactor) — data/route separation.
Re-imported by admin_dashboard.py so external imports keep working.
"""

from pydantic import BaseModel, Field  # noqa: F401


class KPIs(BaseModel):
    total_clients: int
    active_campaigns: int
    calls_today: int
    qualified_leads_month: int
    revenue_month: int  # ₹
    telephony_cost_month: int  # ₹
    net_margin_pct: float  # %


class Client(BaseModel):
    client_id: str = ""
    company: str
    niche: str
    product: str = "marketing"  # marketing | voice | combo (ADR-009)
    plan: str
    leads_delivered: int
    status: str  # active | paused
    mrr: int  # ₹


class Agent(BaseModel):
    id: str
    name: str
    current_client: str
    status: str  # idle | calling | scraping | error
    calls_made: int
    leads_found: int


class Campaign(BaseModel):
    campaign: str
    client: str
    niche: str
    sources: list[str]
    calls_done: int
    calls_target: int
    leads: int
    status: str  # active | paused | completed


class Health(BaseModel):
    api: str  # up | down
    db: str
    telephony: str
    scrapers: str


class RevenueCostSeries(BaseModel):
    labels: list[str]
    revenue: list[int]
    cost: list[int]


class LeadsByNiche(BaseModel):
    labels: list[str]
    values: list[int]


class CallsPerDay(BaseModel):
    labels: list[str]
    values: list[int]


class Charts(BaseModel):
    revenue_cost: RevenueCostSeries
    leads_by_niche: LeadsByNiche
    calls_per_day: CallsPerDay


class DashboardResponse(BaseModel):
    is_sample_data: bool = False
    generated_at: str
    kpis: KPIs
    clients: list[Client]
    agents: list[Agent]
    campaigns: list[Campaign]
    health: Health
    charts: Charts
    # Real aggregates surfaced as-is for new KPI cards / future views.
    live: dict = {}
