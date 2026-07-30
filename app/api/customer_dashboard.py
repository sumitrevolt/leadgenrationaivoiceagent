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
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.api.customer_auth import require_customer
from app.api.ratelimit import rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/customer", tags=["Customer Dashboard"])

# Inquiries store (jsonl-first; same path public_site.py writes to).
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")

# Media-root authority for the customer serve path lives in
# app/marketing/video_media_paths.py (resolve_video_media_file). It is shared
# with approval and publishing so the same artifact cannot be servable but
# unapprovable, or vice versa. There is deliberately no local roots constant.


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
    ApprovalBanner,
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
    agents.append(
        TeamAgentCard(
            key="swara",
            name=sname,
            emoji=semoji,
            title="Telecaller",
            duties="Aapke har lead ko call karke qualify karti hai",
            status=s_status,
            status_label=s_label,
            task=s_task,
            metric=f"{total_leads} call",
            accent="#4f46e5",
        )
    )

    # 📅 Ananya — Appointment Booker
    aname, aemoji = _meta("ananya", "Ananya", "📅")
    if hot > 0:
        a_status, a_label = "working", "Slot book kar rahi"
        a_task = f"{hot} interested customer ke liye appointment set kar rahi."
    else:
        a_status, a_label = "active", "Taiyaar"
        a_task = "Interested customers ke liye booking slots ready hain."
    agents.append(
        TeamAgentCard(
            key="ananya",
            name=aname,
            emoji=aemoji,
            title="Appointment Booker",
            duties="Qualified leads ke appointment/demo slot book karti hai",
            status=a_status,
            status_label=a_label,
            task=a_task,
            metric=(f"{hot} slot" if hot else "Slots ready"),
            accent="#0891b2",
        )
    )

    # 🎓 Meera — Call Quality Trainer (trust: calls sound human + fast)
    mname, memoji = _meta("meera", "Meera", "🎓")
    agents.append(
        TeamAgentCard(
            key="meera",
            name=mname,
            emoji=memoji,
            title="Call Quality",
            duties="Har call ki quality monitor karti hai",
            status="active",
            status_label="Monitor kar rahi",
            task="Har call ki quality check — saaf, natural aur fast awaaz.",
            metric="Quality ✓",
            accent="#7c3aed",
        )
    )

    # 🧑‍💼 Boss — Team Lead (coordinator summary)
    busy_count = sum(1 for a in agents if a.status == "working")
    bname, bemoji = _meta("manager", "Boss", "🧑‍💼")
    if busy_count > 0:
        b_status, b_label = "working", "Coordinate kar raha hai"
        b_task = f"{busy_count} agent abhi call/booking pe — main monitor kar raha hoon."
    else:
        b_status, b_label = "active", "Active"
        b_task = "Team ready hai — naya lead aate hi calling shuru."
    agents.append(
        TeamAgentCard(
            key="manager",
            name=bname,
            emoji=bemoji,
            title="Team Lead",
            duties="Poori voice team ko coordinate karta hai",
            status=b_status,
            status_label=b_label,
            task=b_task,
            metric=f"{len(agents) + 1} member",
            accent="#2563eb",
        )
    )

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
        client_rec and (client_rec.get("website") or niche or client_rec.get("business_name"))
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
    agents.append(
        TeamAgentCard(
            key="isha",
            name=iname,
            emoji=iemoji,
            title="Content Writer",
            duties="Roz aapke liye social posts likhti hai",
            status=i_status,
            status_label=i_label,
            task=i_task,
            metric=f"{total_posts} post",
            accent="#db2777",
        )
    )

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
    agents.append(
        TeamAgentCard(
            key="rohan",
            name=rname,
            emoji=remoji,
            title="Leads Manager",
            duties="Leads laata aur qualify karta hai",
            status=r_status,
            status_label=r_label,
            task=r_task,
            metric=f"{total_leads} lead",
            accent="#ea580c",
        )
    )

    # 📚 Dev — Business Researcher
    dname, demoji = _meta("dev", "Dev", "📚")
    if has_profile:
        d_status, d_label = "active", "Active"
        d_task = "Aapke business ki profile AI ko sikha ke ready rakhi hai."
        d_metric = niche.title() if niche else "Profile ready"
    else:
        d_status, d_label = "working", "Setup kar raha hai"
        d_task = "Aapka business samajh raha hoon — profile complete karo."
        d_metric = "Setup pending"
    agents.append(
        TeamAgentCard(
            key="dev",
            name=dname,
            emoji=demoji,
            title="Business Researcher",
            duties="Aapka business AI ko samjhata hai",
            status=d_status,
            status_label=d_label,
            task=d_task,
            metric=d_metric,
            accent="#7c3aed",
        )
    )

    # 🧑‍💼 Boss — Team Lead (coordinator; summary card)
    busy_count = sum(1 for a in agents if a.status == "working")
    bname, bemoji = _meta("manager", "Boss", "🧑‍💼")
    if busy_count > 0:
        b_status, b_label = "working", "Coordinate kar raha hai"
        b_task = f"{busy_count} agent abhi kaam pe — main monitor kar raha hoon."
    else:
        b_status, b_label = "active", "Active"
        b_task = "Team ready hai — naya kaam aate hi assign kar dunga."
    agents.append(
        TeamAgentCard(
            key="manager",
            name=bname,
            emoji=bemoji,
            title="Team Lead",
            duties="Poori team ko coordinate karta hai",
            status=b_status,
            status_label=b_label,
            task=b_task,
            metric=f"{len(agents) + 1} member",
            accent="#2563eb",
        )
    )

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
    out: dict = {"questions": [], "total": 0, "last": None, "suggested": None}
    try:
        from app.marketing import gbp_audit

        out["questions"] = gbp_audit.AUDIT_QUESTIONS
        out["total"] = len(gbp_audit.AUDIT_QUESTIONS)
        try:
            out["suggested"] = gbp_audit.heuristic_suggest(_client_record(client_id) or {})
        except Exception:
            out["suggested"] = None
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
        with open(
            os.path.join(_GBP_DIR, _safe_cid(client_id) + ".json"), "w", encoding="utf-8"
        ) as fh:
            json.dump(result, fh, ensure_ascii=False)
    except Exception as e:
        logger.debug("customer_gbp_score: persist failed (%s)", e)
    return result


@router.post(
    "/gbp/council-suggest",
    dependencies=[Depends(rate_limit("gbp_council", 4, 60))],
)
async def customer_gbp_council_suggest(client_id: str = Depends(require_customer)) -> dict:
    """Council + heuristic answer suggestions. Score SAVE nahi hota — boss confirm kare."""
    from app.platform import boss_council

    client = _client_record(client_id) or {"id": client_id}
    out = await boss_council.decide_gbp_suggest(client)
    out["persisted"] = False
    return out


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
                posts.append(
                    {
                        "title": str(it.get("title") or it.get("occasion") or "Post")[:140],
                        "caption": str(it.get("caption") or it.get("text") or "")[:2000],
                        "hashtags": list(it.get("hashtags") or [])[:12],
                        "status": str(it.get("status") or "draft"),
                        "created_at": str(it.get("created_at") or ""),
                        "svg": str(it.get("svg") or ""),
                        "has_svg": bool(it.get("svg")),
                    }
                )
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
    """ "Aapki AI team ne ye taiyaar kiya" — the hands-free autopilot drafts
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
                db.query(Lead).filter(Lead.assigned_to == client_id, Lead.phone.isnot(None)).count()
            )
            called = len(
                {
                    r[0]
                    for r in db.query(CallLog.lead_id).filter(CallLog.client_id == client_id).all()
                    if r[0]
                }
            )
            _today = datetime.now(timezone.utc).date()
            today_calls = sum(
                1
                for c in db.query(CallLog.initiated_at).filter(CallLog.client_id == client_id).all()
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
    # PLAN/PRODUCT GATE (2026-07-07 audit fix): AI voice calling is a separate
    # standalone product (₹4,999-19,999/mo) — a Marketing-only ("starter")
    # customer must not get free AI calls just because this flag+DLT happen to
    # both be armed one day. queue_call()'s minute/lead-quota checks fail-OPEN
    # for non-metered plans (no cap = not blocked), so this route-level check
    # is the only gate for product entitlement specifically.
    from app.marketing import clients_store as _clients_store

    if _clients_store.resolve_product(rec) not in ("voice", "combo"):
        raise HTTPException(
            status_code=403,
            detail="AI Voice Calling aapke plan me included nahi hai — Voice ya Combo product chahiye.",
        )
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
            row = db.query(Lead.id).filter(Lead.assigned_to == client_id, Lead.id == lid).first()
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
    action: str = Field(default="approve", pattern="^(approve|reject|escalate)$")
    note: str = Field(default="", max_length=300)


class ApprovalCouncilIn(BaseModel):
    apply: bool = True


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

        chunks = get_knowledge_base().add_documents([text], source="portal:kb_info", namespace=ns)
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


class ProfileUpdateIn(BaseModel):
    """Setup Wizard write path. Deliberately NO plan/status/trial/niche field —
    those stay admin-only via clients_store.update_client's own whitelist AND
    this schema's absence of them (defense in depth, not either/or)."""

    business_name: str = Field("", max_length=120)
    city: str = Field("", max_length=80)
    phone: str = Field("", max_length=40)
    instagram: str = Field("", max_length=200)
    facebook: str = Field("", max_length=200)
    gbp: str = Field("", max_length=300)
    tagline: str = Field("", max_length=160)
    primary_color: str = Field("", max_length=9)
    accent_color: str = Field("", max_length=9)
    logo_text: str = Field("", max_length=40)
    tone: str = Field("", max_length=40)
    services: str = Field("", max_length=500)
    target_area: str = Field("", max_length=200)
    whatsapp_phone: str = Field("", max_length=40)
    approval_preference: str = Field("", max_length=40)


@router.get("/profile")
def customer_get_profile(client_id: str = Depends(require_customer)) -> dict:
    """Setup Wizard read path — current business profile/socials/brand-tone so
    the portal form can pre-fill instead of showing blank fields. Never raises."""
    try:
        from app.marketing import brand_kit, clients_store

        # Profile/brand marketing id pe keyed — billing/login alias canonicalize.
        mcid = clients_store.canonical_client_id(client_id)
        c = clients_store.resolve_client(client_id) or {}
        brand = c.get("brand") or {}
        socials = c.get("socials") or {}
        tone = ""
        try:
            tone = str((brand_kit.get_brand(mcid) or {}).get("tone") or "")
        except Exception:
            pass
        return {
            "ok": True,
            "business_name": c.get("business_name", ""),
            "city": c.get("city", ""),
            "phone": c.get("phone", ""),
            "instagram": socials.get("instagram", ""),
            "facebook": socials.get("facebook", ""),
            "gbp": socials.get("gbp", ""),
            "tagline": brand.get("tagline", ""),
            "primary_color": brand.get("primary", ""),
            "accent_color": brand.get("accent", ""),
            "logo_text": brand.get("logo_text", ""),
            "tone": tone,
            "services": c.get("services", ""),
            "target_area": c.get("target_area", ""),
            "whatsapp_phone": c.get("whatsapp_phone", ""),
            "approval_preference": c.get("approval_preference", "manual"),
        }
    except Exception as e:
        logger.debug("customer get profile failed: %s", e)
        return {"ok": False, "error": "profile load nahi hua"}


@router.post("/profile")
def customer_update_profile(
    body: ProfileUpdateIn, client_id: str = Depends(require_customer)
) -> dict:
    """Setup Wizard write path — business profile/social/WhatsApp/brand-tone,
    Customer Delivery OS mission's 4 wizard dimensions. IDOR-safe (client_id
    from JWT); only the fields named on ProfileUpdateIn can ever be set — no
    plan/status/trial/niche path exists here even though clients_store.update_client
    itself would allow them. Never-500."""
    try:
        from app.marketing import brand_kit, clients_store

        # Marketing record + brand_kit marketing id pe keyed. Billing/login alias
        # (Jiya `d79d690f61b3`) se update_client(alias) pehle 404 deta tha — profile
        # wizard save hi nahi hota tha. Canonicalize once for every write below.
        mcid = clients_store.canonical_client_id(client_id)

        fields: dict = {}
        if body.business_name.strip():
            fields["business_name"] = body.business_name.strip()
        if body.city.strip():
            fields["city"] = body.city.strip()
        if body.phone.strip():
            fields["phone"] = body.phone.strip()
        if body.services.strip():
            fields["services"] = body.services.strip()
        if body.target_area.strip():
            fields["target_area"] = body.target_area.strip()
        if body.whatsapp_phone.strip():
            fields["whatsapp_phone"] = body.whatsapp_phone.strip()
        if body.approval_preference.strip():
            fields["approval_preference"] = body.approval_preference.strip()

        socials = {
            k: v.strip()
            for k, v in {
                "instagram": body.instagram,
                "facebook": body.facebook,
                "gbp": body.gbp,
            }.items()
            if v.strip()
        }
        if socials:
            fields["socials"] = socials
        brand = {
            k: v.strip()
            for k, v in {
                "tagline": body.tagline,
                "primary": body.primary_color,
                "accent": body.accent_color,
                "logo_text": body.logo_text,
            }.items()
            if v.strip()
        }
        if brand:
            fields["brand"] = brand

        updated = (
            clients_store.update_client(mcid, **fields)
            if fields
            else clients_store.resolve_client(client_id)
        )
        if updated is None:
            raise HTTPException(status_code=404, detail="Client not found")

        # tone isn't part of update_client's brand->brand_kit mirror (it only
        # carries tagline/colors/logo_text) — read-modify-write so we add tone
        # without clobbering whatever the mirror above just wrote.
        if body.tone.strip():
            try:
                current = brand_kit.get_brand(mcid) or {}
                brand_kit.save_brand(mcid, {**current, "tone": body.tone.strip()})
            except Exception as e:
                logger.debug("customer profile tone save skip: %s", e)

        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("customer profile update failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}


@router.post("/campaigns/generate-first-week")
def customer_generate_first_week(client_id: str = Depends(require_customer)) -> dict:
    """Setup Wizard ka "pehla 7-din ka plan banao" button — seed ko WORKER me
    enqueue karta hai (seed = multi LLM-call, web process me kabhi heavy job
    nahi, CLAUDE.md). Idempotent: upcoming non-skipped items pehle se hon to
    enqueue hi nahi hota (seed re-run content_approval me duplicates banata —
    guard auto_content.upcoming_item_count single-source, worker task bhi wahi
    re-check karta hai). IDOR-safe: client_id JWT se. Never-500."""
    try:
        from app.marketing import auto_content, clients_store

        # Seed/content pipeline marketing id pe keyed — billing/login alias canonicalize.
        mcid = clients_store.canonical_client_id(client_id)
        if not clients_store.resolve_client(client_id):
            raise HTTPException(status_code=404, detail="Client not found")
        upcoming = auto_content.upcoming_item_count(mcid)
        if upcoming > 0:
            return {
                "ok": True,
                "queued": False,
                "already": True,
                "upcoming_items": upcoming,
                "message": "Aapke aane wale dino ka plan pehle se taiyaar hai — 📅 Calendar me dekhein.",
            }
        try:
            from app.tasks.staff_jobs import seed_first_week

            seed_first_week.delay(mcid)
        except Exception as qe:
            logger.warning("first-week seed enqueue failed for %s: %s", client_id, qe)
            return {
                "ok": False,
                "queued": False,
                "error": "Abhi generate nahi ho paya — thodi der baad try karein.",
            }
        return {
            "ok": True,
            "queued": True,
            "already": False,
            "message": "🎉 AI aapka 7-din ka plan bana rahi hai — 1-2 minute me 📅 Calendar aur approvals me dikhega.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.debug("customer generate-first-week failed: %s", e)
        return {"ok": False, "error": "Campaign generate nahi hua — baad me try karein."}


# --------------------------------------------------------------------------- #
# Social Networking Setup Wizard — "apne social channels connect/configure karo" #
# for the AI to prepare + (when admin-enabled) publish content. This is the     #
# missing piece over the profile wizard (ADR-030), which only captured link     #
# URLs + brand tone. Here the customer picks WHICH channels + cadence +          #
# approval-mode. Auto-posting stays gated/INERT: saving config never posts —     #
# real publish still needs SOCIAL_ENGINE master gate + a configured provider.    #
# IDOR-safe: client_id from JWT only, never from the body.                       #
# --------------------------------------------------------------------------- #
class SocialConfigIn(BaseModel):
    """Social wizard write path. Handles (links) + posting preferences only —
    NO plan/status/niche path (defense-in-depth, same as ProfileUpdateIn)."""

    instagram: str = Field("", max_length=200)
    facebook: str = Field("", max_length=200)
    gbp: str = Field("", max_length=300)
    youtube: str = Field("", max_length=200)
    linkedin: str = Field("", max_length=200)
    twitter: str = Field("", max_length=200)
    channels: list[str] = Field(default_factory=list, max_length=12)
    cadence: str = Field("", max_length=16)
    approval_mode: str = Field("", max_length=16)
    postiz_integrations: list[str] = Field(default_factory=list, max_length=20)
    # Loop-social-19 (2026-07-11): Phase-3 Step-1 + Step-4 fields — all optional
    # so existing callers/UI stay backward-compat.
    timezone: str = Field("", max_length=64)
    website: str = Field("", max_length=300)
    brand_tone: str = Field("", max_length=80)
    target_audience: str = Field("", max_length=500)
    products_or_services: str = Field("", max_length=500)
    preferred_language: str = Field("", max_length=16)
    posting_days: list[str] = Field(default_factory=list, max_length=7)
    posting_times: list[str] = Field(default_factory=list, max_length=8)
    content_categories: list[str] = Field(default_factory=list, max_length=20)
    prohibited_topics: list[str] = Field(default_factory=list, max_length=20)
    brand_safety_instructions: str = Field("", max_length=2000)


def _social_status(client_rec: dict | None) -> dict:
    """Honest per-capability connection status for the wizard's status board.
    Never raises. States: ready | manual | soon | need_phone.

    Auto-publish is ready ONLY when THIS customer has their own Postiz channel
    ids (clients_store or social_config) — global POSTIZ_API_KEY alone is not
    enough (audit 2026-07-17 false-ready + tenant isolation).
    """
    import os as _os

    rec = client_rec or {}
    engine_on = False
    postiz_key_on = False
    client_channels: list[str] = []
    integrations_source = "none"
    wa_ready = False
    approval_mode = "review"
    prefs_honored = _os.environ.get("SOCIAL_PREFS_HONOR", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    try:
        from app.social_engine import enabled as _engine_enabled

        engine_on = bool(_engine_enabled())
    except Exception:
        pass
    try:
        from app.marketing import postiz_publish

        postiz_key_on = bool(postiz_publish.enabled())
        client_channels = list(postiz_publish.effective_integration_ids(rec) or [])
        integrations_source = str(postiz_publish.integrations_source(rec) or "none")
    except Exception:
        pass
    try:
        from app.social_engine import client_config as _scfg

        cfg = _scfg.get(str(rec.get("id") or ""))
        approval_mode = str(cfg.get("approval_mode") or "review")
    except Exception:
        pass
    try:
        from app.social_engine.providers import WhatsAppProvider

        wa_ready = bool(str(rec.get("phone") or "").strip()) and bool(
            WhatsAppProvider._sender_configured()
        )
    except Exception:
        wa_ready = bool(str(rec.get("phone") or "").strip())

    # Ownership: customer must own channels via client/social_config — never env leak.
    ownership_ok = bool(client_channels and integrations_source in ("client", "social_config"))
    customer_postiz_ready = bool(postiz_key_on and ownership_ok)
    # Publish-path ready (approve → Postiz) vs hands-free (approval_mode=auto).
    publish_path_active = bool(engine_on and customer_postiz_ready)
    consent_auto = bool(prefs_honored and approval_mode == "auto")
    hands_free_active = bool(publish_path_active and consent_auto)

    channels = [
        {
            "key": "content",
            "label": "Roz ka content + captions",
            "state": "ready",
            "note": "Aapke branded posts aur Hinglish captions AI roz taiyaar karta hai.",
        },
        {
            "key": "whatsapp",
            "label": "WhatsApp delivery (aapke number pe)",
            "state": "ready" if wa_ready else "need_phone",
            "note": (
                "Approved post aapke apne WhatsApp pe aayega — 1-click forward. (Ban-safe, koi bulk nahi.)"
                if wa_ready
                else "Pehle apna WhatsApp/contact number add karo — phir yahan delivery start."
            ),
        },
        {
            "key": "autopublish",
            "label": "Auto-publish (Instagram/Facebook/YouTube via Postiz)",
            "state": "ready" if publish_path_active else "soon",
            "note": (
                f"Hands-free ON — aapke {len(client_channels)} channel(s), approval=auto."
                if hands_free_active
                else (
                    f"Aapke {len(client_channels)} owned channel(s) — approve ke baad publish. "
                    "Hands-free chahiye to Approval=Auto choose karo."
                    if publish_path_active
                    else (
                        "Postiz platform ready hai — abhi aapke account channels connect karo "
                        "(Postiz me apne pages link + integration IDs save)."
                        if postiz_key_on
                        else "Setup chal raha hai — abhi tak content approve karke manual/1-click post karo."
                    )
                )
            ),
        },
        {
            "key": "direct",
            "label": "Direct API posting (Google Business / LinkedIn)",
            "state": "soon",
            "note": "Platform approval process me — tab tak draft + manual post.",
        },
    ]
    return {
        "engine_on": engine_on,
        "postiz_on": customer_postiz_ready,
        "postiz_key_configured": postiz_key_on,
        "postiz_channels_count": len(client_channels),
        "integrations_source": integrations_source,
        "ownership_ok": ownership_ok,
        "prefs_honored": prefs_honored,
        "approval_mode": approval_mode,
        "consent_auto": consent_auto,
        "hands_free_active": hands_free_active,
        # Publish path armed (engine + owned channels) — not the same as hands-free.
        "auto_posting_active": publish_path_active,
        "channels": channels,
    }


@router.get("/social/config")
def customer_social_get(client_id: str = Depends(require_customer)) -> dict:
    """Social Setup Wizard read path — current handles + posting prefs + honest
    connection status so the portal can pre-fill. Never raises."""
    try:
        from app.marketing import clients_store
        from app.social_engine import client_config

        # Profile socials marketing id pe; social_config may be under either id
        # (legacy connects) — prefer canonical, fall back to raw login id.
        mcid = clients_store.canonical_client_id(client_id)
        rec = clients_store.resolve_client(client_id) or {}
        socials = rec.get("socials") or {}
        cfg = client_config.get(mcid) or client_config.get(client_id)
        handles = cfg.get("handles") or {}
        # instagram/facebook/gbp = clients_store.socials authoritative (profile
        # wizard bhi wahi likhta); config-store extended-handles overlay karta.
        merged_handles = {
            "instagram": socials.get("instagram", "") or handles.get("instagram", ""),
            "facebook": socials.get("facebook", "") or handles.get("facebook", ""),
            "gbp": socials.get("gbp", "") or handles.get("gbp", ""),
            "youtube": handles.get("youtube", ""),
            "linkedin": handles.get("linkedin", ""),
            "twitter": handles.get("twitter", ""),
        }
        return {
            "ok": True,
            "handles": merged_handles,
            "channels": cfg.get("channels") or [],
            "cadence": cfg.get("cadence") or "daily",
            "approval_mode": cfg.get("approval_mode") or "review",
            "postiz_integrations": cfg.get("postiz_integrations") or [],
            "timezone": cfg.get("timezone") or "Asia/Kolkata",
            "website": cfg.get("website") or "",
            "brand_tone": cfg.get("brand_tone") or "",
            "target_audience": cfg.get("target_audience") or "",
            "products_or_services": cfg.get("products_or_services") or "",
            "preferred_language": cfg.get("preferred_language") or "hinglish",
            "posting_days": cfg.get("posting_days") or [],
            "posting_times": cfg.get("posting_times") or [],
            "content_categories": cfg.get("content_categories") or [],
            "prohibited_topics": cfg.get("prohibited_topics") or [],
            "brand_safety_instructions": cfg.get("brand_safety_instructions") or "",
            "configured": bool(cfg.get("configured")),
            "status": _social_status(rec),
        }
    except Exception as e:
        logger.debug("customer social get failed: %s", e)
        return {"ok": False, "error": "social config load nahi hua"}


@router.post("/social/config")
def customer_social_save(body: SocialConfigIn, client_id: str = Depends(require_customer)) -> dict:
    """Social Setup Wizard write path — handles + posting preferences. IDOR-safe
    (client_id from JWT). Saving NEVER auto-posts: it only records preferences;
    real publish stays behind SOCIAL_ENGINE + a configured provider. Never-500."""
    try:
        from app.marketing import clients_store
        from app.social_engine import client_config

        handles = {
            "instagram": body.instagram.strip(),
            "facebook": body.facebook.strip(),
            "gbp": body.gbp.strip(),
            "youtube": body.youtube.strip(),
            "linkedin": body.linkedin.strip(),
            "twitter": body.twitter.strip(),
        }
        cfg = client_config.save(
            client_id,
            handles=handles,
            channels=body.channels,
            cadence=body.cadence,
            approval_mode=body.approval_mode,
            postiz_integrations=body.postiz_integrations,
            # Loop-social-19: Step-1 + Step-4 field pass-through.
            timezone=body.timezone or None,
            website=body.website or None,
            brand_tone=body.brand_tone or None,
            target_audience=body.target_audience or None,
            products_or_services=body.products_or_services or None,
            preferred_language=body.preferred_language or None,
            posting_days=body.posting_days or None,
            posting_times=body.posting_times or None,
            content_categories=body.content_categories or None,
            prohibited_topics=body.prohibited_topics or None,
            brand_safety_instructions=body.brand_safety_instructions or None,
        )
        # Mirror the 3 legacy handles into clients_store.socials so the mini-site /
        # page-kit (jo `socials` padhta) in-sync rahe — profile wizard jaisi hi
        # replace-semantics (khali value = clear). Best-effort, never raises.
        legacy = {k: handles[k] for k in ("instagram", "facebook", "gbp")}
        try:
            clients_store.update_client(client_id, socials=legacy)
        except Exception as e:
            logger.debug("customer social socials-mirror skip: %s", e)
        if not cfg:
            return {"ok": False, "error": "save nahi hua, dobara try karo"}
        # Sync delivery stage — social setup saved = advance to social_setup_completed
        _sync_social_delivery_stage(client_id, cfg)
        return {"ok": True, "config": cfg}
    except Exception as e:
        logger.warning("customer social save failed: %s", e)
        return {"ok": False, "error": str(e)[:160]}


def _sync_social_delivery_stage(client_id: str, cfg: dict) -> None:
    """Best-effort: social config saved → advance delivery_stage. Never raises."""
    try:
        handles = cfg.get("handles", {})
        has_social = any(str(handles.get(k, "")).strip() for k in ("instagram", "facebook", "gbp"))
        if not has_social:
            return
        from app.marketing.delivery_ledger import log_event

        # log_event me `customer_visible` param hai hi nahi — visibility LABELS se
        # derive hoti (social_setup_completed already customer_visible=True). Purana
        # kwarg TypeError phenkta tha jo neeche `except: pass` swallow kar leta →
        # milestone kabhi timeline me nahi aata tha. `key` = idempotency (re-save
        # pe duplicate milestone nahi).
        log_event(client_id, "social_setup_completed", key="social_setup:done")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Social Account CONNECT wizard — provider-mediated fallback (2026-07-11)      #
#                                                                             #
# WHY: The `/social/config` wizard above captures HANDLES (public URLs) + prefs.
# It does NOT give the engine a way to actually publish, because every direct-  #
# API provider (`MetaProvider`, `GBPProvider`, `LinkedInProvider`, `XProvider`,#
# `YouTubeProvider`) needs a per-client **access token** in the encrypted vault#
# (`social_engine.vault.put`). Meta/LinkedIn/GBP OAuth apps are still under    #
# app-review — so the interim connect flow is a **provider-mediated fallback**:#
# customer pastes a Page/Business token they obtained externally (Meta Graph   #
# Explorer / LI Developer app / GBP-linked location owner), we encrypt-and-    #
# store it via the existing Fernet vault, mark the account connected. Once the #
# platform-specific OAuth round-trip ships, this route stays as the interim +  #
# admin fallback path (`meta_pending`, `admin_paste`, `oauth_v1`... in `meta`).#
#                                                                             #
# GATED: `SOCIAL_ENGINE` still master-controls whether ANY publish actually    #
# happens. Connecting an account here NEVER auto-posts. Wizard's approval mode #
# still gates the "publish" step. Also: token never leaked back to the client. #
# --------------------------------------------------------------------------- #
_CONNECT_PLATFORMS = ("facebook", "instagram", "gbp", "linkedin", "x", "youtube", "postiz")


def _mask_ref(ref: str) -> str:
    """Show only tail so customer can distinguish accounts without leaking full id."""
    r = str(ref or "").strip()
    if not r:
        return ""
    if len(r) <= 6:
        return "…" + r
    return "…" + r[-6:]


def _mask_token_present(present: bool) -> str:
    return "✓ stored" if present else "—"


class SocialConnectIn(BaseModel):
    """Per-platform connect input. Token is Fernet-encrypted before it lands on disk.

    account_ref semantics per platform (matches provider dispatch):
      facebook  = Facebook Page ID
      instagram = IG Business User ID
      gbp       = accounts/{aid}/locations/{lid}
      linkedin  = urn:li:organization:{id} OR urn:li:person:{id}
      x         = "" (Bearer token is enough for basic tweet post)
      youtube   = Channel ID
      postiz    = "" (global admin cfg drives Postiz — customer route mainly declarative)
    """

    platform: str = Field(..., max_length=32)
    token: str = Field("", max_length=4096)
    account_ref: str = Field("", max_length=255)
    label: str = Field("", max_length=120)
    source: str = Field(
        "manual_paste",
        max_length=32,
        description="How this token was obtained (manual_paste, admin_paste, oauth_v1)",
    )


@router.get("/social/accounts")
def customer_social_accounts(client_id: str = Depends(require_customer)) -> dict:
    """List all social accounts stored for this customer. TOKEN NEVER LEAKED —
    only presence + masked account_ref + updated_at + meta.source. IDOR-safe
    (client_id from JWT). Never raises. States:
        connected            → row exists + token stored + not deleted
        provider_review_pending → platform requires app-review; will publish only
                                  once SOCIAL_ENGINE + Meta app-review both pass
        not_connected        → nothing stored for this platform yet"""
    try:
        from app.social_engine import vault

        rows = vault.list_accounts(client_id) or []
        accounts_by_plat: dict[str, list[dict]] = {p: [] for p in _CONNECT_PLATFORMS}
        for r in rows:
            plat = str(r.get("platform") or "").strip().lower()
            if plat not in accounts_by_plat:
                continue
            meta = r.get("meta") or {}
            # Loop 27 (2026-07-11): add opaque account_id (short sha1 of client+plat+ref)
            # so the frontend Disconnect button can DELETE the exact record even though
            # the customer never sees the full account_ref back. account_ref itself
            # (e.g. FB Page ID) is not a secret but we keep it masked for display.
            _raw_ref = str(r.get("account_ref") or "")
            try:
                import hashlib as _h

                _acct_id = _h.sha1(
                    (f"{client_id}|{plat}|{_raw_ref}").encode(), usedforsecurity=False
                ).hexdigest()[:16]
            except Exception:
                _acct_id = ""
            accounts_by_plat[plat].append(
                {
                    "platform": plat,
                    "account_id": _acct_id,  # opaque, DELETE-safe (Loop 27)
                    "account_ref_masked": _mask_ref(_raw_ref),
                    "label": str(meta.get("label") or "")[:120],
                    "source": str(meta.get("source") or "manual_paste")[:32],
                    "updated_at": str(r.get("ts") or ""),
                    "token_stored": _mask_token_present(True),  # list_accounts filters deleted
                }
            )

        # Platform-level summary — customer wizard consumes this to render per-platform
        # "Connect / Reconnect / Disconnect" buttons + honest state text.
        _review_pending = {"facebook", "instagram", "gbp", "linkedin", "x", "youtube"}
        platforms = []
        for p in _CONNECT_PLATFORMS:
            has = bool(accounts_by_plat[p])
            state = (
                "connected"
                if has
                else ("provider_review_pending" if p in _review_pending else "not_connected")
            )
            platforms.append(
                {
                    "platform": p,
                    "connected": has,
                    "state": state,
                    "account_count": len(accounts_by_plat[p]),
                    "requires_review": p in _review_pending and not has,
                }
            )

        return {
            "ok": True,
            "platforms": platforms,
            "accounts": accounts_by_plat,
        }
    except Exception as e:
        logger.debug("customer social accounts list failed: %s", e)
        return {"ok": False, "platforms": [], "accounts": {}, "error": "load nahi hua"}


@router.post(
    "/social/accounts/connect",
    dependencies=[Depends(rate_limit("cust_social_connect", 12, 300))],
)
def customer_social_accounts_connect(
    body: SocialConnectIn,
    client_id: str = Depends(require_customer),
) -> dict:
    """Store an encrypted per-client per-platform access token. IDOR-safe: token
    is stored under the JWT's client_id, NEVER a body-supplied client_id.

    NEVER auto-posts. Just registers the account so `social_engine` can dispatch
    once `SOCIAL_ENGINE` is enabled by the operator. Token is Fernet-encrypted
    at rest (`vault._encrypt` — warns loudly if `SOCIAL_TOKEN_KEY`/`SECRET_KEY`
    both unset). Never-500."""
    try:
        from app.social_engine import vault

        plat = str(body.platform or "").strip().lower()
        if plat not in _CONNECT_PLATFORMS:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_platform",
                    "message": f"Sirf {', '.join(_CONNECT_PLATFORMS)} allowed hain",
                },
            )
        tok = str(body.token or "").strip()
        if not tok or len(tok) < 8:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_token",
                    "message": "Access token kam se kam 8 char ka hona chahiye",
                },
            )
        ref = str(body.account_ref or "").strip()[:255]
        # Meta / GBP / LI ke liye account_ref MANDATORY (dispatch node id). X/YT
        # ke liye optional — provider unhe token alone se resolve karta.
        if plat in ("facebook", "instagram", "gbp", "linkedin") and not ref:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "account_ref_required",
                    "message": {
                        "facebook": "Facebook Page ID chahiye",
                        "instagram": "Instagram Business User ID chahiye",
                        "gbp": "GBP location resource (accounts/…/locations/…) chahiye",
                        "linkedin": "LinkedIn organization/person urn chahiye",
                    }.get(plat, "account_ref chahiye"),
                },
            )

        source = str(body.source or "manual_paste").strip().lower()
        if source not in ("manual_paste", "admin_paste", "oauth_v1"):
            source = "manual_paste"
        meta = {
            "label": str(body.label or "")[:120],
            "source": source,
        }
        ok = bool(vault.put(client_id, plat, tok, account_ref=ref, meta=meta))
        if not ok:
            return {
                "ok": False,
                "error": "vault_put_failed",
                "message": "Token save nahi hua, dobara try karo",
            }

        # Best-effort delivery-ledger + team-feed logging so ops/customer both see the
        # connect event. Never-raise (best-effort per §4).
        try:
            from app.marketing import delivery_ledger

            delivery_ledger.log_event(
                client_id,
                "social_setup_completed",
                detail=f"{plat} account connected",
                key=f"social_connect:{plat}:{ref}",
            )
        except Exception:
            pass
        try:
            from app.platform import team

            team.log_event(
                "zara",
                "social_account_connected",
                f"{client_id}: {plat} account connected (source={source})",
                status="ok",
            )
        except Exception:
            pass

        return {
            "ok": True,
            "platform": plat,
            "account_ref_masked": _mask_ref(ref),
            "state": "connected",
            "note": "Connect ho gaya. Actual publish `SOCIAL_ENGINE` on hone par shuru hoga.",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("customer social connect failed: %s", e)
        return {"ok": False, "error": "connect_failed", "message": str(e)[:160]}


@router.delete("/social/accounts/{platform}")
def customer_social_accounts_disconnect(
    platform: str,
    account_ref: str = Query("", max_length=255),
    account_id: str = Query("", max_length=32),
    client_id: str = Depends(require_customer),
) -> dict:
    """Soft-delete a stored social account (`vault.delete` → deleted marker in
    JSONL, latest-wins). IDOR-safe (client_id from JWT). Never-500.

    Loop 27 (2026-07-11): now accepts either `account_ref` (legacy — full ref)
    OR `account_id` (opaque sha1 hash returned by GET /social/accounts). Frontend
    only ever sees masked `…tail` for privacy, so `account_id` is the reliable
    handle for DELETE; `account_ref` retained for backwards compat + admin tools.
    """
    try:
        from app.social_engine import vault

        plat = str(platform or "").strip().lower()
        if plat not in _CONNECT_PLATFORMS:
            raise HTTPException(status_code=400, detail="invalid platform")
        resolved_ref = (account_ref or "").strip()[:255]
        aid = (account_id or "").strip()[:32]
        if aid and not resolved_ref:
            # Resolve opaque id → full account_ref by rescanning the vault for
            # a matching sha1(client|plat|ref)[:16]. Bounded by per-customer
            # account count (small); safe to iterate.
            try:
                import hashlib as _h

                rows = vault.list_accounts(client_id) or []
                for _r in rows:
                    _rp = str(_r.get("platform") or "").strip().lower()
                    if _rp != plat:
                        continue
                    _rr = str(_r.get("account_ref") or "")
                    _h1 = _h.sha1(
                        (f"{client_id}|{plat}|{_rr}").encode(), usedforsecurity=False
                    ).hexdigest()[:16]
                    if _h1 == aid:
                        resolved_ref = _rr[:255]
                        break
            except Exception as _e:
                logger.warning("customer social disconnect account_id resolve failed: %s", _e)
        ok = bool(vault.delete(client_id, plat, account_ref=resolved_ref))
        try:
            from app.platform import team

            team.log_event(
                "zara",
                "social_account_disconnected",
                f"{client_id}: {plat} account_ref={_mask_ref(resolved_ref)}",
                status="warn",
            )
        except Exception:
            pass
        return {"ok": ok, "platform": plat, "state": "disconnected"}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("customer social disconnect failed: %s", e)
        return {"ok": False, "error": "disconnect_failed", "message": str(e)[:160]}


@router.get("/social/readiness")
def customer_social_readiness(client_id: str = Depends(require_customer)) -> dict:
    """Loop-social-16 (2026-07-11): Phase-3 Step-5 readiness check. Aggregates
    signals from business profile + brand assets + social accounts + prefs
    into a single completeness score + missing-piece list so the wizard shows
    "80% ready — 2 items pending" and the customer never leaves setup blindly.

    Never raises; empty client → all-required."""
    try:
        from app.marketing import clients_store
        from app.social_engine import client_config as _cc
        from app.social_engine import vault as _vault

        mcid = clients_store.canonical_client_id(client_id)
        rec = clients_store.resolve_client(client_id) or {}
        cfg = _cc.get(mcid) or _cc.get(client_id) or {}
        accts = _vault.list_accounts(mcid) or _vault.list_accounts(client_id) or []
        socials = rec.get("socials") or {}
        assets = rec.get("brand_assets") or {}

        checks = []

        def _add(key: str, label: str, ok: bool, action: str) -> None:
            checks.append(
                {"key": key, "label": label, "ok": bool(ok), "action": "" if ok else action}
            )

        # Step 1: business profile
        _add(
            "business_name",
            "Business ka naam",
            bool(str(rec.get("business_name") or "").strip()),
            "Business name add karo",
        )
        _add(
            "niche",
            "Niche / category",
            bool(str(rec.get("niche") or "").strip()),
            "Niche select karo",
        )
        _add(
            "location",
            "Location / city",
            bool(str(rec.get("city") or rec.get("location") or "").strip()),
            "Sheher select karo",
        )
        _add(
            "phone",
            "Contact number",
            bool(str(rec.get("phone") or "").strip()),
            "WhatsApp number add karo",
        )
        _add("email", "Email", bool(str(rec.get("email") or "").strip()), "Email confirm karo")

        # Step 2: brand assets
        _add(
            "brand_logo",
            "Logo",
            bool(assets.get("logo_url") or rec.get("logo_url")),
            "Logo upload karo (Brand section)",
        )
        _add(
            "brand_colors",
            "Brand color",
            bool(assets.get("primary_color") or rec.get("primary_color")),
            "Ek brand color choose karo",
        )

        # Step 3: at least one social account connected OR a social handle
        has_any_social = bool(accts) or any(
            str(socials.get(k) or "").strip() for k in ("instagram", "facebook", "gbp")
        )
        _add(
            "social_account",
            "Ek social account",
            has_any_social,
            "Kam se kam ek Instagram/Facebook/GBP connect karo",
        )

        # Step 4: content prefs
        _add(
            "channels_chosen",
            "AI kin channels ke liye content banaye",
            bool(cfg.get("channels")),
            "Wizard me channel select karo",
        )
        _add(
            "cadence",
            "Content cadence",
            str(cfg.get("cadence") or "").strip() not in ("", "off"),
            "Weekly cadence choose karo",
        )
        _add(
            "approval_mode",
            "Approval preference",
            bool(str(cfg.get("approval_mode") or "").strip()),
            "Approve-mode select karo (recommended: review)",
        )

        total = len(checks)
        done = sum(1 for c in checks if c["ok"])
        pending = [c for c in checks if not c["ok"]]
        percent = int(round(100.0 * done / total)) if total else 0
        return {
            "ok": True,
            "score": percent,
            "done": done,
            "total": total,
            "checks": checks,
            "pending": pending,
            "ready_to_publish": percent >= 80
            and any(c["key"] == "social_account" and c["ok"] for c in checks),
        }
    except Exception as e:
        logger.debug("customer social readiness failed: %s", e)
        return {
            "ok": False,
            "score": 0,
            "checks": [],
            "pending": [],
            "ready_to_publish": False,
            "error": "readiness load nahi hua",
        }


@router.get("/branded-feed")
async def customer_branded_feed(client_id: str = Depends(require_customer)):
    """AdBanao-style aaj ke 3 branded posts (logo+naam frame) — customer scoped."""
    try:
        from app.marketing import brand_frames
        from app.marketing.clients_store import resolve_client

        c = resolve_client(client_id) or {}
        slug = str(c.get("slug") or client_id or "").strip()
        return await brand_frames.daily_feed(slug)
    except Exception as e:
        logger.debug("customer branded-feed failed: %s", e)
        return {"ok": False, "error": "feed load nahi hua", "posts": []}


@router.get("/timeline")
def customer_delivery_timeline(client_id: str = Depends(require_customer), limit: int = 30) -> dict:
    """'AI ne aapke liye kya kiya' — customer's own delivery-ledger timeline.
    client_id JWT (require_customer) se aata hai => customer sirf apni hi
    timeline dekhta hai. Never raises; empty list on any error."""
    try:
        from app.marketing import clients_store
        from app.marketing.delivery_ledger import ensure_backfilled, timeline

        # Ledger files marketing id pe keyed hain — billing/login alias (Jiya
        # `d79d690f61b3`) ko canonicalize kiye bina timeline blank dikhti thi.
        mcid = clients_store.canonical_client_id(client_id)
        # Pre-ledger (purane paid) customers ka historical timeline pehli read pe
        # lazily backfill karo — warna jiya jaise existing customer ko "AI ne kya
        # kiya" blank dikhta. Idempotent (marker file), never-raises.
        ensure_backfilled(mcid)
        events = timeline(mcid, limit=limit, customer_only=True)
        return {"ok": True, "events": events}
    except Exception as e:
        logger.debug("customer timeline failed: %s", e)
        return {"ok": False, "events": []}


@router.get("/delivery-proof")
def customer_delivery_proof(client_id: str = Depends(require_customer)) -> dict:
    """Customer-safe Product One proof/report.

    No cron/API/worker jargon. Shows what they bought, what is complete, what is
    pending, and proof notes for monthly renewal conversations.
    """
    try:
        from app.marketing import product_one_delivery

        state = product_one_delivery.customer_delivery_status(client_id)
        deliverables = [d for d in state.get("deliverables", []) if d.get("customer_visible", True)]
        # Fetch pending approvals + published posts for the new delivery view.
        # Marketing content/approvals/ledger are keyed on the canonical marketing
        # id (Jiya: `jiya-makeover`); the JWT carries the billing/login alias
        # (`d79d690f61b3`). Canonicalize once for every marketing-domain read.
        approvals_pending = []
        posts_published = []
        business_name = ""
        try:
            from app.marketing import clients_store

            mcid = clients_store.canonical_client_id(client_id)
            c = clients_store.resolve_client(client_id) or {}
            business_name = c.get("business_name", "")
        except Exception:
            mcid = client_id
        try:
            from app.marketing import content_approval

            for row in content_approval.pending(mcid)[:10]:
                content = row.get("content") or {}
                caption = str(content.get("caption") or content.get("text") or "")
                approvals_pending.append(
                    {
                        "id": row.get("id"),
                        "status": row.get("status"),
                        "created_at": row.get("created_at"),
                        "title": content.get("title") or content.get("occasion") or "Post",
                        "caption_preview": caption[:180],
                        "content": content,
                    }
                )
        except Exception:
            approvals_pending = []
        try:
            from app.marketing.delivery_ledger import timeline

            ledger = timeline(mcid, limit=100)
            posts_published = [
                {
                    "date": e.get("at", "")[:10],
                    "title": e.get("detail") or e.get("label") or e.get("event", "Post"),
                    "detail": e.get("detail", ""),
                    "status": "published" if e.get("event") == "post_published" else "approved",
                    "status_label": (
                        "Published" if e.get("event") == "post_published" else "Approved"
                    ),
                }
                for e in ledger
                if e.get("event") in ("post_published", "post_approved")
            ][:10]
        except Exception:
            posts_published = []
        return {
            "ok": True,
            "business_name": business_name or state.get("customer_name"),
            "customer_name": state.get("customer_name"),
            "plan": state.get("plan"),
            "stage": state.get("stage"),
            "stage_label": state.get("stage_label"),
            "setup_completion_pct": state.get("setup_completion_pct"),
            "deliverable_completion_pct": state.get("deliverable_completion_pct"),
            "next_action": state.get("next_action"),
            "deliverables": deliverables,
            "approvals_pending": approvals_pending,
            "posts_published": posts_published,
            "proof_summary": {
                "content_ready": state.get("content_generated", 0),
                "approval_pending": state.get("posts_waiting_for_approval", 0),
                "scheduled": state.get("posts_scheduled", 0),
                "published": state.get("posts_published", 0),
            },
            "customer_status_notes": state.get("customer_status_notes") or [],
            "monthly_summary": state.get("monthly_summary") or {},
            "customer_message": _customer_delivery_message(state),
        }
    except Exception as e:
        logger.debug("customer delivery-proof failed: %s", e)
        return {"ok": False, "deliverables": [], "customer_message": "Report abhi load nahi hua."}


def _customer_delivery_message(state: dict) -> str:
    stage = str(state.get("stage") or "")
    if state.get("risk_flag") == "customer_blocked":
        return "Aapke kuch setup details pending hain. Ye complete hote hi content delivery tez ho jayegi."
    if stage in ("content_ready", "approval_pending"):
        return "Aapke posts ready hain. Approval ke baad publish/manual delivery ho jayegi."
    if stage in ("published", "report_sent", "renewal_ready"):
        return "Aapke liye delivery proof ready hai. Neeche completed items dekh sakte hain."
    return "Setup aur content delivery progress yahan live update hoti rahegi."


@router.get("/approvals/pending")
def customer_pending_approvals(client_id: str = Depends(require_customer)):
    """Posts jo client approval ka wait kar rahe hain."""
    try:
        from app.marketing import clients_store, content_approval

        rows = content_approval.pending(clients_store.canonical_client_id(client_id))
        safe = [
            {
                "id": r.get("id"),
                "status": r.get("status"),
                "created_at": r.get("created_at"),
                "content": r.get("content") or {},
                "needs_admin": bool(r.get("needs_admin")),
                "admin_note": r.get("admin_note") or "",
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
    """Portal se approve/reject/escalate — token link ki zaroorat nahi."""
    from app.marketing import clients_store, content_approval

    # Approval records marketing id pe keyed hain aur decide/escalate ownership
    # check `rec.client_id == cid` karta hai. UPI/billing alias se login (Jiya
    # `d79d690f61b3`) ko canonical marketing id (`jiya-makeover`) pe map kiye bina
    # ownership check kabhi match nahi hota → customer apna content approve hi
    # nahi kar pata tha. canonical_client_id sirf isi tenant ke record pe map
    # karta (billing_client_ids), isliye cross-tenant access nahi khulta.
    cid = clients_store.canonical_client_id(client_id)
    if body.action == "escalate":
        return content_approval.escalate_for_client(cid, approval_id, note=body.note or "")
    return content_approval.decide_for_client(cid, approval_id, body.action, body.note or "")


@router.post(
    "/approvals/{approval_id}/council-decide",
    dependencies=[Depends(rate_limit("approval_council", 6, 60))],
)
async def customer_approval_council_decide(
    approval_id: str,
    body: ApprovalCouncilIn | None = None,
    client_id: str = Depends(require_customer),
):
    """Samajh nahi aaya → LLM Council decide (APPROVE / PARK_ADMIN / KEEP)."""
    from app.marketing import clients_store
    from app.platform import boss_council

    # Council ownership check `_by_id_for_client` marketing id pe match karta —
    # billing alias se login pe "pending approval nahi mila" aata tha.
    apply = True if body is None else bool(body.apply)
    return await boss_council.decide_approval(
        clients_store.canonical_client_id(client_id), approval_id, apply=apply
    )


def _customer_video_record(mcid: str, video_ad_id: str) -> dict | None:
    from app.marketing import video_ad_cycle

    for row in video_ad_cycle.list_for_client(mcid):
        if str(row.get("id") or "") == str(video_ad_id or ""):
            return row
    return None


def _resolve_customer_video_path(rec: dict) -> Path | None:
    raw = str(rec.get("video_path") or "").strip()
    if not raw:
        return None
    # SERVABLE == APPROVABLE == SNAPSHOTTABLE == PUBLISHABLE: one media-root
    # authority for all four, so a file the publish gate rejects can never be
    # served, and vice versa. A second local definition would drift.
    try:
        from app.marketing.video_media_paths import resolve_video_media_file

        resolved = resolve_video_media_file(raw)
        if resolved is None or resolved.suffix.lower() != ".mp4":
            return None
        return resolved
    except (OSError, RuntimeError, ValueError):
        return None


def _customer_video_context(client_id: str) -> tuple[str, bool]:
    from app.marketing import clients_store
    from app.marketing.video_production import flags

    mcid = clients_store.canonical_client_id(client_id)
    return mcid, flags.customer_review_allowed(mcid)


@router.get("/videos")
def customer_videos_list(client_id: str = Depends(require_customer)):
    """Customer Video Production Cell — own videos only (tenant-isolated)."""
    try:
        from app.marketing import video_ad_cycle

        mcid, enabled = _customer_video_context(client_id)
        if not enabled:
            return {"ok": True, "enabled": False, "count": 0, "videos": []}
        rows = video_ad_cycle.list_for_client(mcid)
        safe = []
        for r in rows:
            rid = str(r.get("id") or "")
            revision = int(r.get("revision") or 0)
            media_path = _resolve_customer_video_path(r)
            safe.append(
                {
                    "id": rid,
                    "status": r.get("status"),
                    "workflow_state": r.get("workflow_state"),
                    "revision": revision,
                    "approved_version": r.get("approved_version"),
                    "caption": r.get("caption"),
                    "channels": r.get("channels"),
                    "created_at": r.get("created_at"),
                    "published_at": r.get("published_at"),
                    "approval_id": r.get("approval_id"),
                    "has_video": media_path is not None,
                    "media_url": (
                        f"/api/customer/videos/{quote(rid, safe='')}/media?revision={revision}"
                        if media_path is not None
                        else None
                    ),
                    "aspect_ratio": r.get("aspect_ratio") or "9:16",
                    "feedback_categories": r.get("feedback_categories") or [],
                }
            )
        return {"ok": True, "enabled": True, "count": len(safe), "videos": safe}
    except Exception as e:
        logger.debug("customer videos list failed: %s", e)
        return {"ok": False, "enabled": False, "count": 0, "videos": []}


@router.get("/videos/{video_ad_id}/preview")
def customer_video_preview(
    video_ad_id: str,
    client_id: str = Depends(require_customer),
):
    """Identity of the EXACT artifact the customer is about to review.

    Hashes only THIS video (never the whole list) through a single descriptor.
    The customer approves the revision + digest returned here, so an in-place
    re-render between preview and approve is detectable. No filesystem path is
    ever exposed.
    """
    mcid, enabled = _customer_video_context(client_id)
    if not enabled:
        raise HTTPException(status_code=404, detail="video not found")
    rec = _customer_video_record(mcid, video_ad_id)
    if not rec:
        raise HTTPException(status_code=404, detail="video not found")

    from app.marketing.video_media_paths import observe_content_identity

    observed = observe_content_identity(str(rec.get("video_path") or ""))
    if not observed.get("ok"):
        raise HTTPException(status_code=409, detail=str(observed.get("error") or "unverifiable"))
    return {
        "ok": True,
        "id": str(rec.get("id") or ""),
        "revision": int(rec.get("revision") or 0),
        "status": rec.get("status"),
        "caption": rec.get("caption"),
        "content_sha256": observed["sha256"],
        "content_bytes": observed["bytes"],
        "etag": observed["etag"],
        "media_url": (
            f"/api/customer/videos/{quote(str(rec.get('id') or ''), safe='')}"
            f"/media?revision={int(rec.get('revision') or 0)}"
        ),
    }


@router.get("/videos/{video_ad_id}/media")
def customer_video_media(
    video_ad_id: str,
    revision: int = Query(..., ge=0),
    client_id: str = Depends(require_customer),
    range_header: str | None = Header(None, alias="Range"),
):
    """Serve an exact customer-owned video version with HTTP Range (seek) support.

    Starlette FileResponse lacks reliable Range for HTML5 video scrubbing — stream
    bytes ourselves while keeping the revision gate fail-closed.
    """
    mcid, enabled = _customer_video_context(client_id)
    if not enabled:
        raise HTTPException(status_code=404, detail="video not found")
    rec = _customer_video_record(mcid, video_ad_id)
    if not rec:
        raise HTTPException(status_code=404, detail="video not found")
    current_revision = int(rec.get("revision") or 0)
    if current_revision != revision:
        raise HTTPException(status_code=409, detail="video version changed; refresh review")
    media_path = _resolve_customer_video_path(rec)
    if media_path is None:
        logger.warning("customer video media refused id=%s tenant=%s", video_ad_id, mcid)
        raise HTTPException(status_code=404, detail="video not found")

    # ONE descriptor for identity AND streaming. Hashing via one open() and then
    # re-open()ing the path to stream would let a path replacement in between
    # serve bytes that do not match the advertised ETag.
    from app.marketing.video_media_paths import open_verified_media

    opened = open_verified_media(str(rec.get("video_path") or ""))
    if not opened.get("ok"):
        raise HTTPException(status_code=409, detail=str(opened.get("error") or "unverifiable"))
    media_fh = opened["fh"]
    observed = {"sha256": opened["sha256"], "bytes": opened["bytes"], "etag": opened["etag"]}

    file_size = int(observed["bytes"])
    filename = f"video_ad_{video_ad_id}.mp4"
    base_headers = {
        "Content-Type": "video/mp4",
        "Content-Disposition": f'inline; filename="{filename}"',
        "Accept-Ranges": "bytes",
        "Cache-Control": "private, max-age=300, no-transform",
        "ETag": observed["etag"],
        "X-Content-SHA256": observed["sha256"],
    }

    def _unsatisfiable() -> Response:
        try:
            media_fh.close()
        except OSError:
            pass
        return Response(
            status_code=416,
            headers={
                "Content-Range": f"bytes */{file_size}",
                **base_headers,
            },
        )

    if range_header:
        range_str = range_header.strip()
        if "," in range_str:
            return _unsatisfiable()

        m_start_end = re.match(r"^bytes=(\d+)-(\d+)$", range_str)
        m_open_end = re.match(r"^bytes=(\d+)-$", range_str)
        m_suffix = re.match(r"^bytes=-(\d+)$", range_str)

        start: int | None = None
        end: int | None = None
        if m_start_end:
            start = int(m_start_end.group(1))
            end = int(m_start_end.group(2))
        elif m_open_end:
            start = int(m_open_end.group(1))
            end = file_size - 1
        elif m_suffix:
            suffix_len = int(m_suffix.group(1))
            if suffix_len == 0:
                return _unsatisfiable()
            start = max(0, file_size - suffix_len)
            end = file_size - 1
        else:
            return _unsatisfiable()

        if start < 0 or start >= file_size or end < start:
            return _unsatisfiable()

        end = min(end, file_size - 1)
        content_length = end - start + 1
        headers = {
            **base_headers,
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        }

        def iter_range():
            # Same descriptor the ETag was computed from — no re-open, so a path
            # replacement cannot change the bytes served. Closed deterministically
            # on completion, exception, or client disconnect (GeneratorExit).
            try:
                media_fh.seek(start)
                remaining = content_length
                chunk_size = 64 * 1024
                while remaining > 0:
                    read_bytes = media_fh.read(min(chunk_size, remaining))
                    if not read_bytes:
                        break
                    remaining -= len(read_bytes)
                    yield read_bytes
            finally:
                try:
                    media_fh.close()
                except OSError:
                    pass

        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers=headers,
            media_type="video/mp4",
        )

    headers = {
        **base_headers,
        "Content-Length": str(file_size),
    }

    def iter_full():
        # Same descriptor the ETag was computed from (see iter_range).
        try:
            media_fh.seek(0)
            chunk_size = 64 * 1024
            while chunk := media_fh.read(chunk_size):
                yield chunk
        finally:
            try:
                media_fh.close()
            except OSError:
                pass

    return StreamingResponse(
        iter_full(),
        status_code=200,
        headers=headers,
        media_type="video/mp4",
    )


class VideoFeedbackIn(BaseModel):
    text: str = Field("", max_length=300)
    action: str = "changes"  # approve | changes | reject
    expected_revision: int = Field(..., ge=0)
    # Required for action="approve": the digest the customer actually previewed.
    # Optional here so changes/reject keep working; the approve branch enforces
    # presence and shape, fail-closed.
    expected_content_sha256: str = Field("", max_length=64)


async def _approval_session_facts(client_id: str, creds) -> tuple[bool, bool]:
    """Establish, server-side, the two facts ``require_customer`` does not.

    Returns ``(tenant_verified, revocation_verified)``. Both are POSITIVE
    checks: an error anywhere yields False, so approval fails closed. The read
    paths deliberately keep their existing fail-open behaviour — this stricter
    rule applies only to the approval mutation.
    """
    tenant_verified = False
    try:
        from app.marketing import clients_store

        rec = clients_store.resolve_client(client_id)
        tenant_verified = bool(rec and str(rec.get("id") or "").strip())
    except Exception:
        tenant_verified = False

    revocation_verified = False
    try:
        from app.cache import get_redis_client

        token = getattr(creds, "credentials", "") or ""
        if token:
            redis_client = await get_redis_client()
            revoked = await redis_client.exists(f"customer:logout:{token[:20]}")
            revocation_verified = not revoked
    except Exception:
        # Store unreachable => we cannot prove the session is still valid.
        revocation_verified = False
    return tenant_verified, revocation_verified


@router.post("/videos/{video_ad_id}/feedback")
async def customer_video_feedback(
    video_ad_id: str,
    body: VideoFeedbackIn,
    client_id: str = Depends(require_customer),
    creds: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)),
):
    """Dashboard video review — same intents as WhatsApp (version-bound)."""
    from app.marketing import clients_store, content_approval, video_ad_cycle
    from app.marketing.video_production import cell, flags, states
    from app.marketing.video_production.feedback import classify_feedback

    mcid = clients_store.canonical_client_id(client_id)
    if not flags.customer_review_allowed(mcid):
        raise HTTPException(status_code=403, detail="customer video review disabled")
    rec = _customer_video_record(mcid, video_ad_id)
    if not rec:
        raise HTTPException(status_code=404, detail="video nahi mila")
    current_revision = int(rec.get("revision") or 0)
    if current_revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="video version changed; refresh review")
    action = (body.action or "changes").strip().lower()
    if action not in {"approve", "changes", "reject"}:
        raise HTTPException(status_code=422, detail="invalid video feedback action")
    current_status = str(rec.get("status") or "").strip().lower()
    approved_version = rec.get("approved_version")
    try:
        approved_revision = int(approved_version) if approved_version is not None else None
    except (TypeError, ValueError):
        approved_revision = None
    if current_status != "pending":
        if (
            action == "approve"
            and current_status == "approved"
            and approved_revision == body.expected_revision
        ):
            txn_state = str(rec.get("approval_txn_state") or "").strip()
            hash_ok = bool(str(rec.get("approved_content_sha256") or "").strip())
            snap_ok = bool(str(rec.get("approval_snapshot_path") or "").strip())
            if txn_state == "finalized" and hash_ok and snap_ok:
                return {"ok": True, "already_decided": True, "status": "approved"}
            if txn_state == "":
                # Legacy approved with no saga transaction — fall through to fresh approve.
                current_status = "pending"
            else:
                raise HTTPException(
                    status_code=409,
                    detail=f"approval_not_finalized:{txn_state}",
                )
        if current_status != "pending":
            raise HTTPException(status_code=409, detail="video review already decided; refresh")
    if action == "approve":
        # Bind the approval to the bytes the customer actually previewed. Every
        # refusal below happens BEFORE any ledger write, record update, snapshot
        # or provider call.
        import re as _re

        from app.marketing.video_media_paths import observe_content_identity

        expected_hash = str(body.expected_content_sha256 or "").strip().lower()
        if not _re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise HTTPException(status_code=400, detail="expected_content_sha256 required (64-hex)")
        observed = observe_content_identity(str(rec.get("video_path") or ""))
        if not observed.get("ok"):
            raise HTTPException(
                status_code=409, detail=str(observed.get("error") or "content_unverifiable")
            )
        if observed["sha256"] != expected_hash:
            raise HTTPException(status_code=409, detail="approval_content_changed")
        from app.marketing.video_production.approval_principal import (
            PrincipalRefused,
            from_customer_session,
        )

        # Server-constructed from the verified session. `mcid` is the canonical
        # tenant from require_customer, never request input. Tenant existence
        # and session revocation are proven POSITIVELY here — require_customer's
        # revocation check fails open, which is not acceptable for a mutation.
        tenant_ok, revocation_ok = await _approval_session_facts(mcid, creds)
        try:
            principal = from_customer_session(
                mcid, tenant_verified=tenant_ok, revocation_verified=revocation_ok
            )
        except PrincipalRefused as exc:
            raise HTTPException(status_code=exc.status, detail=exc.code) from None
        out = cell.approve_version(
            str(video_ad_id),
            body.expected_revision,
            principal=principal,
            expected_sha256=expected_hash,
        )
        if not out.get("ok"):
            raise HTTPException(status_code=409, detail=str(out.get("error") or "approval failed"))
        return out
    text = (body.text or "").strip()
    classified = classify_feedback(text if action != "reject" else "REJECT")
    if action == "reject":
        classified = {"intent": "reject", **{k: v for k, v in classified.items() if k != "intent"}}
    tok = str(rec.get("token") or "")
    if not tok:
        return {"ok": False, "error": "approval token missing"}
    if classified.get("intent") == "ambiguous" and action == "changes" and not text:
        return {
            "ok": False,
            "ambiguous": True,
            "clarification": "CHANGES ke saath detail likho (jaise: logo bada karo).",
        }
    note = text[:300] or action
    approval = content_approval.get_by_token(tok)
    if not approval or str(approval.get("status") or "").strip().lower() != "pending":
        raise HTTPException(status_code=409, detail="approval already decided; refresh review")
    if action == "reject":
        # Terminal first: the generic rejection hook only converts pending videos
        # to changes_requested, so a hard reject can never enter the regen queue.
        video_ad_cycle._update(
            str(video_ad_id),
            status="held_max_revisions",
            workflow_state=states.CLIENT_REJECTED,
            final_approved=False,
            note=note,
            revision_tasks=[],
            feedback_categories=[],
        )
    out = content_approval.reject(tok, note=note)
    if not out.get("ok") or out.get("already_decided"):
        raise HTTPException(status_code=409, detail="approval already decided; refresh review")
    video_ad_cycle._update(
        str(video_ad_id),
        revision_tasks=classified.get("tasks") or [],
        feedback_categories=classified.get("categories") or [],
    )
    return {"ok": True, "classified": classified, "approval": out}


# ---------- Creative Automation OS (ADR-143) — customer review surface ---------- #
class CreativeFeedbackIn(BaseModel):
    text: str = Field("", max_length=300)
    action: str = "changes"  # approve | changes
    expected_revision: int = Field(..., ge=0)


@router.get("/creative-os")
def customer_creative_os_list(client_id: str = Depends(require_customer)):
    """Customer-owned Creative OS items — JWT tenant only, no infra leak."""
    try:
        from app.marketing import clients_store
        from app.marketing.creative_os import flags as cflags
        from app.marketing.creative_os.service import customer_view, list_cockpit

        if not cflags.os_enabled():
            return {"ok": True, "enabled": False, "count": 0, "creatives": []}
        mcid = clients_store.canonical_client_id(client_id)
        out = list_cockpit(mcid, limit=50)
        items = []
        for row in out.get("items") or []:
            view = customer_view(mcid, str(row.get("creative_id") or ""))
            if view.get("ok"):
                items.append(view)
        return {"ok": True, "enabled": True, "count": len(items), "creatives": items}
    except Exception as e:
        logger.debug("customer creative-os list failed: %s", e)
        return {"ok": False, "enabled": False, "count": 0, "creatives": []}


@router.get("/creative-os/{creative_id}/media")
def customer_creative_os_media(
    creative_id: str,
    revision: int = Query(..., ge=0),
    client_id: str = Depends(require_customer),
):
    """Serve Creative OS media via authenticated path resolve — no raw path exposure."""
    from app.marketing import clients_store
    from app.marketing.creative_os import flags as cflags
    from app.marketing.creative_os.service import resolve_output_path
    from app.marketing.creative_os.store import get_record

    if not cflags.os_enabled():
        raise HTTPException(status_code=404, detail="creative not found")
    mcid = clients_store.canonical_client_id(client_id)
    got = get_record(mcid, creative_id)
    if not got.get("ok"):
        raise HTTPException(status_code=404, detail="creative not found")
    rec = got["record"]
    current_revision = int(rec.get("approval_revision") or 0)
    if current_revision != revision:
        raise HTTPException(status_code=409, detail="creative version changed; refresh")
    resolved = resolve_output_path(mcid, creative_id)
    if not resolved.get("ok"):
        raise HTTPException(status_code=404, detail="creative not found")
    return FileResponse(
        resolved["path"],
        media_type="video/mp4",
        headers={"Cache-Control": "private, max-age=300, no-transform"},
    )


@router.post("/creative-os/{creative_id}/feedback")
def customer_creative_os_feedback(
    creative_id: str,
    body: CreativeFeedbackIn,
    client_id: str = Depends(require_customer),
):
    """Customer approve / request-changes — same exact-hash authority as admin."""
    from app.marketing import clients_store
    from app.marketing.creative_os import flags as cflags
    from app.marketing.creative_os.service import approve_exact, request_changes
    from app.marketing.creative_os.store import get_record

    if not cflags.os_enabled():
        raise HTTPException(status_code=403, detail="creative review disabled")
    mcid = clients_store.canonical_client_id(client_id)
    got = get_record(mcid, creative_id)
    if not got.get("ok"):
        raise HTTPException(status_code=404, detail="creative nahi mila")
    rec = got["record"]
    current_revision = int(rec.get("approval_revision") or 0)
    if current_revision != body.expected_revision:
        raise HTTPException(status_code=409, detail="creative version changed; refresh")
    action = (body.action or "changes").strip().lower()
    if action not in {"approve", "changes"}:
        raise HTTPException(status_code=422, detail="invalid creative feedback action")
    if action == "approve":
        out = approve_exact(mcid, creative_id, actor="customer")
        if not out.get("ok"):
            raise HTTPException(status_code=409, detail=str(out.get("error") or "approval failed"))
        return out
    note = (body.text or "").strip()[:300] or "changes"
    out = request_changes(mcid, creative_id, note=note)
    if not out.get("ok"):
        raise HTTPException(status_code=409, detail=str(out.get("error") or "changes failed"))
    return out


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
