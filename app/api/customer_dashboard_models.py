"""Customer dashboard response models — Pydantic schemas for app/api/customer_dashboard.py.

Extracted from customer_dashboard.py (2026-06-20 refactor) — data/route separation.
Re-imported by customer_dashboard.py so external imports keep working.
"""

from datetime import date, datetime  # noqa: F401

from pydantic import BaseModel, Field


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
    id: str = ""  # B4: stable inquiry UUID; used by inline status edit
    status: str = (
        ""  # B4: customer-editable status (defaults to AI tier `score`); kept SEPARATE from score so tier charts/filters stay intact
    )
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


class OnboardingStep(BaseModel):
    id: str
    label: str
    done: bool
    hint: str = ""
    link: str | None = None


class OnboardingChecklist(BaseModel):
    steps: list[OnboardingStep]
    done: int
    total: int
    pct: float
    complete: bool


class TrialBanner(BaseModel):
    """7-day trial → paid conversion nudge (customer portal)."""

    trial: bool = False
    active: bool = False
    expired: bool = False
    days_left: int = 0
    expires_at: str | None = None
    show_pay_cta: bool = False
    starter_price_inr: int = 1199
    message: str = ""


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
    branding: dict | None = None  # reseller white-label (set from Host on subdomains)
    onboarding: OnboardingChecklist | None = None
    trial_banner: TrialBanner | None = None


class CrmSyncLeadResult(BaseModel):
    business: str
    ok: bool
    provider: str | None = None
    record_id: str | None = None
    contact_id: str | None = None
    skipped: str | None = None
    error: str | None = None


class CrmSyncResponse(BaseModel):
    ok: bool
    client_id: str
    campaign: str | None = None
    attempted: int
    delivered: int
    skipped: int
    failed: int
    provider: str | None = None
    message: str
    results: list[CrmSyncLeadResult] = Field(default_factory=list)
