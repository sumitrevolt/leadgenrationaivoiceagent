"""Customer dashboard response models — Pydantic schemas for app/api/customer_dashboard.py.

Extracted from customer_dashboard.py (2026-06-20 refactor) — data/route separation.
Re-imported by customer_dashboard.py so external imports keep working.
"""

from datetime import date, datetime  # noqa: F401

from pydantic import BaseModel, Field


def _starter_price_inr_default() -> int:
    """Canonical starter price (packages.py single source) — import-safe (lazy)."""
    try:
        from app.marketing.packages import get_starter_price_inr

        return get_starter_price_inr()
    except Exception:
        return 1999


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
    # Product-2 delivery fix (2026-07-06): the AI value the voice customer PAID for
    # — Hinglish transcript + AI summary + per-call qualification report + sentiment.
    # These live on CallLog but were dropped from CallRow, so the promised "call
    # transcripts + AI summary aapke dashboard me" reached NO customer surface.
    # Optional (older rows / calls with no transcript => "").
    transcript: str = ""
    summary: str = ""
    qualification: str = ""
    sentiment: str = ""


class LeadRow(BaseModel):
    id: str = ""  # B4: stable inquiry UUID; used by inline status edit
    status: str = ""  # B4: customer-editable status (defaults to AI tier `score`); kept SEPARATE from score so tier charts/filters stay intact
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
    starter_price_inr: int = Field(
        default_factory=_starter_price_inr_default,
        description="Starter plan monthly ₹ (canonical from packages.py)",
    )
    message: str = ""


class ApprovalBanner(BaseModel):
    """Customer-safe nudge for content waiting on the owner's decision."""

    show: bool = False
    count: int = 0
    urgency: str = "normal"
    message: str = ""
    target: str = "approvalCard"


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
    approval_banner: ApprovalBanner | None = None
    social_error: str | None = None


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


# --------------------------------------------------------------------------- #
# Customer "AI Marketing Team" — virtual agentic office (per-client activity)  #
# Roster names come from app.platform.team.STAFF (single source of truth); the #
# per-agent activity lines are derived ONLY from THIS client's data, never the #
# agency-wide event feed (so a customer can't see other clients' work).        #
# --------------------------------------------------------------------------- #
class TeamAgentCard(BaseModel):
    key: str = Field(..., description="STAFF key e.g. isha/rohan/dev/manager")
    name: str
    emoji: str
    title: str = Field(..., description="Customer-friendly role")
    duties: str = Field(..., description="Short 'what they do for you' line")
    status: str = Field("active", description="working | active | idle")
    status_label: str = Field("Active", description="Hinglish status pill text")
    task: str = Field("", description="Current client-scoped activity line")
    metric: str = Field("", description="Headline number chip e.g. '12 post'")
    accent: str = Field("#6d28d9", description="Card accent hex colour")


class CustomerTeamResponse(BaseModel):
    client_id: str
    generated_at: str
    is_sample_data: bool = False
    headline: str = ""
    summary: str = ""
    busy_count: int = 0
    total_today: int = 0
    agents: list[TeamAgentCard] = Field(default_factory=list)
