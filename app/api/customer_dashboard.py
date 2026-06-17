"""
Customer-facing Dashboard API
==============================
Powers frontend/customer_dashboard.html.

The END CUSTOMER here is a small business (the SaaS's client). They want to see
the leads + enquiries our platform generated for them and the calls the AI voice
agent made on their behalf.

Data is REAL (no fictional "SunVolt Energy" sample anymore). Sources, all
best-effort + never-500, mirror admin_dashboard.py's real-data approach:
  - DB (Lead, CallLog, Campaign) keyed by client_id  -> richest view
  - data/inquiries.jsonl filtered by this client      -> leads (mini-site/website)
    (matched on source_slug / client_id / business name / phone)
  - data/content_queue/<id>.jsonl                     -> content posts count
  - data/marketing_clients.jsonl                      -> the client's own record

When NOTHING real exists for a client, the dashboard returns honest ZEROS with
is_sample_data=True (so the UI can show a "no data yet" state) — it NEVER invents
businesses/leads. This module stays import-safe: heavy imports are local+guarded.

Mount in main.py with:
    from app.api.customer_dashboard import router as customer_router
    app.include_router(customer_router)
(Router already carries prefix="/api/customer".)
"""

import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from app.api.customer_auth import require_customer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer", tags=["Customer Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


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
# Onboarding checklist — drives customer portal getting-started wizard         #
# --------------------------------------------------------------------------- #
def _build_onboarding_checklist(
    client_id: str,
    client_rec: dict | None,
    leads_count: int,
    content_count: int,
) -> OnboardingChecklist:
    """Compute setup progress from existing stores (no new deps)."""
    try:
        from app.api.customer_auth import client_has_login
    except Exception:
        def client_has_login(_cid: str) -> bool:  # type: ignore[misc]
            return False

    rec = client_rec or _client_record(client_id)
    slug = str((rec or {}).get("slug") or "").strip()
    steps = [
        OnboardingStep(
            id="login",
            label="Portal login set",
            done=client_has_login(client_id),
            hint="Admin se login email+password issue karvao",
        ),
        OnboardingStep(
            id="profile",
            label="Business profile complete",
            done=bool(rec and rec.get("business_name") and rec.get("phone")),
            hint="Business naam + phone add karo",
        ),
        OnboardingStep(
            id="setup",
            label="AI setup (website → knowledge base)",
            done=bool(rec and rec.get("setup_done")),
            hint="Website URL do — hum KB auto-seed karenge",
        ),
        OnboardingStep(
            id="minisite",
            label="Mini-site live",
            done=bool(slug),
            hint="Aapka /b/slug page customer ko dikhega",
            link=f"/b/{slug}" if slug else None,
        ),
        OnboardingStep(
            id="content",
            label="Pehla marketing post ready",
            done=content_count > 0,
            hint="Roz ka post yahan dikhega jab content queue bharegi",
        ),
        OnboardingStep(
            id="leads",
            label="Pehli lead / enquiry aayi",
            done=leads_count > 0,
            hint="Mini-site ya widget se enquiry bhej kar test karo",
        ),
    ]
    done = sum(1 for s in steps if s.done)
    total = len(steps)
    pct = round(done / total * 100, 1) if total else 0.0
    return OnboardingChecklist(
        steps=steps,
        done=done,
        total=total,
        pct=pct,
        complete=done >= total,
    )


def _enrich_dashboard(resp: DashboardResponse, client_id: str) -> DashboardResponse:
    """Attach onboarding checklist using real client_id from JWT."""
    client_rec = _client_record(client_id)
    content_count = _content_posts_count(client_id, client_rec)
    onboarding = _build_onboarding_checklist(
        client_id,
        client_rec,
        len(resp.leads or []),
        content_count,
    )
    return resp.model_copy(update={"client_id": client_id, "onboarding": onboarding})


# --------------------------------------------------------------------------- #
# Real per-client builder from FILE sources (no DB needed)                     #
# Mirrors admin_dashboard.py: jsonl-first, never invents data.                 #
# --------------------------------------------------------------------------- #
def _read_inquiries() -> list[dict]:
    """data/inquiries.jsonl ki saari lines (parse-safe). Never raises."""
    out: list[dict] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return out
        with open(_INQUIRIES_FILE, encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                    if isinstance(rec, dict):
                        out.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("customer_dashboard: inquiries read failed (%s)", e)
    return out


def _client_record(client_id: str) -> dict | None:
    """clients_store se is client ka record (slug/business_name/niche match)."""
    try:
        from app.marketing.clients_store import get_by_slug, get_client

        return get_client(client_id) or get_by_slug(client_id)
    except Exception:
        return None


def _inquiries_for_client(client_id: str, client_rec: dict | None) -> list[dict]:
    """Is client se related inquiries — source_slug / client_id / business / phone
    par match. client "demo" ho aur koi record na ho to ALL inquiries (platform
    overview), warna sirf is client ki."""
    rows = _read_inquiries()
    if not rows:
        return []
    cid = (client_id or "").strip().lower()
    slug = str((client_rec or {}).get("slug") or "").strip().lower()
    rec_id = str((client_rec or {}).get("id") or "").strip().lower()
    biz = str((client_rec or {}).get("business_name") or "").strip().lower()
    phone_d = "".join(ch for ch in str((client_rec or {}).get("phone") or "") if ch.isdigit())[-10:]

    # No client identity at all (default "demo" with no stored record) =>
    # show every inquiry as a platform-wide overview (still REAL data).
    if not client_rec and cid in ("", "demo"):
        return rows

    matched: list[dict] = []
    for r in rows:
        r_slug = str(r.get("source_slug") or "").strip().lower()
        r_cid = str(r.get("client_id") or "").strip().lower()
        r_biz = str(r.get("business_name") or "").strip().lower()
        r_ph = "".join(ch for ch in str(r.get("phone") or "") if ch.isdigit())[-10:]
        if slug and r_slug == slug:
            matched.append(r)
        elif rec_id and r_cid == rec_id:
            matched.append(r)
        elif cid and r_cid == cid:
            matched.append(r)
        elif biz and r_biz == biz:
            matched.append(r)
        elif phone_d and r_ph and r_ph == phone_d:
            matched.append(r)
    return matched


def _content_posts_count(client_id: str, client_rec: dict | None) -> int:
    """Is client ke content-queue items (posted+approved+draft) — posts ka proxy."""
    try:
        from app.marketing.auto_content import list_queue

        rid = str((client_rec or {}).get("id") or client_id or "").strip()
        if not rid:
            return 0
        return len(list_queue(rid, limit=500))
    except Exception:
        return 0


def _lead_score_from_inquiry(rec: dict) -> str:
    """Inquiry ko Hot/Warm/Cold me bucket karo (lead_scoring jaisa simple)."""
    msg = str(rec.get("message") or "")
    pt = str(rec.get("preferred_time") or "")
    # preferred-time diya + message hai => high intent
    if pt and len(msg) >= 20:
        return "Hot"
    if pt or len(msg) >= 12:
        return "Warm"
    return "Cold"


def _mask_full_phone_local(num) -> str:
    digits = "".join(c for c in (num or "") if c.isdigit())[-10:]
    if len(digits) < 4:
        return "+91 XXXXXXXXXX"
    return f"+91 {digits[:2]}XXXXXX{digits[-2:]}"


def _parse_dt(rec: dict) -> datetime:
    raw = str(rec.get("at") or rec.get("created_at") or "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(raw.split("+")[0].rstrip("Z") + ("Z" if raw.endswith("Z") else ""), fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(raw.replace("Z", ""))
    except Exception:
        return datetime.utcnow()


def _build_from_files(client_id: str, campaign: str | None) -> DashboardResponse:
    """File-based REAL dashboard: inquiries.jsonl + content queue + client record.

    is_sample_data=False jab koi real activity ho; agar bilkul kuch na ho to
    honest zeros (is_sample_data=True, par koi fictional business NAHI)."""
    client_rec = _client_record(client_id)
    inquiries = _inquiries_for_client(client_id, client_rec)
    posts = _content_posts_count(client_id, client_rec)

    # ----- leads from inquiries (each inquiry = a lead the client got) -----
    leads: list[LeadRow] = []
    from collections import defaultdict

    tier_counts = {"Hot": 0, "Warm": 0, "Cold": 0}
    city_counts: dict = defaultdict(int)
    day_counts: dict = defaultdict(int)

    inquiries_sorted = sorted(inquiries, key=_parse_dt, reverse=True)
    for r in inquiries_sorted:
        tier = _lead_score_from_inquiry(r)
        tier_counts[tier] += 1
        city = str(r.get("city") or "").strip() or "-"
        if city != "-":
            city_counts[city] += 1
        dt = _parse_dt(r)
        day_counts[dt.strftime("%b %d")] += 1
        qual_bits = []
        if r.get("preferred_time"):
            qual_bits.append(f"Time: {r['preferred_time']}")
        if r.get("message"):
            qual_bits.append(str(r["message"])[:70])
        leads.append(
            LeadRow(
                business=str(r.get("business_name") or "-")[:80],
                contact=str(r.get("name") or "-")[:80],
                phone=(
                    f"+91 {r['phone']}"
                    if r.get("phone") and not str(r["phone"]).startswith("+")
                    else str(r.get("phone") or "-")
                ),
                city=city,
                niche=str(r.get("niche") or (client_rec or {}).get("niche") or "general"),
                score=tier,
                qualification=", ".join(qual_bits) or "Website/mini-site enquiry",
                date=dt.strftime("%Y-%m-%d"),
            )
        )

    # ----- calls from agent_events (swara) keyed loosely (platform-level) -----
    calls, connected, calls_today = _calls_from_events(client_id, client_rec)

    qualified = tier_counts["Hot"] + tier_counts["Warm"]
    total_leads = len(leads)
    conv = round((qualified / connected) * 100, 1) if connected else 0.0
    est_cost = int(connected * 1.5 * 0.65)  # ~₹0.65/min, ~1.5 min avg/connected

    has_real = bool(total_leads or calls or posts)

    kpis = Kpis(
        total_calls=len(calls),
        connected_calls=connected,
        qualified_leads=qualified or total_leads,
        conversion_pct=conv,
        est_cost_inr=est_cost,
    )

    calls_per_day = [SeriesPoint(label=k, value=v) for k, v in sorted(day_counts.items())]
    leads_by_status = [SeriesPoint(label=k, value=v) for k, v in tier_counts.items()]
    leads_by_city = [
        SeriesPoint(label=c, value=n)
        for c, n in sorted(city_counts.items(), key=lambda kv: kv[1], reverse=True)[:6]
    ]

    campaigns = [Campaign(id="all", name="All Campaigns")]

    return DashboardResponse(
        is_sample_data=not has_real,  # honest: zeros + flag jab kuch na ho
        client_id=(str((client_rec or {}).get("business_name") or client_id) or client_id),
        generated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        campaigns=campaigns,
        kpis=kpis,
        calls=calls[:50],
        leads=leads[:100],
        charts=ChartsData(
            calls_per_day=calls_per_day,
            leads_by_status=leads_by_status,
            leads_by_city=leads_by_city,
        ),
    )


def _calls_from_events(client_id: str, client_rec: dict | None):
    """AI-staff (swara) call activity → CallRow list + connected + calls_today.

    Per-client call mapping abhi nahi (calls platform-level log hote), isliye
    detail rows skip — sirf KPI counts. Returns ([], count, today)."""
    total = 0
    today = 0
    try:
        from app.models.agent_event import AgentEvent
        from app.models.base import get_db_session

        with get_db_session() as db:
            try:
                total = (
                    db.query(AgentEvent)
                    .filter(AgentEvent.member == "swara")
                    .filter(AgentEvent.action.in_(["call_placed", "call_finished", "auto_callback"]))
                    .count()
                )
            except Exception:
                total = 0
    except Exception:
        total = 0
    # connected ~ all placed (no per-call status here); detail rows intentionally empty
    return [], int(total), int(today)


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
# Routes                                                                       #
# --------------------------------------------------------------------------- #
@router.get("/dashboard", response_model=DashboardResponse)
def get_customer_dashboard(
    request: Request,
    campaign: str | None = Query(None, description="Optional campaign id to filter by"),
    client_id: str = Depends(require_customer),
) -> DashboardResponse:
    """
    Return the full dashboard payload for a customer — REAL data only.

    1. Real DB (Lead, CallLog, Campaign) keyed by client_id + campaign — richest.
    2. Else FILE-based real builder: this client's inquiries (inquiries.jsonl,
       matched by source_slug / client_id / business / phone) + content-queue
       posts + agent-event call counts.
    No fictional "SunVolt Energy" sample. If a client genuinely has zero
    activity the response carries honest zeros with is_sample_data=True (UI
    shows a clean "no data yet" state) — never invented businesses or leads.
    """
    resp = _build_from_db(client_id=client_id, campaign=campaign)
    if resp is None:
        resp = _build_from_files(client_id=client_id, campaign=campaign)
    resp = _enrich_dashboard(resp, client_id)
    # White-label: on a reseller subdomain the middleware set request.state.tenant.
    try:
        resp.branding = getattr(request.state, "tenant", None)
    except Exception:
        pass
    return resp


@router.get("/speed-to-lead")
def customer_speed_to_lead(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    client_id: str = Depends(require_customer),
) -> dict:
    """Client-scoped speed-to-lead SLA metric for dashboard badge."""
    from app.platform import speed_to_lead

    client_rec = _client_record(client_id)
    return speed_to_lead.summary_for_client(client_id, client_rec, days)


@router.post("/dashboard/send-to-crm", response_model=CrmSyncResponse)
async def send_dashboard_leads_to_crm(
    campaign: str | None = Query(None, description="Optional campaign id to filter by"),
    client_id: str = Depends(require_customer),
) -> CrmSyncResponse:
    """Customer ke visible dashboard leads ko configured CRM me push karo.

    AuthZ: client_id JWT se aata hai (query-param tenancy nahi).
    """
    resp = _build_from_db(client_id=client_id, campaign=campaign)
    if resp is None:
        resp = _build_from_files(client_id=client_id, campaign=campaign)
    leads = list(resp.leads or [])[:100]
    if not leads:
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=0,
            delivered=0,
            skipped=0,
            failed=0,
            provider=None,
            message="Sync karne ke liye leads nahi mili.",
            results=[],
        )
    try:
        from app.platform import crm_sync
    except Exception as e:
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=len(leads),
            delivered=0,
            skipped=0,
            failed=len(leads),
            provider=None,
            message="CRM module unavailable.",
            results=[
                CrmSyncLeadResult(
                    business=(l.business or "-"),
                    ok=False,
                    error=str(e)[:140],
                )
                for l in leads
            ],
        )

    status = crm_sync.status(client_id=client_id)
    provider = str(status.get("provider") or "none")
    if provider == "none":
        return CrmSyncResponse(
            ok=False,
            client_id=client_id,
            campaign=campaign,
            attempted=len(leads),
            delivered=0,
            skipped=len(leads),
            failed=0,
            provider=provider,
            message="CRM configured nahi hai. Admin se Zoho/HubSpot connect karvao.",
            results=[
                CrmSyncLeadResult(
                    business=(l.business or "-"),
                    ok=False,
                    provider=provider,
                    skipped="no CRM configured",
                )
                for l in leads
            ],
        )

    results: list[CrmSyncLeadResult] = []
    delivered = skipped = failed = 0
    for l in leads:
        payload = {
            "business_name": l.business or "",
            "contact_name": l.contact or "",
            "phone": l.phone or "",
            "city": l.city or "",
            "niche": l.niche or "",
            "score": l.score or "",
            "qualification": l.qualification or "",
            "source": "customer_dashboard",
        }
        out = await crm_sync.push_lead(payload, client_id=client_id, note=l.qualification or "")
        ok = bool(out.get("ok"))
        if ok:
            delivered += 1
        elif out.get("skipped"):
            skipped += 1
        else:
            failed += 1
        results.append(
            CrmSyncLeadResult(
                business=l.business or "-",
                ok=ok,
                provider=str(out.get("provider") or provider),
                record_id=(str(out.get("record_id")) if out.get("record_id") else None),
                contact_id=(str(out.get("contact_id")) if out.get("contact_id") else None),
                skipped=(str(out.get("skipped")) if out.get("skipped") else None),
                error=(str(out.get("error")) if out.get("error") else None),
            )
        )
    message = (
        f"{delivered} lead CRM me sync hui."
        if delivered
        else ("CRM configured hai, par koi lead sync nahi hui." if failed else "CRM sync skipped.")
    )
    return CrmSyncResponse(
        ok=delivered > 0,
        client_id=client_id,
        campaign=campaign,
        attempted=len(leads),
        delivered=delivered,
        skipped=skipped,
        failed=failed,
        provider=provider,
        message=message,
        results=results,
    )


@router.get("/health")
def customer_dashboard_health() -> dict:
    """Lightweight liveness probe for the customer dashboard API."""
    return {"status": "ok", "service": "customer-dashboard"}
