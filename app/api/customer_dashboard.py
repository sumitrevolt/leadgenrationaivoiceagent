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

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer", tags=["Customer Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


# --------------------------------------------------------------------------- #
# Onboarding checklist — drives customer portal getting-started wizard         #
# --------------------------------------------------------------------------- #
from app.api.customer_dashboard_builders import (  # noqa: F401  (helpers extracted 2026-06-20)
    _build_from_db,
    _build_from_files,
    _build_onboarding_checklist,
    _calls_from_events,
    _client_record,
    _content_posts_count,
    _enrich_dashboard,
    _fmt_duration,
    _inquiries_for_client,
    _lead_score_from_inquiry,
    _mask_full_phone,
    _mask_full_phone_local,
    _parse_dt,
    _read_inquiries,
    _score_tier,
)

# --------------------------------------------------------------------------- #
# Pydantic response models (this is the exact JSON contract the HTML consumes) #
# --------------------------------------------------------------------------- #
from app.api.customer_dashboard_models import (  # noqa: F401  (models extracted 2026-06-20)
    CallRow,
    Campaign,
    ChartsData,
    CrmSyncLeadResult,
    CrmSyncResponse,
    CustomerTeamResponse,
    DashboardResponse,
    Kpis,
    LeadRow,
    OnboardingChecklist,
    OnboardingStep,
    SeriesPoint,
    TeamAgentCard,
)


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


@router.get("/office")
def get_customer_office(client_id: str = Depends(require_customer)):
    """🏢 Aapka Office — plain-Hinglish virtual-office view for the customer.

    Ek nazar me: (a) AI team ne aapke liye kya kiya (activity feed), (b) summary
    counts, aur (c) **customer ko khud kya manual karna hai** with automation-impact
    ("website do → behtar content", "X post approve → auto-publish"). Product-aware
    (marketing/voice/combo). client_id JWT se (require_customer) => IDOR-safe.
    Read-only, never-500, gated by CUSTOMER_OFFICE (default ON; '0' => disabled)."""
    if os.getenv("CUSTOMER_OFFICE", "1").strip().lower() in ("0", "false", "no", "off"):
        return {"ok": True, "enabled": False, "your_tasks": [], "activity": [], "summary": {}}
    from app.api.customer_dashboard_builders import _build_office

    return _build_office(client_id)


def _voice_team_response(
    client_id: str,
    client_rec: dict | None,
    total_leads: int,
    hot: int,
    has_profile: bool,
    niche: str,
) -> CustomerTeamResponse:
    """Voice-product customer's AI team — Swara/Ananya/Meera + Boss, with
    call-based activity derived ONLY from this client's own leads (IDOR-safe).

    ADR-009 two-product split: a voice-only dashboard must NOT show the marketing
    roster (Isha/Rohan/Dev). Mirrors get_customer_team's best-effort, never-500
    contract — every value comes from already-validated, client-scoped inputs.
    """
    try:
        from app.platform.team import STAFF
    except Exception:
        STAFF = {}

    def _meta(key: str, fallback_name: str, fallback_emoji: str) -> tuple[str, str]:
        info = STAFF.get(key) or {}
        return (str(info.get("name") or fallback_name), str(info.get("emoji") or fallback_emoji))

    agents: list[TeamAgentCard] = []

    # 📞 Swara — Telecaller (calls + qualifies this client's leads)
    sname, semoji = _meta("swara", "Swara", "📞")
    if hot > 0:
        s_status, s_label = "working", "Call pe"
        s_task = f"{hot} hot lead ko call karke qualify kiya — ready to buy. 🔥"
    elif total_leads > 0:
        s_status, s_label = "active", "Active"
        s_task = f"{total_leads} leads ko call karke qualify kiya."
    else:
        s_status, s_label = "active", "Taiyaar"
        s_task = "Naya lead aate hi turant call karne ko taiyaar hoon."
    agents.append(TeamAgentCard(
        key="swara", name=sname, emoji=semoji, title="Telecaller",
        duties="Aapke har lead ko call karke qualify karti hai",
        status=s_status, status_label=s_label, task=s_task,
        metric=f"{total_leads} call", accent="#4f46e5",
    ))

    # 📅 Ananya — Appointment Booker
    aname, aemoji = _meta("ananya", "Ananya", "📅")
    if hot > 0:
        a_status, a_label = "working", "Slot book kar rahi"
        a_task = f"{hot} interested customer ke liye appointment set kar rahi."
    else:
        a_status, a_label = "active", "Taiyaar"
        a_task = "Interested customers ke liye booking slots ready hain."
    agents.append(TeamAgentCard(
        key="ananya", name=aname, emoji=aemoji, title="Appointment Booker",
        duties="Qualified leads ke appointment/demo slot book karti hai",
        status=a_status, status_label=a_label, task=a_task,
        metric=(f"{hot} slot" if hot else "Slots ready"), accent="#0891b2",
    ))

    # 🎓 Meera — Call Quality Trainer (trust: calls sound human + fast)
    mname, memoji = _meta("meera", "Meera", "🎓")
    agents.append(TeamAgentCard(
        key="meera", name=mname, emoji=memoji, title="Call Quality",
        duties="Har call ki quality monitor karti hai",
        status="active", status_label="Monitor kar rahi",
        task="Har call ki quality check — saaf, natural aur fast awaaz.",
        metric="Quality ✓", accent="#7c3aed",
    ))

    # 🧑‍💼 Boss — Team Lead (coordinator summary)
    busy_count = sum(1 for a in agents if a.status == "working")
    bname, bemoji = _meta("manager", "Boss", "🧑‍💼")
    if busy_count > 0:
        b_status, b_label = "working", "Coordinate kar raha hai"
        b_task = f"{busy_count} agent abhi call/booking pe — main monitor kar raha hoon."
    else:
        b_status, b_label = "active", "Active"
        b_task = "Team ready hai — naya lead aate hi calling shuru."
    agents.append(TeamAgentCard(
        key="manager", name=bname, emoji=bemoji, title="Team Lead",
        duties="Poori voice team ko coordinate karta hai",
        status=b_status, status_label=b_label, task=b_task,
        metric=f"{len(agents) + 1} member", accent="#2563eb",
    ))

    total_today = total_leads
    is_sample = bool(not client_rec and total_today == 0)
    if total_today > 0:
        headline = f"Aaj aapki AI voice team ne {total_today} lead handle kiye"
    else:
        headline = "Aapki AI voice team active hai — lead aate hi call shuru"
    summary = (
        f"{busy_count} agent abhi kaam pe · {total_leads} lead · {hot} hot"
        if total_today
        else "Team din-raat aapki calling pe kaam karti hai."
    )
    return CustomerTeamResponse(
        client_id=client_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        is_sample_data=is_sample,
        headline=headline,
        summary=summary,
        busy_count=busy_count,
        total_today=total_today,
        agents=agents,
    )


@router.get("/team", response_model=CustomerTeamResponse)
def get_customer_team(client_id: str = Depends(require_customer)) -> CustomerTeamResponse:
    """Customer-facing **AI Marketing Team** — a virtual agentic office that shows
    each AI staff member and what they are doing FOR THIS client right now.

    Privacy: the roster (name/emoji/role) is read from app.platform.team.STAFF —
    the single source of truth — but every activity line / metric is derived ONLY
    from *this* client's own data (content queue + their inquiries). The
    agency-wide event feed is never exposed here, so one customer can never see
    another customer's work. client_id comes from the JWT (require_customer) =>
    IDOR-safe. Best-effort + never-500 (mirrors the dashboard builders).
    """
    client_rec = _client_record(client_id)

    # ---- content queue breakdown (drafts await your approval / published) ----
    total_posts = drafts = approved = posted = 0
    try:
        from app.marketing.auto_content import list_queue

        rid = str((client_rec or {}).get("id") or client_id or "").strip()
        if rid:
            for it in list_queue(rid, limit=500):
                total_posts += 1
                st = str(it.get("status") or "").lower()
                if st == "draft":
                    drafts += 1
                elif st == "approved":
                    approved += 1
                elif st == "posted":
                    posted += 1
    except Exception as e:  # pragma: no cover - defensive
        logger.debug("customer_team: content queue read failed (%s)", e)

    # ---- leads from this client's inquiries (Hot/Warm/Cold tiering) ----
    inquiries = _inquiries_for_client(client_id, client_rec)
    total_leads = len(inquiries)
    hot = 0
    for r in inquiries:
        try:
            if _lead_score_from_inquiry(r) == "Hot":
                hot += 1
        except Exception:
            pass

    niche = str((client_rec or {}).get("niche") or "").strip()
    has_profile = bool(
        client_rec
        and (client_rec.get("website") or niche or client_rec.get("business_name"))
    )

    # ---- per-agent state (client-scoped; names/emoji from STAFF) ----
    try:
        from app.platform.team import STAFF
    except Exception:
        STAFF = {}

    def _meta(key: str, fallback_name: str, fallback_emoji: str) -> tuple[str, str]:
        info = STAFF.get(key) or {}
        return (str(info.get("name") or fallback_name), str(info.get("emoji") or fallback_emoji))

    agents: list[TeamAgentCard] = []

    # ADR-009 product split: a voice-only client gets the VOICE team (call-based);
    # marketing/combo fall through to the marketing roster below (unchanged).
    _product = str((client_rec or {}).get("product") or "marketing").strip().lower()
    if _product == "voice":
        return _voice_team_response(client_id, client_rec, total_leads, hot, has_profile, niche)

    # 📣 Isha — Content Writer
    iname, iemoji = _meta("isha", "Isha", "📣")
    if drafts > 0:
        i_status, i_label = "working", "Likh rahi hai"
        i_task = f"{drafts} naye post taiyaar — aapke approve ka intezaar."
    elif total_posts > 0:
        i_status, i_label = "active", "Active"
        i_task = f"{posted or total_posts} post share/publish ke liye ready hain."
    else:
        i_status, i_label = "working", "Likh rahi hai"
        i_task = "Aaj ka social post draft kar rahi hoon."
    agents.append(TeamAgentCard(
        key="isha", name=iname, emoji=iemoji, title="Content Writer",
        duties="Roz aapke liye social posts likhti hai",
        status=i_status, status_label=i_label, task=i_task,
        metric=f"{total_posts} post", accent="#db2777",
    ))

    # 🎯 Rohan — Leads Manager
    rname, remoji = _meta("rohan", "Rohan", "🎯")
    if hot > 0:
        r_status, r_label = "working", "Follow-up pe"
        r_task = f"{hot} hot lead mile — abhi follow-up karna best hai."
    elif total_leads > 0:
        r_status, r_label = "active", "Active"
        r_task = f"{total_leads} leads handle kiye, scoring ho gayi."
    else:
        r_status, r_label = "active", "Taiyaar"
        r_task = "Naye leads ke liye targeting set kar rakhi hai."
    agents.append(TeamAgentCard(
        key="rohan", name=rname, emoji=remoji, title="Leads Manager",
        duties="Leads laata aur qualify karta hai",
        status=r_status, status_label=r_label, task=r_task,
        metric=f"{total_leads} lead", accent="#ea580c",
    ))

    # 📚 Dev — Business Researcher
    dname, demoji = _meta("dev", "Dev", "📚")
    if has_profile:
        d_status, d_label = "active", "Active"
        d_task = "Aapke business ki profile AI ko sikha ke ready rakhi hai."
        d_metric = (niche.title() if niche else "Profile ready")
    else:
        d_status, d_label = "working", "Setup kar raha hai"
        d_task = "Aapka business samajh raha hoon — profile complete karo."
        d_metric = "Setup pending"
    agents.append(TeamAgentCard(
        key="dev", name=dname, emoji=demoji, title="Business Researcher",
        duties="Aapka business AI ko samjhata hai",
        status=d_status, status_label=d_label, task=d_task,
        metric=d_metric, accent="#7c3aed",
    ))

    # 🧑‍💼 Boss — Team Lead (coordinator; summary card)
    busy_count = sum(1 for a in agents if a.status == "working")
    bname, bemoji = _meta("manager", "Boss", "🧑‍💼")
    if busy_count > 0:
        b_status, b_label = "working", "Coordinate kar raha hai"
        b_task = f"{busy_count} agent abhi kaam pe — main monitor kar raha hoon."
    else:
        b_status, b_label = "active", "Active"
        b_task = "Team ready hai — naya kaam aate hi assign kar dunga."
    agents.append(TeamAgentCard(
        key="manager", name=bname, emoji=bemoji, title="Team Lead",
        duties="Poori team ko coordinate karta hai",
        status=b_status, status_label=b_label, task=b_task,
        metric=f"{len(agents) + 1} member", accent="#2563eb",
    ))

    total_today = total_posts + total_leads
    is_sample = bool(not client_rec and total_today == 0)
    if total_today > 0:
        headline = f"Aaj aapki AI team ne {total_today} cheezein handle ki"
    else:
        headline = "Aapki AI team active hai — kaam aate hi yahan dikhega"
    summary = (
        f"{busy_count} agent abhi kaam pe · {total_posts} post · {total_leads} lead"
        if total_today
        else "Team din-raat aapke marketing pe kaam karti hai."
    )

    return CustomerTeamResponse(
        client_id=client_id,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        is_sample_data=is_sample,
        headline=headline,
        summary=summary,
        busy_count=busy_count,
        total_today=total_today,
        agents=agents,
    )


# --------------------------------------------------------------------------- #
# Phase-1 self-serve marketing tools (council 2026-06-26) — customer-scoped,   #
# IDOR-safe versions of the admin "done-for-you" generators. Each reuses the   #
# same underlying generator module the admin console uses; client_id comes     #
# from the JWT (require_customer) so a customer only ever touches its own data. #
# --------------------------------------------------------------------------- #
def _safe_cid(cid: str) -> str:
    """Filesystem-safe client id (no path traversal)."""
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(cid or "demo"))[:64]


_GBP_DIR = os.path.join("data", "gbp_audits")


@router.get("/gbp/questions")
def customer_gbp_questions(client_id: str = Depends(require_customer)) -> dict:
    """GBP self-audit ke 16 Hinglish sawal + is client ka last saved score.

    Customer khud apna Google Business Profile audit kar sakta hai — scoring
    PURE LOGIC hai (koi LLM cost nahi). Last result per-client file me save hota
    hai taaki card pe "pichla score" dikhe."""
    out: dict = {"questions": [], "total": 0, "last": None}
    try:
        from app.marketing import gbp_audit

        out["questions"] = gbp_audit.AUDIT_QUESTIONS
        out["total"] = len(gbp_audit.AUDIT_QUESTIONS)
    except Exception as e:
        logger.debug("customer_gbp_questions: module load failed (%s)", e)
    try:
        fp = os.path.join(_GBP_DIR, _safe_cid(client_id) + ".json")
        if os.path.exists(fp):
            with open(fp, encoding="utf-8") as fh:
                out["last"] = json.load(fh)
    except Exception as e:
        logger.debug("customer_gbp_questions: last read failed (%s)", e)
    return out


@router.post("/gbp/score")
def customer_gbp_score(
    answers: dict = Body(..., embed=True, description="{question_id: option_index}"),
    client_id: str = Depends(require_customer),
) -> dict:
    """Audit answers => 0-100 score + grade + top-5 Hinglish fixes (persist latest)."""
    try:
        from app.marketing import gbp_audit

        result = gbp_audit.score_audit(answers if isinstance(answers, dict) else {})
    except Exception as e:
        logger.error("customer_gbp_score failed: %s", e)
        raise HTTPException(status_code=500, detail="GBP scoring abhi available nahi.")
    result["at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        os.makedirs(_GBP_DIR, exist_ok=True)
        with open(os.path.join(_GBP_DIR, _safe_cid(client_id) + ".json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False)
    except Exception as e:
        logger.debug("customer_gbp_score: persist failed (%s)", e)
    return result


@router.get("/creatives")
def customer_creatives(client_id: str = Depends(require_customer)) -> dict:
    """Creatives & Festival gallery — upcoming Indian festivals (static calendar)
    + is client ke ready content posts/posters (content queue se). Read-only,
    near-zero cost. Festival captions/posters generation admin/AI karta hai;
    yahan customer ready creatives dekh+download kar sakta hai."""
    client_rec = _client_record(client_id)
    festivals_list: list = []
    try:
        from app.marketing import festivals

        festivals_list = festivals.upcoming(45)
    except Exception as e:
        logger.debug("customer_creatives: festivals failed (%s)", e)

    posts: list[dict] = []
    try:
        from app.marketing.auto_content import list_queue

        rid = str((client_rec or {}).get("id") or client_id or "").strip()
        if rid:
            for it in list_queue(rid, limit=24):
                posts.append({
                    "title": str(it.get("title") or it.get("occasion") or "Post")[:140],
                    "caption": str(it.get("caption") or it.get("text") or "")[:2000],
                    "hashtags": list(it.get("hashtags") or [])[:12],
                    "status": str(it.get("status") or "draft"),
                    "created_at": str(it.get("created_at") or ""),
                    "svg": str(it.get("svg") or ""),
                    "has_svg": bool(it.get("svg")),
                })
    except Exception as e:
        logger.debug("customer_creatives: content queue failed (%s)", e)

    return {
        "client_id": client_id,
        "festivals": festivals_list,
        "posts": posts,
        "poster_count": sum(1 for p in posts if p["has_svg"]),
        "is_sample_data": bool(not client_rec and not posts),
    }


@router.get("/autopilot")
def customer_autopilot_drafts(client_id: str = Depends(require_customer)) -> dict:
    """"Aapki AI team ne ye taiyaar kiya" — the hands-free autopilot drafts
    (owner-brief / feedback survey / stale-inquiry nudge / evergreen post) the AI
    prepared for THIS business. Draft-only: 1-click send stays the customer's
    choice (no bulk auto-send — ban-safe). client_id from the JWT (require_customer)
    => customer sees ONLY its own drafts. GAP-1 fix (2026-07-06): these drafts had
    no customer-facing route before. Empty until the autopilot flags are armed and
    drafts accumulate (see docs — SIGNUP_AUTO_ONBOARD / OWNER_BRIEF_DAILY / etc.)."""
    slug = ""
    try:
        rec = _client_record(client_id) or {}
        slug = str(rec.get("slug") or "").strip()
    except Exception:
        pass
    drafts: list = []
    try:
        from app.platform import customer_autopilot

        drafts = customer_autopilot.drafts_for_client(client_id, slug=slug)
    except Exception as e:
        logger.debug("customer_autopilot_drafts failed (%s)", e)
    return {"ok": True, "client_id": client_id, "count": len(drafts), "drafts": drafts}


# --------------------------------------------------------------------------- #
# Product-2 (Voice) self-serve calling — GAP-1 fix (council decision 2026-07-06)
# ---------------------------------------------------------------------------
# The flat-fee "AI calls your leads" value was admin-only (campaigns.py require_admin)
# — a paying voice customer had no way to trigger, or even SEE, calling. These two
# routes close it SAFELY: every call is routed through call_manager.queue_call() — the
# SINGLE compliance chokepoint (DND fail-closed + 9am-7pm TRAI window + DLT/140 +
# prepaid-minutes + voice-quota + lead-score) — so this route CANNOT bypass any gate.
# client_id is forced from the JWT (IDOR-safe). POST is gated CUSTOMER_VOICE_SELFSERVE
# (default OFF => 503) and NEVER auto-schedules — one explicit customer action per
# batch. Enable only after a live outbound test call (voice = phone-final-verify).


def _voice_selfserve_enabled() -> bool:
    import os as _os

    return (_os.getenv("CUSTOMER_VOICE_SELFSERVE", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


_VOICE_CALL_MGR = None


def _voice_call_manager():
    """Lazy CallManager (enqueues to the shared Redis queue the prod call-processor
    drains). Cached module-level. Import-safe."""
    global _VOICE_CALL_MGR
    if _VOICE_CALL_MGR is None:
        from app.telephony.call_manager import CallManager

        _VOICE_CALL_MGR = CallManager()
    return _VOICE_CALL_MGR


@router.get("/voice/queue-status")
def customer_voice_queue_status(client_id: str = Depends(require_customer)) -> dict:
    """Read-only voice activity for THIS client (no calls placed) — so the customer
    can SEE calling even before self-serve is enabled. client_id from the JWT."""
    total, called, today_calls = 0, 0, 0
    try:
        from datetime import datetime, timezone

        from app.models.base import get_db_session
        from app.models.call_log import CallLog
        from app.models.lead import Lead

        with get_db_session() as db:
            total = (
                db.query(Lead)
                .filter(Lead.assigned_to == client_id, Lead.phone.isnot(None))
                .count()
            )
            called = len(
                {
                    r[0]
                    for r in db.query(CallLog.lead_id)
                    .filter(CallLog.client_id == client_id)
                    .all()
                    if r[0]
                }
            )
            _today = datetime.now(timezone.utc).date()
            today_calls = sum(
                1
                for c in db.query(CallLog.initiated_at)
                .filter(CallLog.client_id == client_id)
                .all()
                if c[0] and c[0].date() == _today
            )
    except Exception as e:
        logger.debug("voice queue-status: %s", e)
    return {
        "ok": True,
        "leads_with_phone": total,
        "already_called": called,
        "remaining_to_call": max(0, total - called),
        "calls_today": today_calls,
        "self_serve_enabled": _voice_selfserve_enabled(),
    }


@router.post(
    "/voice/call-queue",
    dependencies=[Depends(rate_limit("voice_call_queue", 6, 60))],
)
async def customer_voice_call_queue(
    limit: int = Body(20, embed=True),
    client_id: str = Depends(require_customer),
) -> dict:
    """Self-serve: queue THIS client's un-called leads for the AI voice agent.

    Every call goes through `queue_call` (the sole compliance chokepoint), so a
    non-compliant number (DND / outside 9am-7pm / no DLT / out of minutes/quota) is
    simply NOT queued — this route bypasses nothing. NO REPEAT-DIAL: skips leads that
    have a CallLog row AND an in-flight Redis set (`voice_inflight:{cid}`, TTL) so the
    same person isn't re-queued in the queue→dial→log window (2026-07-06 sec-audit
    fix); plus a per-client daily cap (`VOICE_SELFSERVE_DAILY_CAP`, default 200) and a
    per-IP rate limit. client_id forced from JWT (IDOR-safe). Gated
    CUSTOMER_VOICE_SELFSERVE (default OFF => 503). Enable only after a live test call."""
    if not _voice_selfserve_enabled():
        raise HTTPException(
            status_code=503,
            detail="Voice self-serve calling abhi enable nahi hai — admin se activate karwayein.",
        )
    lim = max(1, min(int(limit or 20), 50))
    rec = _client_record(client_id) or {}
    client_name = str(rec.get("business_name") or "Aapka business")
    niche_default = str(rec.get("niche") or "general")

    try:
        from app.models.base import get_db_session
        from app.models.call_log import CallLog
        from app.models.lead import Lead

        with get_db_session() as db:
            called_ids = {
                r[0]
                for r in db.query(CallLog.lead_id).filter(CallLog.client_id == client_id).all()
                if r[0]
            }
            # Materialize plain column rows INSIDE the session — building CallRequests
            # after the `with` closes on ORM objects would raise DetachedInstanceError.
            leads = [
                {
                    "id": r[0],
                    "phone": r[1],
                    "niche": r[2],
                    "company_name": r[3],
                    "city": r[4],
                    "lead_score": r[5],
                    "is_hot_lead": r[6],
                }
                for r in db.query(
                    Lead.id,
                    Lead.phone,
                    Lead.niche,
                    Lead.company_name,
                    Lead.city,
                    Lead.lead_score,
                    Lead.is_hot_lead,
                )
                .filter(Lead.assigned_to == client_id)
                .order_by(Lead.lead_score.desc())
                .limit(500)
                .all()
            ]
    except Exception as e:
        logger.warning("voice call-queue: lead fetch failed (%s)", e)
        raise HTTPException(status_code=503, detail="Leads abhi load nahi ho paaye — baad me.")

    from app.telephony.call_manager import CallRequest

    # In-flight dedup + per-client daily cap (2026-07-06 sec-audit fix): queue_call
    # only Redis-enqueues; the CallLog row lands POST-call, so `called_ids` alone
    # leaves a TOCTOU window where the SAME lead (a real person's phone) could be
    # re-queued/re-dialled before its call logs. A short-TTL Redis SET of in-flight
    # lead_ids + a per-client daily counter close it. Best-effort / fail-open — the
    # per-call compliance gate in queue_call stays the hard control regardless.
    _redis = None
    _inflight: set[str] = set()
    _ikey = f"voice_inflight:{client_id}"
    _dcap = int(os.getenv("VOICE_SELFSERVE_DAILY_CAP", "200") or "200")
    _dused = 0
    _dkey = ""
    try:
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from app.cache import get_redis_client

        _redis = await get_redis_client()
        _dkey = f"voice_dcap:{client_id}:{_dt.now(_tz.utc):%Y%m%d}"
        _inflight = {
            (m.decode() if isinstance(m, bytes) else str(m))
            for m in (await _redis.smembers(_ikey) or set())
        }
        _dv = await _redis.get(_dkey)
        _dused = int(_dv) if _dv else 0
    except Exception as e:
        logger.debug("voice call-queue: redis dedup unavailable, degrading (%s)", e)
        _redis = None

    mgr = _voice_call_manager()
    queued, blocked, no_phone, capped = 0, 0, 0, False
    reasons: dict[str, int] = {}
    for lead in leads:
        if queued >= lim:
            break
        if _dcap and (_dused + queued) >= _dcap:
            capped = True  # per-client daily cap reached
            break
        if lead["id"] in called_ids or lead["id"] in _inflight:
            continue
        phone = str(lead["phone"] or "").strip()
        if not phone:
            no_phone += 1
            continue
        try:
            req = CallRequest(
                lead_id=str(lead["id"]),
                phone_number=phone,
                campaign_id="",
                niche=(lead["niche"] or niche_default),
                client_name=client_name,
                client_service=niche_default,
                script_name="",
                lead_data={
                    "company_name": lead["company_name"],
                    "city": lead["city"],
                    "score": lead["lead_score"],
                },
                client_id=client_id,  # IDOR + metering/quota scoped to the caller
                call_type="promotional",  # queue_call applies DND + DLT + 9-7 window
                priority=3 if lead["is_hot_lead"] else 5,
            )
            res = await mgr.queue_call(req)
            # queue_call returns "<reason>_<uuid>" when a gate refused, else a plain
            # call-id (queued). Match the KNOWN reason prefixes (robust to the suffix).
            _block_key = next(
                (
                    k
                    for k in (
                        "compliance_blocked",
                        "compliance_error",
                        "out_of_minutes",
                        "out_of_lead_quota",
                        "below_min_score",
                    )
                    if isinstance(res, str) and res.startswith(k)
                ),
                None,
            )
            if _block_key:
                blocked += 1
                reasons[_block_key] = reasons.get(_block_key, 0) + 1
            else:
                queued += 1
                if _redis is not None:  # mark in-flight (no re-dial) + count vs daily cap
                    try:
                        await _redis.sadd(_ikey, lead["id"])
                        await _redis.expire(
                            _ikey, int(os.getenv("VOICE_INFLIGHT_TTL_S", "1800") or 1800)
                        )
                        if _dkey:
                            await _redis.incr(_dkey)
                            await _redis.expire(_dkey, 90000)
                    except Exception:
                        pass
        except Exception as e:
            logger.debug("voice call-queue: queue_call skip (%s)", e)
            blocked += 1
    return {
        "ok": True,
        "queued": queued,
        "blocked": blocked,
        "skipped_no_phone": no_phone,
        "daily_cap_reached": capped,
        "reasons": reasons,
        "note": "Sirf compliant leads (DND-clear, 9am-7pm window, DLT) queue hue — AI team inhe call karegi.",
    }


# tiny per-process cache so the monthly report (1 LLM call) isn't rebuilt on
# every poll/refresh; keyed by client_id+month, short TTL.
_REPORT_CACHE: dict[str, tuple[float, dict]] = {}


@router.get("/report")
async def customer_monthly_report(
    month: str = Query("", description="YYYY-MM; blank => current month"),
    client_id: str = Depends(require_customer),
) -> dict:
    """Customer-facing monthly marketing report (read-only deliverable) — kya
    kaam hua is mahine. build_report team events se banta hai + 1 free-LLM
    Hinglish summary; result short-TTL cache hota hai (cost guard)."""
    import time

    client_rec = _client_record(client_id)
    client_name = str((client_rec or {}).get("business_name") or client_id or "")
    ck = f"{_safe_cid(client_id)}:{month or 'cur'}"
    hit = _REPORT_CACHE.get(ck)
    if hit and (time.time() - hit[0]) < 900:  # 15-min cache
        return hit[1]
    try:
        from app.marketing import monthly_report

        result = await monthly_report.build_report(
            client_name=client_name, month=month or None, client_id=client_id
        )
    except Exception as e:
        logger.error("customer_monthly_report failed: %s", e)
        raise HTTPException(status_code=500, detail="Report abhi available nahi.")
    _REPORT_CACHE[ck] = (time.time(), result)
    return result


@router.get("/speed-to-lead")
def customer_speed_to_lead(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    client_id: str = Depends(require_customer),
) -> dict:
    """Client-scoped speed-to-lead SLA metric for dashboard badge."""
    from app.platform import speed_to_lead

    client_rec = _client_record(client_id)
    return speed_to_lead.summary_for_client(client_id, client_rec, days)


def _client_owns_lead(client_id: str, lead_id: str) -> tuple[bool, bool]:
    """Verify lead_id belongs to client_id, mirroring how the dashboard scopes
    leads (inquiries.jsonl + DB Lead.assigned_to).

    Returns (owned, infra_error):
      owned=True       -> confirmed this client's lead (inquiry OR DB row).
      owned=False      -> not confirmed to belong to this client.
      infra_error=True -> a lookup backend errored, so ownership is UNKNOWN
                          (caller must fail-CLOSED: refuse the write).
    Never raises. Cheap: file path is an in-memory scan of this client's
    inquiries; DB path is a single indexed lookup and only runs when the
    inquiry path did not already confirm ownership."""
    lid = str(lead_id or "").strip()
    if not lid:
        return False, False
    infra_error = False
    # 1) File/inquiry path — same scoping as _build_from_files. Never raises.
    try:
        rec = _client_record(client_id)
        for r in _inquiries_for_client(client_id, rec):
            if str(r.get("id") or "") == lid:
                return True, False
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("lead ownership: inquiry lookup failed (%s)", e)
        infra_error = True
    # 2) DB path — same scoping as _build_from_db (Lead.assigned_to == client_id).
    try:
        from app.models.base import get_db_session
        from app.models.lead import Lead

        with get_db_session() as db:
            row = (
                db.query(Lead.id)
                .filter(Lead.assigned_to == client_id, Lead.id == lid)
                .first()
            )
            if row is not None:
                return True, False
    except Exception as e:
        logger.warning("lead ownership: DB lookup failed (%s)", e)
        infra_error = True
    return False, infra_error


@router.patch("/leads/{lead_id}")
async def patch_lead_status(
    lead_id: str,
    status: str = Body(..., embed=True),
    client_id: str = Depends(require_customer),
) -> dict:
    """B4: customer updates a lead's status inline. require_customer resolves
    client_id from the JWT, so a client can only ever record an override under
    its own id (IDOR-safe).

    Cross-tenant eviction guard (2026-07): overrides are stored append-only and
    read collapses to one record per lead_id (latest wins). Without an ownership
    check, client B could PATCH client A's lead_id and silently EVICT A's own
    override (A's Kanban edit would revert). So we verify the lead belongs to the
    authenticated client BEFORE recording — non-owned lead_id => 404 (generic, no
    existence leak, matching customer_flows). Ownership-lookup infra error =>
    fail-CLOSED (503, write refused), never a blind unverified write."""
    from app.platform.lead_overrides import ALLOWED_STATUSES, set_status

    if status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=422, detail=f"status must be one of {sorted(ALLOWED_STATUSES)}"
        )
    owned, infra_error = _client_owns_lead(client_id, lead_id)
    if not owned:
        if infra_error:
            # Could not verify ownership (backend error) — refuse rather than risk
            # evicting another tenant's override.
            raise HTTPException(status_code=503, detail="lead ownership check unavailable")
        raise HTTPException(status_code=404, detail="not found")
    ok = set_status(lead_id, client_id, status)
    return {"ok": ok, "lead_id": lead_id, "status": status}


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


class RoutingMemberIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    phone: str = Field(..., min_length=10, max_length=15)


class RoutingConfigIn(BaseModel):
    members: list[RoutingMemberIn] = Field(default_factory=list, max_length=10)


class ApprovalDecideIn(BaseModel):
    action: str = Field(default="approve", pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=300)


class KbInfoIn(BaseModel):
    text: str = Field(..., min_length=5, max_length=4000)


def _kb_namespace(cid: str) -> str:
    """client:<id> namespace (same helper onboarding uses)."""
    try:
        from app.platform.agent_provisioner import _client_namespace

        return _client_namespace(cid)
    except Exception:
        return f"client:{cid}"


@router.post("/kb-info")
def customer_kb_info(
    body: KbInfoIn,
    client_id: str = Depends(require_customer),
):
    """Portal self-serve business-info entry.

    Aaj tak customer sirf onboarding wale EK WhatsApp reply se apni business-info
    de sakta tha — agar woh miss ho gaya to AI agent ko client ke business ka pata
    hi nahi chalta. Yeh route customer ko portal se hi text daal ke apni KB
    (namespace client:<id>) seed karne deta hai + awaiting_kb_interview clear.

    client_id JWT (require_customer) se aata hai => customer sirf apni hi KB likhta
    (IDOR-safe). Never-500."""
    text = (body.text or "").strip()[:4000]
    if len(text) < 5:
        raise HTTPException(status_code=400, detail="Kuch business-info text bhejo")
    ns = _kb_namespace(client_id)
    chunks = 0
    try:
        from app.voice_agent.knowledge_base import get_knowledge_base

        chunks = get_knowledge_base().add_documents(
            [text], source="portal:kb_info", namespace=ns
        )
    except Exception as e:
        logger.debug("customer kb-info add_documents failed: %s", e)
        raise HTTPException(status_code=503, detail="KB abhi available nahi, thodi der me try karo")
    # Interview pending flag clear — portal se info aa gayi (best-effort).
    try:
        from app.marketing import clients_store

        clients_store.update_client(client_id, awaiting_kb_interview=False)
    except Exception as e:
        logger.debug("customer kb-info flag clear failed: %s", e)
    return {"ok": True, "chunks_added": int(chunks or 0), "namespace": ns}


@router.get("/branded-feed")
async def customer_branded_feed(client_id: str = Depends(require_customer)):
    """AdBanao-style aaj ke 3 branded posts (logo+naam frame) — customer scoped."""
    try:
        from app.marketing import brand_frames
        from app.marketing.clients_store import get_client

        c = get_client(client_id) or {}
        slug = str(c.get("slug") or client_id or "").strip()
        return await brand_frames.daily_feed(slug)
    except Exception as e:
        logger.debug("customer branded-feed failed: %s", e)
        return {"ok": False, "error": "feed load nahi hua", "posts": []}


@router.get("/approvals/pending")
def customer_pending_approvals(client_id: str = Depends(require_customer)):
    """Posts jo client approval ka wait kar rahe hain."""
    try:
        from app.marketing import content_approval

        rows = content_approval.pending(client_id)
        safe = [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "content": r.get("content") or {},
            }
            for r in rows
        ]
        return {"ok": True, "count": len(safe), "approvals": safe}
    except Exception as e:
        logger.debug("customer approvals pending failed: %s", e)
        return {"ok": False, "count": 0, "approvals": []}


@router.post("/approvals/{approval_id}/decide")
def customer_decide_approval(
    approval_id: str,
    body: ApprovalDecideIn,
    client_id: str = Depends(require_customer),
):
    """Portal se approve/reject — token link ki zaroorat nahi."""
    from app.marketing import content_approval

    return content_approval.decide_for_client(client_id, approval_id, body.action, body.note or "")


@router.get("/routing")
def customer_routing_get(client_id: str = Depends(require_customer)):
    """Client ki sales team round-robin config."""
    from app.platform import lead_distribution as ld

    cfg = ld.get_config(client_id)
    recent = ld.assignments(client_id, limit=15)
    return {"ok": True, "config": cfg, "recent_assignments": recent}


@router.post("/routing")
def customer_routing_set(
    body: RoutingConfigIn,
    client_id: str = Depends(require_customer),
):
    """Team members set karo — naye leads round-robin me bantenge."""
    from app.platform import lead_distribution as ld

    members = [{"name": m.name, "phone": m.phone} for m in body.members]
    return ld.set_config(client_id, members)


@router.get("/health")
def customer_dashboard_health() -> dict:
    """Lightweight liveness probe for the customer dashboard API."""
    return {"status": "ok", "service": "customer-dashboard"}
