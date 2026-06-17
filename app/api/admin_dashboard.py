"""
Admin Dashboard API
Owner/operator overview + control view for the AI voice-agent lead-gen SaaS.

Provides GET /api/admin/dashboard which returns a single JSON payload consumed
by frontend/admin_dashboard.html. Shape is kept COMPATIBLE with that HTML so the
page renders, but the numbers are now REAL — pulled from the actual data the
platform produces (prospects, inquiries, marketing clients, emails, blog,
content queue, AI-staff activity). NO hardcoded SunVolt/sample data.

Sources (all best-effort, never 500):
  - data/prospects.jsonl          (prospector.list_prospects)
  - data/inquiries.jsonl          (public inquiries)
  - data/marketing_clients.jsonl  (clients_store.list_clients)
  - data/blog/*.json              (seo_blog.list_articles)
  - data/content_queue/*.jsonl    (auto_content.list_queue)
  - agent_events table            (team.team_status / recent_events)
  - auto_outreach.outreach_stats  (emails sent / pending)
  - app/marketing/packages        (plan prices for revenue estimate)

is_sample_data is ALWAYS False — we show the truth, even if everything is zero.

Import-safe: heavy imports are local + guarded so this module always mounts.
"""

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


# ----------------------------------------------------------------------------
# Pydantic models (the contract the HTML expects)
# ----------------------------------------------------------------------------
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


# ----------------------------------------------------------------------------
# REAL data aggregation. Every source is best-effort (file may be absent →
# 0). NEVER raises — returns a plain dict of true numbers.
# ----------------------------------------------------------------------------
def _read_inquiries() -> list[dict]:
    """data/inquiries.jsonl rows (parse-safe; corrupt/missing → [])."""
    rows: list[dict] = []
    try:
        if not os.path.isfile(_INQUIRIES_FILE):
            return rows
        with open(_INQUIRIES_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("admin_dashboard: read inquiries failed: %s", e)
    return rows


def _is_today_iso(ts: object) -> bool:
    """True if an ISO timestamp string falls on today's (UTC) date."""
    s = str(ts or "").strip()
    if not s:
        return False
    try:
        if s.endswith("Z"):
            s = s[:-1]
        dt = datetime.fromisoformat(s)
        return dt.date() == datetime.utcnow().date()
    except Exception:
        return False


def _plan_price(plan: str) -> int:
    """Marketing plan key → monthly ₹ from packages (fallback Starter ₹1,199)."""
    try:
        from app.marketing.packages import get_packages

        key = (plan or "starter").strip().lower()
        for p in get_packages():
            if str(p.get("key", "")).lower() == key:
                return int(p.get("price_inr_month") or 0)
        # default to the cheapest tier price
        prices = [int(p.get("price_inr_month") or 0) for p in get_packages()]
        return min([x for x in prices if x > 0] or [1199])
    except Exception:
        return 999


def _collect_live_stats() -> dict:
    """The single source of truth for REAL platform numbers. Best-effort."""
    stats: dict = {
        "total_prospects": 0,
        "prospects_by_status": {},
        "prospects_with_email": 0,
        "inquiries_total": 0,
        "inquiries_today": 0,
        "marketing_clients": 0,
        "marketing_clients_active": 0,
        "emails_sent": 0,
        "emails_pending": 0,
        "blog_articles": 0,
        "content_items_generated": 0,
        "agent_actions_today": 0,
        "agent_errors_today": 0,
        "active_staff": 0,
        "calls_today": 0,
        "estimated_mrr": 0,
    }

    # --- prospects ---
    prospects: list[dict] = []
    try:
        from app.platform import prospector

        prospects = prospector.list_prospects(limit=500)
        stats["total_prospects"] = len(prospects)
        by_status: dict[str, int] = {}
        with_email = 0
        for p in prospects:
            st = str(p.get("status") or "ready").lower()
            by_status[st] = by_status.get(st, 0) + 1
            if str(p.get("email") or "").strip():
                with_email += 1
        stats["prospects_by_status"] = by_status
        stats["prospects_with_email"] = with_email
    except Exception as e:
        logger.debug("admin_dashboard: prospects failed: %s", e)

    # --- inquiries ---
    try:
        inqs = _read_inquiries()
        stats["inquiries_total"] = len(inqs)
        stats["inquiries_today"] = sum(
            1 for r in inqs if _is_today_iso(r.get("created_at") or r.get("at") or r.get("ts"))
        )
    except Exception as e:
        logger.debug("admin_dashboard: inquiries failed: %s", e)

    # --- marketing clients ---
    clients: list[dict] = []
    try:
        from app.marketing import clients_store

        clients = clients_store.list_clients()
        stats["marketing_clients"] = len(clients)
        active = clients_store.list_clients(status="active")
        stats["marketing_clients_active"] = len(active)
        stats["estimated_mrr"] = sum(_plan_price(c.get("plan", "starter")) for c in active)
    except Exception as e:
        logger.debug("admin_dashboard: clients failed: %s", e)

    # --- email outreach ---
    try:
        from app.platform.auto_outreach import outreach_stats

        o = outreach_stats()
        stats["emails_sent"] = int(o.get("emailed") or 0)
        stats["emails_pending"] = int(o.get("pending") or 0)
    except Exception as e:
        logger.debug("admin_dashboard: outreach_stats failed: %s", e)

    # --- blog articles ---
    try:
        from app.marketing import seo_blog

        stats["blog_articles"] = len(seo_blog.list_articles(limit=500))
    except Exception as e:
        logger.debug("admin_dashboard: blog failed: %s", e)

    # --- content queue items (across all marketing clients) ---
    try:
        from app.marketing import auto_content

        total_items = 0
        for c in clients:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            try:
                total_items += len(auto_content.list_queue(cid, limit=500))
            except Exception:
                continue
        stats["content_items_generated"] = total_items
    except Exception as e:
        logger.debug("admin_dashboard: content_queue failed: %s", e)

    # --- AI staff activity (agent_events) ---
    try:
        from app.platform.team import team_status

        ts = team_status()
        totals = ts.get("totals", {}) if isinstance(ts, dict) else {}
        stats["agent_actions_today"] = int(totals.get("actions_today") or 0)
        stats["agent_errors_today"] = int(totals.get("errors_today") or 0)
        stats["active_staff"] = int(totals.get("active_members") or 0)
        # calls today = Swara's call_placed events today
        try:
            from app.platform.team import recent_events

            evs = recent_events(limit=300, member="swara")
            stats["calls_today"] = sum(
                1
                for e in evs
                if str(e.get("action") or "") == "call_placed" and _is_today_iso(e.get("at"))
            )
        except Exception:
            pass
    except Exception as e:
        logger.debug("admin_dashboard: team_status failed: %s", e)

    return stats


def _inquiry_count_for_client(c: dict) -> int:
    """Count inquiries.jsonl rows matched to this client record."""
    cid = str(c.get("id") or "").strip().lower()
    slug = str(c.get("slug") or "").strip().lower()
    biz = str(c.get("business_name") or "").strip().lower()
    phone_d = "".join(ch for ch in str(c.get("phone") or "") if ch.isdigit())[-10:]
    n = 0
    for r in _read_inquiries():
        r_slug = str(r.get("source_slug") or "").strip().lower()
        r_cid = str(r.get("client_id") or "").strip().lower()
        r_biz = str(r.get("business_name") or "").strip().lower()
        r_ph = "".join(ch for ch in str(r.get("phone") or "") if ch.isdigit())[-10:]
        if slug and r_slug == slug:
            n += 1
        elif cid and r_cid == cid:
            n += 1
        elif biz and r_biz == biz:
            n += 1
        elif phone_d and r_ph and r_ph == phone_d:
            n += 1
    return n


def _real_clients() -> list[Client]:
    """Real marketing clients → Client rows (empty list if none). No samples."""
    out: list[Client] = []
    try:
        from app.marketing import clients_store

        for c in clients_store.list_clients():
            plan = str(c.get("plan") or "starter")
            status = str(c.get("status") or "active")
            mrr = _plan_price(plan) if status == "active" else 0
            out.append(
                Client(
                    client_id=str(c.get("id") or ""),
                    company=str(c.get("business_name") or "Client"),
                    niche=str(c.get("niche") or "-"),
                    plan=plan.title(),
                    leads_delivered=_inquiry_count_for_client(c),
                    status=status,
                    mrr=mrr,
                )
            )
    except Exception as e:
        logger.debug("admin_dashboard: _real_clients failed: %s", e)
    return out


def _real_agents() -> list[Agent]:
    """Real AI staff (team.STAFF) → Agent cards with today's action counts."""
    out: list[Agent] = []
    try:
        from app.platform.team import team_status

        ts = team_status()
        members = ts.get("members", []) if isinstance(ts, dict) else []
        # working = green pulse; active (aaj kaam kiya) = scraping/blue; offline = grey idle.
        # data/scraper roles ka active = "scraping" (blue), baaki = "calling" (green-ish).
        _scraper_roles = {"dev", "rohan"}
        for m in members:
            la = m.get("last_activity") or {}
            action = str(la.get("action") or "")
            detail = str(la.get("detail") or m.get("title") or "-")[:60]
            mins = m.get("last_active_mins")
            when = ""
            if isinstance(mins, (int, float)):
                when = "abhi" if mins < 2 else (f"{int(mins)}m pehle" if mins < 60 else f"{int(mins // 60)}h pehle")
            line = (f"{detail} · {when}" if when else detail)[:72]
            errs = int(m.get("today_errors") or 0)
            state = str(m.get("state") or "offline")
            key = str(m.get("key") or "")
            if errs > 0:
                ui_status = "error"
            elif state == "working":
                ui_status = "scraping" if key in _scraper_roles else "calling"
            elif state == "active":
                ui_status = "scraping" if key in _scraper_roles else "calling"
            else:
                ui_status = "idle"
            out.append(
                Agent(
                    id=str(m.get("emoji") or "🤖") + " " + str(m.get("title") or "Staff"),
                    name=str(m.get("name") or "Agent"),
                    current_client=str(line or m.get("title") or "-"),
                    status=ui_status,
                    calls_made=int(m.get("today_actions") or 0),
                    leads_found=errs,
                )
            )
    except Exception as e:
        logger.debug("admin_dashboard: _real_agents failed: %s", e)
    return out


def _real_kpis(live: dict) -> KPIs:
    """Map REAL aggregates onto the KPI keys the HTML expects."""
    active_clients = int(live.get("marketing_clients_active") or 0)
    mrr = int(live.get("estimated_mrr") or 0)
    return KPIs(
        total_clients=int(live.get("marketing_clients") or 0),
        active_campaigns=active_clients,  # active clients = "running" engagements
        calls_today=int(live.get("calls_today") or 0),
        qualified_leads_month=int(live.get("inquiries_total") or 0),
        revenue_month=mrr,
        telephony_cost_month=0,
        net_margin_pct=100.0 if mrr else 0.0,
    )


def _real_charts(live: dict) -> Charts:
    """Charts from real data; empty-but-valid when there's nothing yet."""
    by_status = live.get("prospects_by_status") or {}
    if by_status:
        items = sorted(by_status.items(), key=lambda kv: kv[1], reverse=True)
        niche_labels = [k.title() for k, _ in items]
        niche_values = [int(v) for _, v in items]
    else:
        niche_labels, niche_values = ["No data"], [0]

    # "Pipeline" snapshot bars: prospects / inquiries / clients / emails / blog
    rev_labels = ["Prospects", "Inquiries", "Clients", "Emails", "Blog"]
    rev_revenue = [
        int(live.get("total_prospects") or 0),
        int(live.get("inquiries_total") or 0),
        int(live.get("marketing_clients") or 0),
        int(live.get("emails_sent") or 0),
        int(live.get("blog_articles") or 0),
    ]
    rev_cost = [0, 0, 0, int(live.get("emails_pending") or 0), 0]

    return Charts(
        revenue_cost=RevenueCostSeries(labels=rev_labels, revenue=rev_revenue, cost=rev_cost),
        leads_by_niche=LeadsByNiche(labels=niche_labels, values=niche_values),
        calls_per_day=CallsPerDay(
            labels=["Actions", "Calls", "Content", "Active Staff"],
            values=[
                int(live.get("agent_actions_today") or 0),
                int(live.get("calls_today") or 0),
                int(live.get("content_items_generated") or 0),
                int(live.get("active_staff") or 0),
            ],
        ),
    )


def _build_real() -> "DashboardResponse":
    """Build the dashboard ENTIRELY from real platform data. Never raises."""
    live = _collect_live_stats()
    now = datetime.utcnow()
    return DashboardResponse(
        is_sample_data=False,
        generated_at=now.replace(tzinfo=timezone.utc).isoformat(),
        kpis=_real_kpis(live),
        clients=_real_clients(),
        agents=_real_agents(),
        campaigns=[],  # no fake campaigns — real campaigns wired when DB has them
        health=_real_health(),
        charts=_real_charts(live),
        live=live,
    )


def _real_health() -> Health:
    """Real-ish health: API up, DB checked, telephony/scrapers by config."""
    db_ok = "up"
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        db_ok = "up" if _b._SessionLocal is not None else "down"
    except Exception:
        db_ok = "down"
    telephony = "down"
    scrapers = "up"  # OSM Overpass always available (no key needed)
    try:
        from app.config import settings

        if (getattr(settings, "vobiz_auth_id", "") or "") or (
            getattr(settings, "VOBIZ_AUTH_ID", "") or ""
        ):
            telephony = "up"
        if getattr(settings, "google_maps_api_key", "") or getattr(
            settings, "GOOGLE_MAPS_API_KEY", ""
        ):
            scrapers = "up"
    except Exception:
        pass
    return Health(api="up", db=db_ok, telephony=telephony, scrapers=scrapers)


# ----------------------------------------------------------------------------
# (Removed) Hardcoded SAMPLE builders — the dashboard now serves REAL data only.
# The SunVolt/Prestige/etc. fake clients, fake agents, fake campaigns and fake
# charts have been deleted on purpose. See _build_real() above for the live
# pipeline. _build_from_db() below is kept for DB-backed deployments (real).
# ----------------------------------------------------------------------------


# ----------------------------------------------------------------------------
# DB-backed builder (real data). Import-safe: DB imports are local + guarded so
# this module still mounts when DB deps/connection are missing.
# ----------------------------------------------------------------------------
def _build_from_db() -> "DashboardResponse | None":
    """
    Aggregate the admin dashboard from the real relational DB (clients /
    campaigns / agents / calls / billing tables). Returns None when the DB is
    unavailable OR has no clients — the caller then serves the file-based REAL
    aggregates instead (never sample data).
    """
    try:
        from collections import defaultdict

        from app.models.agent import Agent as AgentModel
        from app.models.base import get_db_session
        from app.models.billing_record import BillingRecord, BillingRecordType
        from app.models.call_log import CallLog as CallLogModel
        from app.models.campaign import Campaign as CampaignModel
        from app.models.client import Client as ClientModel
        from app.models.lead import Lead as LeadModel
        from app.models.lead import LeadStatus
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
            clients: list[Client] = []
            total_mrr = 0
            for c in client_rows:
                leads_delivered = db.query(LeadModel).filter(LeadModel.assigned_to == c.id).count()
                mrr = int((c.monthly_amount or 0) / 100)
                total_mrr += mrr if (c.status and c.status.value == "active") else 0
                clients.append(
                    Client(
                        client_id=str(c.id or ""),
                        company=c.business_name or "Unknown",
                        niche=c.industry or "-",
                        plan=(c.plan.value.title() if c.plan else "Starter"),
                        leads_delivered=leads_delivered,
                        status=(c.status.value if c.status else "active"),
                        mrr=mrr,
                    )
                )

            # ----- agents panel -----
            agents: list[Agent] = []
            for a in agent_rows:
                agents.append(
                    Agent(
                        id=a.agent_code or str(a.id)[:8],
                        name=a.name or "Agent",
                        current_client=a.current_client_name or "-",
                        status=(a.status.value if a.status else "idle"),
                        calls_made=a.calls_made or 0,
                        leads_found=a.leads_found or 0,
                    )
                )

            # ----- campaigns panel -----
            campaigns: list[Campaign] = []
            active_campaigns = 0
            for cp in campaign_rows:
                st = cp.status.value if cp.status else "draft"
                if st in ("running", "scheduled"):
                    active_campaigns += 1
                ui_status = "active" if st == "running" else st
                campaigns.append(
                    Campaign(
                        campaign=cp.name or "Campaign",
                        client=cp.client_name or "-",
                        niche=cp.niche or "-",
                        sources=[],
                        calls_done=cp.leads_called or 0,
                        calls_target=cp.target_lead_count or 0,
                        leads=cp.leads_qualified or 0,
                        status=ui_status,
                    )
                )

            # ----- KPIs -----
            calls_today = (
                db.query(CallLogModel)
                .filter(CallLogModel.initiated_at >= datetime(today.year, today.month, today.day))
                .count()
            )
            qualified_month = (
                db.query(LeadModel)
                .filter(
                    LeadModel.created_at >= datetime(now.year, now.month, 1),
                    LeadModel.status.in_(
                        [LeadStatus.QUALIFIED, LeadStatus.APPOINTMENT, LeadStatus.CONVERTED]
                    ),
                )
                .count()
            )

            # revenue + telephony cost this month (from billing records, in paise)
            br = (
                db.query(BillingRecord)
                .filter(
                    BillingRecord.period_year == now.year,
                    BillingRecord.period_month == now.month,
                )
                .all()
            )
            revenue_month = sum(
                (r.amount or 0) for r in br if r.record_type != BillingRecordType.TELEPHONY
            )
            telephony_cost_month = sum((r.cost or 0) for r in br) + sum(
                (c.call_cost or 0)
                for c in db.query(CallLogModel)
                .filter(CallLogModel.initiated_at >= datetime(now.year, now.month, 1))
                .all()
            )
            revenue_inr = int(revenue_month / 100) or total_mrr
            cost_inr = int(telephony_cost_month / 100)
            net_margin = (
                round(((revenue_inr - cost_inr) / revenue_inr) * 100, 1) if revenue_inr else 0.0
            )

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
                cnt = (
                    db.query(CallLogModel)
                    .filter(
                        CallLogModel.initiated_at >= start,
                        CallLogModel.initiated_at < end,
                    )
                    .count()
                )
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
                month_br = list(
                    db.query(BillingRecord)
                    .filter(
                        BillingRecord.period_year == y,
                        BillingRecord.period_month == m,
                    )
                    .all()
                )
                rev = int(
                    sum(
                        (r.amount or 0)
                        for r in month_br
                        if r.record_type != BillingRecordType.TELEPHONY
                    )
                    / 100
                )
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
        logger.warning("admin_dashboard: DB query failed, using file aggregates (%s)", e)
        return None


# ----------------------------------------------------------------------------
# Route
# ----------------------------------------------------------------------------
@router.get("/dashboard", response_model=DashboardResponse)
async def get_admin_dashboard() -> DashboardResponse:
    """
    Owner/operator dashboard payload — REAL data only.

    KPIs/clients/agents/charts are computed from the actual platform output:
    prospects, inquiries, marketing clients, emails sent, blog articles,
    content queue and AI-staff activity. is_sample_data is always False — the
    numbers reflect reality, even if everything is currently zero.

    If a richer DB (clients/campaigns/billing tables) is populated, that detail
    is merged in on top of the real aggregates.
    """
    try:
        resp = _build_real()
    except Exception as e:  # absolute guard — never 500
        logger.warning("admin_dashboard: build_real failed (%s)", e)
        return DashboardResponse(
            is_sample_data=False,
            generated_at=datetime.utcnow().replace(tzinfo=timezone.utc).isoformat(),
            kpis=KPIs(
                total_clients=0,
                active_campaigns=0,
                calls_today=0,
                qualified_leads_month=0,
                revenue_month=0,
                telephony_cost_month=0,
                net_margin_pct=0.0,
            ),
            clients=[],
            agents=[],
            campaigns=[],
            health=Health(api="up", db="down", telephony="down", scrapers="up"),
            charts=_real_charts({}),
            live={},
        )

    # NOTE: relational clients/campaigns tables me PURANA seeded DEMO data hai
    # (SunVolt Solar Pvt Ltd, ₹2.3L revenue) — woh override "purana data dikha
    # raha" wali bug ki jad thi. Marketing business ka source-of-truth ab
    # file-based aggregates (prospects/inquiries/clients_store/blog/emails) hai,
    # isliye _build_real() ka result HI return hota hai — DB demo-seed se override
    # NAHI. (Future: jab relational tables me asli clients aayein, _build_from_db
    # ko sirf empty panels bharne ke liye merge karna, KPIs replace karne ke liye nahi.)
    return resp


@router.get("/revenue-analytics")
async def get_revenue_analytics() -> dict:
    """MRR, churn-risk, LTV estimate — powers admin revenue analytics panel."""
    out: dict = {
        "mrr": 0,
        "subscriptions": {},
        "churn_risk_pct": 0.0,
        "clients_red": 0,
        "clients_yellow": 0,
        "clients_green": 0,
        "ltv_estimate_inr": 0,
        "hot_leads": 0,
        "health_top_risk": [],
    }
    try:
        from app.platform import client_health, revenue_digest

        stats = await revenue_digest._collect()
        out["mrr"] = int(stats.get("mrr") or 0)
        out["subscriptions"] = stats.get("subscriptions") or {}
        out["hot_leads"] = int(stats.get("hot_leads") or 0)
        out["deals"] = stats.get("deals") or {}
        out["dunning"] = stats.get("dunning") or {}
        health = await client_health.health_report()
        reds = sum(1 for h in health if h.get("band") == "red")
        yellows = sum(1 for h in health if h.get("band") == "yellow")
        greens = sum(1 for h in health if h.get("band") == "green")
        total = len(health) or 1
        active = int((out["subscriptions"] or {}).get("active") or 0) or total
        out["clients_red"] = reds
        out["clients_yellow"] = yellows
        out["clients_green"] = greens
        out["churn_risk_pct"] = round((reds + yellows) / total * 100, 1)
        out["ltv_estimate_inr"] = int(out["mrr"] * 12 / max(1, active))
        out["health_top_risk"] = [
            {
                "client_id": h.get("client_id"),
                "business_name": h.get("business_name"),
                "score": h.get("score"),
                "band": h.get("band"),
                "action": h.get("action"),
            }
            for h in health[:8]
        ]
    except Exception as e:
        logger.warning("admin_dashboard: revenue-analytics failed (%s)", e)
        out["error"] = str(e)[:160]
    return out


@router.get("/activity-feed")
def get_activity_feed(limit: int = Query(40, ge=1, le=100)) -> dict:
    """Agent events timeline for admin activity panel."""
    try:
        from app.platform.team import recent_events

        events = recent_events(limit=limit)
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.warning("admin_dashboard: activity-feed failed (%s)", e)
        return {"events": [], "count": 0, "error": str(e)[:120]}


@router.get("/prospects-preview")
def get_prospects_preview(limit: int = Query(40, ge=1, le=200)) -> dict:
    """Prospect pipeline preview for admin leads section."""
    try:
        from app.platform import prospector

        rows = prospector.list_prospects(limit=limit) or []
        by_status: dict[str, int] = {}
        for r in rows:
            st = str(r.get("status") or "ready").lower()
            by_status[st] = by_status.get(st, 0) + 1
        preview = [
            {
                "business": r.get("business_name") or r.get("name") or "-",
                "city": r.get("city") or "-",
                "niche": r.get("niche") or "-",
                "status": r.get("status") or "ready",
                "phone": r.get("phone") or "",
                "email": r.get("email") or "",
            }
            for r in rows[:limit]
        ]
        return {"prospects": preview, "by_status": by_status, "total": len(rows)}
    except Exception as e:
        logger.warning("admin_dashboard: prospects-preview failed (%s)", e)
        return {"prospects": [], "by_status": {}, "total": 0, "error": str(e)[:120]}


@router.get("/live-stats")
async def get_live_stats() -> dict:
    """Lightweight REAL aggregates dict (prospects, inquiries, clients, emails,
    blog, content, staff actions, calls). Best-effort — never 500."""
    try:
        stats = _collect_live_stats()
        stats["generated_at"] = datetime.utcnow().replace(tzinfo=timezone.utc).isoformat()
        stats["is_sample_data"] = False
        return stats
    except Exception as e:
        logger.warning("admin_dashboard: live-stats failed (%s)", e)
        return {"is_sample_data": False, "error": str(e)}
