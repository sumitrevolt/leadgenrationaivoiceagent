"""
Analytics API
Endpoints for analytics and reporting.

Data source is DB-primary with a graceful fallback: each endpoint reads real
rows from the relational models (`CallLog` / `Lead`) via `_db_calls()` /
`_db_leads()`, flattened to plain dicts. When the DB is unavailable or returns
no rows, the aggregation transparently falls back to the in-memory
`analytics_store` that the pipeline / call manager can push events into. The
aggregation logic is identical on either source, so the route signatures stay
stable regardless of which backs a given response.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
# Whole router is admin-only: every endpoint aggregates platform-wide Lead/CallLog
# data (conversion rates, lead scores, agent/campaign performance) — must not be
# reachable anonymously.
router = APIRouter(prefix="/analytics", tags=["Analytics"], dependencies=[Depends(require_admin)])


class DashboardStats(BaseModel):
    """Dashboard statistics"""

    total_leads: int
    total_calls: int
    total_appointments: int
    total_callbacks: int
    conversion_rate: float
    avg_lead_score: float
    calls_today: int
    hot_leads_today: int


class CallMetrics(BaseModel):
    """Call metrics"""

    total_calls: int
    connected_calls: int
    connection_rate: float
    avg_duration: float
    total_talk_time: int
    appointments_booked: int
    callbacks_scheduled: int


class LeadMetrics(BaseModel):
    """Lead metrics"""

    total_leads: int
    new_leads: int
    contacted_leads: int
    qualified_leads: int
    converted_leads: int
    rejected_leads: int
    avg_score: float


class TimeSeriesPoint(BaseModel):
    """Time series data point"""

    date: str
    value: float


# =============================================================================
# In-memory analytics store
# =============================================================================
# Fallback source when the DB is unavailable or empty. Each record is a plain
# dict shaped exactly like the flattened ORM rows from `_db_calls`/`_db_leads`,
# so the aggregation logic works unchanged on either source.
class AnalyticsStore:
    """
    Lightweight in-memory event store for analytics aggregation.

    Other modules (pipeline, call manager) can call `record_lead` /
    `record_call` to push events. The API endpoints prefer real DB rows and
    fall back to these lists when the DB is unavailable or returns nothing.
    """

    def __init__(self):
        self.leads: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self.appointments: list[dict[str, Any]] = []

    def record_lead(self, lead: dict[str, Any]) -> None:
        lead.setdefault("created_at", datetime.now())
        self.leads.append(lead)

    def record_call(self, call: dict[str, Any]) -> None:
        call.setdefault("completed_at", datetime.now())
        self.calls.append(call)

    def record_appointment(self, appt: dict[str, Any]) -> None:
        appt.setdefault("created_at", datetime.now())
        self.appointments.append(appt)

    @staticmethod
    def _as_dt(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None


# Shared singleton; importable as `from app.api.analytics import analytics_store`.
analytics_store = AnalyticsStore()

# Backwards-compatible alias (older code referenced `analytics_data`).
analytics_data = {
    "calls": analytics_store.calls,
    "leads": analytics_store.leads,
    "appointments": analytics_store.appointments,
}


# =============================================================================
# Helpers
# =============================================================================
def _in_range(
    records: list[dict[str, Any]],
    date_field: str,
    start: datetime | None,
    end: datetime | None,
) -> list[dict[str, Any]]:
    """Filter records whose datetime field falls within [start, end]."""
    out = []
    for r in records:
        dt = analytics_store._as_dt(r.get(date_field))
        if dt is None:
            continue
        if start and dt < start:
            continue
        if end and dt > end:
            continue
        out.append(r)
    return out


def _avg(values: list[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


# =============================================================================
# DB-backed source (real data) with graceful fallback to the in-memory store.
# All DB imports are local + guarded so this module stays import-safe even when
# DB drivers/connection are missing. Each ORM row is flattened to a plain dict
# shaped exactly like the in-memory store records, so the aggregation logic
# below works unchanged on either source.
# =============================================================================
def _db_calls() -> list[dict[str, Any]] | None:
    """Return CallLog rows as store-compatible dicts, or None if unavailable/empty."""
    try:
        from app.models.base import get_db_session
        from app.models.call_log import CallLog
    except Exception as e:
        logger.debug("analytics: CallLog model unavailable (%s)", e)
        return None
    try:
        with get_db_session() as db:
            rows = db.query(CallLog).all()
            if not rows:
                return None
            out: list[dict[str, Any]] = []
            for c in rows:
                out.append(
                    {
                        "completed_at": c.ended_at or c.initiated_at or c.created_at,
                        "duration_seconds": c.duration_seconds or 0,
                        "status": c.status
                        or ("completed" if (c.duration_seconds or 0) > 0 else "failed"),
                        "outcome": c.outcome.value if c.outcome else None,
                        "lead_score": c.lead_score or 0,
                        "campaign_id": c.campaign_id,
                        "agent_id": getattr(c, "agent_id", None) or "unassigned",
                        "revenue": 0,
                    }
                )
            return out
    except Exception as e:
        logger.debug("analytics: CallLog query failed (%s)", e)
        return None


def _db_leads() -> list[dict[str, Any]] | None:
    """Return Lead rows as store-compatible dicts, or None if unavailable/empty."""
    try:
        from app.models.base import get_db_session
        from app.models.lead import Lead
    except Exception as e:
        logger.debug("analytics: Lead model unavailable (%s)", e)
        return None
    try:
        with get_db_session() as db:
            rows = db.query(Lead).all()
            if not rows:
                return None
            out: list[dict[str, Any]] = []
            for l in rows:
                out.append(
                    {
                        "created_at": l.created_at,
                        "status": l.status.value if l.status else "new",
                        "lead_score": l.lead_score or 0,
                        "lead_tier": "hot" if l.is_hot_lead else None,
                        "niche": l.niche,
                        "city": l.city,
                        "source": l.source.value if l.source else "manual",
                        "outcome": None,
                    }
                )
            return out
    except Exception as e:
        logger.debug("analytics: Lead query failed (%s)", e)
        return None


def _calls_source() -> list[dict[str, Any]]:
    """Prefer real DB calls; fall back to the in-memory store."""
    db = _db_calls()
    return db if db is not None else analytics_store.calls


def _leads_source() -> list[dict[str, Any]]:
    """Prefer real DB leads; fall back to the in-memory store."""
    db = _db_leads()
    return db if db is not None else analytics_store.leads


# =============================================================================
# Endpoints
# =============================================================================
@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats():
    """
    Get main dashboard statistics.
    Data source: Lead + CallLog DB rows with in-memory store fallback.
    """
    leads = _leads_source()
    calls = _calls_source()

    today = datetime.now().date()
    calls_today = [
        c
        for c in calls
        if (dt := analytics_store._as_dt(c.get("completed_at"))) and dt.date() == today
    ]
    hot_leads_today = [c for c in calls_today if c.get("lead_score", 0) >= 70]

    appointments = [c for c in calls if c.get("outcome") == "appointment"]
    callbacks = [c for c in calls if c.get("outcome") == "callback"]

    conversion_rate = round(len(appointments) / len(calls), 4) if calls else 0.0
    avg_lead_score = _avg([c.get("lead_score", 0) for c in calls])

    return DashboardStats(
        total_leads=len(leads),
        total_calls=len(calls),
        total_appointments=len(appointments),
        total_callbacks=len(callbacks),
        conversion_rate=conversion_rate,
        avg_lead_score=avg_lead_score,
        calls_today=len(calls_today),
        hot_leads_today=len(hot_leads_today),
    )


@router.get("/calls", response_model=CallMetrics)
async def get_call_metrics(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    campaign_id: str | None = None,
):
    """
    Get call metrics for a period.
    Data source: CallLog DB rows (via _db_calls) with in-memory store fallback.
    """
    calls = _in_range(_calls_source(), "completed_at", start_date, end_date)
    if campaign_id:
        calls = [c for c in calls if c.get("campaign_id") == campaign_id]

    connected = [
        c
        for c in calls
        if c.get("status") in ("completed", "connected") or c.get("duration_seconds", 0) > 0
    ]
    durations = [c.get("duration_seconds", 0) for c in connected]
    appointments = [c for c in calls if c.get("outcome") == "appointment"]
    callbacks = [c for c in calls if c.get("outcome") == "callback"]

    return CallMetrics(
        total_calls=len(calls),
        connected_calls=len(connected),
        connection_rate=round(len(connected) / len(calls), 4) if calls else 0.0,
        avg_duration=_avg(durations),
        total_talk_time=sum(durations),
        appointments_booked=len(appointments),
        callbacks_scheduled=len(callbacks),
    )


@router.get("/leads", response_model=LeadMetrics)
async def get_lead_metrics(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    niche: str | None = None,
):
    """
    Get lead metrics for a period.
    Data source: Lead DB rows (via _db_leads) with in-memory store fallback.
    """
    leads = _in_range(_leads_source(), "created_at", start_date, end_date)
    if niche:
        leads = [l for l in leads if l.get("niche") == niche]

    def _status(l):
        return (l.get("call_status") or l.get("status") or "new").lower()

    contacted = [l for l in leads if _status(l) in ("called", "contacted", "completed")]
    qualified = [
        l for l in leads if l.get("lead_score", 0) >= 50 or l.get("lead_tier") in ("hot", "warm")
    ]
    converted = [l for l in leads if l.get("outcome") == "appointment"]
    rejected = [l for l in leads if l.get("outcome") in ("not_interested", "opt_out")]
    new_leads = [l for l in leads if _status(l) in ("new", "pending")]

    return LeadMetrics(
        total_leads=len(leads),
        new_leads=len(new_leads),
        contacted_leads=len(contacted),
        qualified_leads=len(qualified),
        converted_leads=len(converted),
        rejected_leads=len(rejected),
        avg_score=_avg([l.get("lead_score", 0) for l in leads]),
    )


@router.get("/calls/by-day", response_model=list[TimeSeriesPoint])
async def get_calls_by_day(days: int = Query(30, ge=1, le=365)):
    """
    Get calls per day for the last N days.
    Data source: CallLog DB rows (via _db_calls) with in-memory store fallback.
    """
    today = datetime.now().date()
    counts: dict[str, int] = defaultdict(int)
    for c in _calls_source():
        dt = analytics_store._as_dt(c.get("completed_at"))
        if dt:
            counts[dt.date().isoformat()] += 1

    result = []
    for i in range(days):
        date = today - timedelta(days=i)
        result.append(TimeSeriesPoint(date=date.isoformat(), value=counts.get(date.isoformat(), 0)))

    return list(reversed(result))


@router.get("/leads/by-source")
async def get_leads_by_source():
    """
    Get lead distribution by source.
    Data source: Lead DB rows (via _db_leads) with in-memory store fallback.
    """
    counts: dict[str, int] = defaultdict(int)
    for l in _leads_source():
        src = l.get("source", "manual") or "manual"
        counts[src] += 1
    # Ensure the common keys always appear.
    base = {"google_maps": 0, "indiamart": 0, "justdial": 0, "linkedin": 0, "manual": 0}
    base.update(counts)
    return base


@router.get("/leads/by-city")
async def get_leads_by_city(limit: int = Query(10, ge=1, le=50)):
    """
    Get top cities by lead count.
    Data source: Lead DB rows (via _db_leads) with in-memory store fallback.
    """
    counts: dict[str, int] = defaultdict(int)
    for l in _leads_source():
        city = l.get("city")
        if city:
            counts[city] += 1
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    return [{"city": c, "count": n} for c, n in ranked[:limit]]


@router.get("/calls/by-outcome")
async def get_calls_by_outcome():
    """
    Get call distribution by outcome.
    Data source: CallLog DB rows (via _db_calls) with in-memory store fallback.
    """
    base = {
        "appointment": 0,
        "callback": 0,
        "not_interested": 0,
        "no_answer": 0,
        "busy": 0,
        "wrong_number": 0,
    }
    for c in _calls_source():
        outcome = c.get("outcome", "no_answer") or "no_answer"
        base[outcome] = base.get(outcome, 0) + 1
    return base


@router.get("/performance/agents")
async def get_agent_performance():
    """
    Get performance metrics per agent.
    Data source: CallLog DB rows (agent_id) with in-memory store fallback.
    """
    by_agent: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "appointments": 0, "qualified": 0, "talk_time": 0}
    )
    for c in _calls_source():
        agent = c.get("agent_id", "unassigned")
        rec = by_agent[agent]
        rec["calls"] += 1
        rec["talk_time"] += c.get("duration_seconds", 0)
        if c.get("outcome") == "appointment":
            rec["appointments"] += 1
        if c.get("lead_score", 0) >= 50:
            rec["qualified"] += 1
    return [{"agent_id": a, **stats} for a, stats in by_agent.items()]


@router.get("/performance/campaigns")
async def get_campaign_performance():
    """
    Get performance metrics per campaign.
    Data source: CallLog DB rows (campaign_id) with in-memory store fallback.
    """
    by_campaign: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "qualified": 0, "appointments": 0}
    )
    for c in _calls_source():
        cid = c.get("campaign_id", "unknown")
        rec = by_campaign[cid]
        rec["calls"] += 1
        if c.get("lead_score", 0) >= 50:
            rec["qualified"] += 1
        if c.get("outcome") == "appointment":
            rec["appointments"] += 1
    out = []
    for cid, stats in by_campaign.items():
        stats["qualification_rate"] = (
            round(stats["qualified"] / stats["calls"], 4) if stats["calls"] else 0.0
        )
        out.append({"campaign_id": cid, **stats})
    return out


@router.get("/hourly-distribution")
async def get_hourly_distribution():
    """
    Get call success rate by hour of day.
    Data source: CallLog DB rows (via _db_calls) with in-memory store fallback.
    """
    buckets: dict[int, dict[str, int]] = {
        hour: {"calls": 0, "connected": 0} for hour in range(9, 19)
    }
    for c in _calls_source():
        dt = analytics_store._as_dt(c.get("completed_at"))
        if not dt or dt.hour not in buckets:
            continue
        buckets[dt.hour]["calls"] += 1
        if c.get("duration_seconds", 0) > 0:
            buckets[dt.hour]["connected"] += 1

    result = {}
    for hour, b in buckets.items():
        rate = round(b["connected"] / b["calls"], 4) if b["calls"] else 0.0
        result[f"{hour:02d}:00"] = {
            "calls": b["calls"],
            "connected": b["connected"],
            "connection_rate": rate,
        }
    return result


@router.get("/reports/daily")
async def get_daily_report(date: str | None = None):
    """
    Get daily summary report.
    Data source: Lead + CallLog DB rows with in-memory store fallback.
    """
    if date:
        report_date = datetime.fromisoformat(date).date()
    else:
        report_date = datetime.now().date()

    day_calls = [
        c
        for c in _calls_source()
        if (dt := analytics_store._as_dt(c.get("completed_at"))) and dt.date() == report_date
    ]
    day_leads = [
        l
        for l in _leads_source()
        if (dt := analytics_store._as_dt(l.get("created_at"))) and dt.date() == report_date
    ]

    connected = [c for c in day_calls if c.get("duration_seconds", 0) > 0]
    appointments = [c for c in day_calls if c.get("outcome") == "appointment"]
    callbacks = [c for c in day_calls if c.get("outcome") == "callback"]
    hot = [c for c in day_calls if c.get("lead_score", 0) >= 70]

    return {
        "date": report_date.isoformat(),
        "summary": {
            "leads_scraped": len(day_leads),
            "calls_made": len(day_calls),
            "calls_connected": len(connected),
            "appointments_booked": len(appointments),
            "callbacks_scheduled": len(callbacks),
            "hot_leads": len(hot),
        },
        "by_campaign": await get_campaign_performance(),
        "by_niche": _group_count(day_leads, "niche"),
        "top_performers": await get_agent_performance(),
    }


@router.get("/reports/weekly")
async def get_weekly_report():
    """
    Get weekly summary report.
    Data source: Lead + CallLog DB rows with in-memory store fallback.
    """
    today = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    start_dt = datetime.combine(week_start, datetime.min.time())
    end_dt = datetime.combine(week_end, datetime.max.time())

    week_calls = _in_range(_calls_source(), "completed_at", start_dt, end_dt)
    week_leads = _in_range(_leads_source(), "created_at", start_dt, end_dt)
    appointments = [c for c in week_calls if c.get("outcome") == "appointment"]

    # Daily breakdown
    daily: dict[str, int] = defaultdict(int)
    for c in week_calls:
        dt = analytics_store._as_dt(c.get("completed_at"))
        if dt:
            daily[dt.date().isoformat()] += 1
    daily_breakdown = [{"date": d, "calls": n} for d, n in sorted(daily.items())]

    best_day = max(daily_breakdown, key=lambda x: x["calls"], default=None)
    worst_day = min(daily_breakdown, key=lambda x: x["calls"], default=None)
    avg_daily = round(len(week_calls) / 7, 2)

    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "summary": {
            "total_leads": len(week_leads),
            "total_calls": len(week_calls),
            "total_appointments": len(appointments),
            "avg_daily_calls": avg_daily,
            "best_day": best_day["date"] if best_day else None,
            "worst_day": worst_day["date"] if worst_day else None,
        },
        "daily_breakdown": daily_breakdown,
        "trends": _week_trends(week_calls, week_leads, week_start),
    }


@router.get("/reports/monthly")
async def get_monthly_report(
    year: int = Query(default=None), month: int = Query(default=None, ge=1, le=12)
):
    """
    Get monthly summary report.
    Data source: Lead + CallLog DB rows with in-memory store fallback.
    """
    today = datetime.now()
    if year is None:
        year = today.year
    if month is None:
        month = today.month

    month_calls = [
        c
        for c in _calls_source()
        if (dt := analytics_store._as_dt(c.get("completed_at")))
        and dt.year == year
        and dt.month == month
    ]
    month_leads = [
        l
        for l in _leads_source()
        if (dt := analytics_store._as_dt(l.get("created_at")))
        and dt.year == year
        and dt.month == month
    ]
    appointments = [c for c in month_calls if c.get("outcome") == "appointment"]
    revenue = sum(c.get("revenue", 0) for c in month_calls)

    conversion_rate = round(len(appointments) / len(month_calls), 4) if month_calls else 0.0

    return {
        "year": year,
        "month": month,
        "summary": {
            "total_leads": len(month_leads),
            "total_calls": len(month_calls),
            "total_appointments": len(appointments),
            "revenue_generated": revenue,
            "avg_lead_score": _avg([c.get("lead_score", 0) for c in month_calls]),
            "conversion_rate": conversion_rate,
        },
        "weekly_breakdown": _iso_week_buckets(month_calls, year, month),
        "by_campaign": await get_campaign_performance(),
        "by_niche": _group_count(month_leads, "niche"),
        "comparison": _month_comparison(len(month_calls), len(month_leads), year, month),
    }


def _iso_week_buckets(calls: list[dict[str, Any]], year: int, month: int) -> list[dict[str, Any]]:
    """Month ke calls ko ISO-week buckets me group karo."""
    from collections import defaultdict as _dd

    buckets: dict[str, int] = _dd(int)
    for c in calls:
        dt = analytics_store._as_dt(c.get("completed_at"))
        if dt:
            iso = dt.isocalendar()
            key = f"{iso[0]}-W{iso[1]:02d}"
            buckets[key] += 1
    return [{"week": k, "calls": v} for k, v in sorted(buckets.items())]


def _month_comparison(calls_this: int, leads_this: int, year: int, month: int) -> dict[str, Any]:
    """Is month vs previous month % change."""
    import calendar as _cal

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    _, last_day = _cal.monthrange(prev_year, prev_month)
    prev_start = datetime(prev_year, prev_month, 1)
    prev_end = datetime(prev_year, prev_month, last_day, 23, 59, 59)
    prev_calls = _in_range(_calls_source(), "completed_at", prev_start, prev_end)
    prev_leads = _in_range(_leads_source(), "created_at", prev_start, prev_end)

    def _pct(cur: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round((cur - prev) / prev * 100, 1)

    return {
        "vs_last_month_calls": _pct(calls_this, len(prev_calls)),
        "vs_last_month_leads": _pct(leads_this, len(prev_leads)),
        "prev_month_calls": len(prev_calls),
        "prev_month_leads": len(prev_leads),
    }


def _week_trends(week_calls: list, week_leads: list, week_start) -> dict[str, Any]:
    """Is week vs previous week % change."""
    prev_start = datetime.combine(week_start - timedelta(days=7), datetime.min.time())
    prev_end = datetime.combine(week_start - timedelta(days=1), datetime.max.time())
    prev_calls = _in_range(_calls_source(), "completed_at", prev_start, prev_end)
    prev_leads = _in_range(_leads_source(), "created_at", prev_start, prev_end)

    def _pct(cur: int, prev: int) -> float:
        if prev == 0:
            return 100.0 if cur > 0 else 0.0
        return round((cur - prev) / prev * 100, 1)

    prev_appts = [c for c in prev_calls if c.get("outcome") == "appointment"]
    cur_appts = [c for c in week_calls if c.get("outcome") == "appointment"]
    return {
        "leads_trend": _pct(len(week_leads), len(prev_leads)),
        "calls_trend": _pct(len(week_calls), len(prev_calls)),
        "conversion_trend": _pct(len(cur_appts), len(prev_appts)),
        "vs_prev_week_calls": len(prev_calls),
        "vs_prev_week_leads": len(prev_leads),
    }


def _group_count(records: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    """Group records by a field and return [{field: value, count: n}]."""
    counts: dict[str, int] = defaultdict(int)
    for r in records:
        val = r.get(field)
        if val:
            counts[val] += 1
    return [
        {field: k, "count": v}
        for k, v in sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    ]
