"""Customer dashboard data-assembly helpers — build KPIs/charts/leads/onboarding from
files (jsonl) or DB, masking + scoring utilities.

Extracted from app/api/customer_dashboard.py (2026-06-20 refactor). Re-exported by
customer_dashboard.py so external importers (admin_dashboard / customer_auth /
lead_scoring / speed_to_lead / prospector) keep working.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime

from app.api.customer_dashboard_models import (
    CallRow,
    Campaign,
    ChartsData,
    DashboardResponse,
    Kpis,
    LeadRow,
    OnboardingChecklist,
    OnboardingStep,
    SeriesPoint,
    TrialBanner,
)

logger = logging.getLogger(__name__)

# Restored in the 2026-06-20 godfile split (was lost when extracted from
# customer_dashboard.py) — without it _read_inquiries() silently returned [].
_INQUIRIES_FILE = os.path.join("data", "inquiries.jsonl")


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

    rec = client_rec or _client_record(client_id) or {}
    slug = str(rec.get("slug") or "").strip()
    socials = rec.get("socials") or {}

    # Retrieve tone
    tone = ""
    try:
        from app.marketing import brand_kit, clients_store

        # Brand marketing id pe keyed — alias/login id ko canonicalize karo.
        tone = str(
            (brand_kit.get_brand(clients_store.canonical_client_id(client_id)) or {}).get("tone")
            or ""
        ).strip()
    except Exception:
        pass

    steps = [
        OnboardingStep(
            id="login",
            label="Portal login set",
            done=client_has_login(client_id),
            hint="Admin se login email+password issue karvao",
        ),
        OnboardingStep(
            id="profile",
            label="Business Profile complete",
            done=bool(rec.get("business_name") and rec.get("phone") and rec.get("city")),
            hint="Business name, phone and city/address update karein",
        ),
        OnboardingStep(
            id="wizard_details",
            label="Services & Target Area set",
            done=bool(rec.get("services") and rec.get("target_area")),
            hint="Services details aur target areas update karein",
        ),
        OnboardingStep(
            id="socials",
            label="Social Accounts checklist complete",
            done=bool(socials.get("facebook") or socials.get("instagram") or socials.get("gbp")),
            hint="Social accounts connect checklist update karein",
        ),
        OnboardingStep(
            id="whatsapp",
            label="WhatsApp Details connected",
            done=bool(rec.get("whatsapp_phone")),
            hint="WhatsApp connectivity phone details fill karein",
        ),
        OnboardingStep(
            id="preferences",
            label="Brand Tone & Approvals set",
            done=bool(tone and rec.get("approval_preference")),
            hint="Brand voice tone aur approvals choice set karein",
        ),
        OnboardingStep(
            id="value",
            label="Day-1 Value generated",
            done=content_count > 0,
            hint="Day-1 calendar drafts auto-create ho chuki hain",
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


def _trial_banner(client_rec: dict | None, *, has_paid_plan: bool = False) -> TrialBanner | None:
    """Trial expiry nudge — day 5+ ya expired pe pay CTA."""
    from app.api.customer_dashboard_models import TrialBanner
    from app.marketing.packages import PACKAGES, get_starter_price_inr, trial_status

    try:
        if has_paid_plan:
            return None
        st = trial_status(client_rec)
        if not st.get("trial") and not st.get("expired"):
            return None
        days = int(st.get("days_left") or 0)
        expired = bool(st.get("expired"))
        show = expired or days <= 7
        starter = get_starter_price_inr()  # canonical ₹1,999 — packages.py single source
        for p in PACKAGES:
            if str(p.get("key") or "") == "starter":
                starter = int(
                    p.get("price_inr_month") or p.get("price_inr") or get_starter_price_inr()
                )
                break
        if expired:
            msg = (
                f"Aapka FREE trial khatam ho gaya — Starter ₹{starter:,}/mahina se "
                "phir se shuru karo. Neeche UPI se pay karo."
            )
        elif days <= 2:
            msg = (
                f"Trial {days} din me khatam — abhi pay karo taaki roz ka content "
                f"band na ho. Starter sirf ₹{starter:,}/mahina."
            )
        else:
            msg = (
                f"Trial me {days} din bache — pasand aaye to Starter ₹{starter:,}/mahina "
                "pe upgrade karo (UPI neeche)."
            )
        return TrialBanner(
            trial=bool(st.get("trial")),
            active=bool(st.get("active")),
            expired=expired,
            days_left=days,
            expires_at=st.get("expires_at"),
            show_pay_cta=show,
            starter_price_inr=starter,
            message=msg,
        )
    except Exception:
        return None


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
    plan = str((client_rec or {}).get("plan") or "").lower()
    has_paid = plan not in ("", "trial", "free")
    trial = _trial_banner(client_rec, has_paid_plan=has_paid)
    social_err = str((client_rec or {}).get("social_error") or "").strip() or None
    approval_banner = _approval_banner(client_id)
    return resp.model_copy(
        update={
            "client_id": client_id,
            "onboarding": onboarding,
            "trial_banner": trial,
            "approval_banner": approval_banner,
            "social_error": social_err,
        }
    )


def _approval_banner(client_id: str):
    """Return a bounded, PII-free customer nudge for pending approvals."""
    from app.api.customer_dashboard_models import ApprovalBanner

    try:
        from app.marketing import clients_store, content_approval

        # Approvals marketing id pe keyed hain — billing/login alias ko canonicalize
        # karo warna alias-login customer (Jiya) ko apne pending approvals nahi dikhte.
        count = len(content_approval.pending(clients_store.canonical_client_id(client_id)) or [])
    except Exception:
        count = 0
    if count <= 0:
        return ApprovalBanner()
    noun = "post" if count == 1 else "posts"
    return ApprovalBanner(
        show=True,
        count=count,
        urgency="high" if count >= 3 else "normal",
        message=f"Aapke {count} {noun} approval ka wait kar rahe hain — approve karte hi delivery aage badhegi.",
    )


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
    """clients_store se is client ka canonical marketing record.

    UPI-activated customers apni billing/login id (e.g. Jiya `d79d690f61b3`) se
    login karte hain, par marketing record marketing id (`jiya-makeover`) pe keyed
    hai — billing id us record ke `billing_client_ids` me carry hoti hai.
    `resolve_client` alias ko canonical record pe map karta; warna customer
    dashboard ko orphaned partial view (content/plan/onboarding sab khali) dikhta
    tha. Billing/invoice reads raw id use karte hain (yahan nahi). Kabhi raise nahi.
    """
    try:
        from app.marketing.clients_store import get_by_slug, resolve_client

        return resolve_client(client_id) or get_by_slug(client_id)
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
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(
                raw.split("+")[0].rstrip("Z") + ("Z" if raw.endswith("Z") else ""), fmt
            )
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
                id=str(r.get("id") or ""),
                status=tier,  # B4: default status = AI tier; overridden below if customer set one
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

    # B4: apply this client's OWN lead-status overrides (IDOR-safe: skip
    # overrides set by any other client_id). Source inquiries stay immutable.
    try:
        from app.platform.lead_overrides import read_overrides

        _ovr = read_overrides()
        if _ovr:
            for _ld in leads:
                _o = _ovr.get(_ld.id)
                if _o and str(_o.get("client_id") or "") == str(client_id) and _o.get("status"):
                    _ld.status = _o[
                        "status"
                    ]  # status only; score (tier) untouched so charts/filters stay valid
    except Exception:
        pass

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

    Client-scoped via meta_json.client_id (2026-07-02) — call events now carry
    client_id at the source (vobiz_stream.py call_finished, telephony_vobiz.py
    call_placed, public_site._auto_callback). Events logged BEFORE this fix have
    no client_id in meta and are correctly excluded (honest zero, not counted
    toward any client — the prior behaviour showed every customer the SAME
    platform-wide total under their own name, which this replaces).

    The client_id filter runs IN SQL (meta_json LIKE, matching log_event's
    json.dumps `"client_id": "..."` serialization) before the row limit, not
    after — a naive "fetch latest 2000 platform-wide, then filter in Python"
    would silently undercount a client's calls to 0 once platform-wide call
    volume outpaces the window. The `.limit()` here bounds THIS client's own
    rows, which realistically never approaches it. Python still re-checks the
    exact client_id post-parse (defense-in-depth against LIKE false-positives).
    Detail rows intentionally empty (this is a fallback-KPI count, not a log)."""
    total = 0
    today = 0
    if not client_id:
        return [], 0, 0
    try:
        import json as _json

        from app.models.agent_event import AgentEvent
        from app.models.base import get_db_session

        needle = f'"client_id": "{client_id}"'
        with get_db_session() as db:
            try:
                rows = (
                    db.query(AgentEvent.meta_json, AgentEvent.created_at)
                    .filter(AgentEvent.member == "swara")
                    .filter(
                        AgentEvent.action.in_(["call_placed", "call_finished", "auto_callback"])
                    )
                    .filter(AgentEvent.meta_json.contains(needle, autoescape=True))
                    .order_by(AgentEvent.created_at.desc())
                    .limit(5000)
                    .all()
                )
                today_date = datetime.utcnow().date()
                for meta_raw, created_at in rows:
                    try:
                        meta = _json.loads(meta_raw or "{}")
                    except Exception:
                        continue
                    if str(meta.get("client_id") or "") != client_id:
                        continue
                    total += 1
                    if created_at and created_at.date() == today_date:
                        today += 1
            except Exception:
                total = 0
    except Exception:
        total = 0
    # connected ~ all matched (no per-call status here); detail rows intentionally empty
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
                # Per-call AI qualification report (JSON text -> short readable line).
                _qtext = ""
                try:
                    import json as _json

                    _qd = c.qualification_data
                    _qd = (
                        _json.loads(_qd)
                        if isinstance(_qd, str) and _qd.strip()
                        else (_qd if isinstance(_qd, dict) else {})
                    )
                    if isinstance(_qd, dict) and _qd:
                        _qtext = " · ".join(f"{k}: {v}" for k, v in list(_qd.items())[:4])
                except Exception:
                    _qtext = ""
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
                        # Product-2 delivery: surface the AI value (was CallLog-only).
                        transcript=(c.transcription or "")[:4000],
                        summary=(c.summary or "")[:1500],
                        qualification=_qtext[:600],
                        sentiment=(c.sentiment or ""),
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
# Aapka Office — virtual-office aggregator (2026-06-28)                        #
# Plain-Hinglish "kya ho raha · AI team ne kya kiya · customer ko khud kya     #
# karna hai (+ automation-impact)" for the 3 customer dashboards. Reuses the   #
# onboarding / approvals / trial / inquiry builders above — NO new store, no   #
# LLM, never raises. Product-aware (marketing | voice | combo) so each         #
# dashboard shows the RIGHT tasks. Drives frontend "🏢 Aapka Office" block.    #
# --------------------------------------------------------------------------- #
def _rel_time(dt: datetime | None) -> str:
    """datetime -> chhota Hinglish relative time ('abhi' / 'N min pehle' / 'kal')."""
    if not dt:
        return ""
    try:
        secs = (datetime.utcnow() - dt).total_seconds()
    except Exception:
        return ""
    secs = max(secs, 0)
    if secs < 90:
        return "abhi"
    mins = secs / 60
    if mins < 60:
        return f"{int(mins)} min pehle"
    hrs = mins / 60
    if hrs < 24:
        return f"{int(hrs)} ghante pehle"
    days = hrs / 24
    if days < 2:
        return "kal"
    if days < 30:
        return f"{int(days)} din pehle"
    try:
        return dt.strftime("%d %b")
    except Exception:
        return ""


def _office_tasks(rec, product, onboarding, approvals_pending, trial, routing_set, hot_leads):
    """Manual-action list with automation-impact, product-tailored + prioritized.

    Har task: {id, icon, severity(high|medium|low), priority, title, why, impact,
    cta_label, cta_target(existing card id) }. Lower priority = top."""
    is_mkt = product in ("marketing", "combo")
    is_voice = product in ("voice", "combo")
    steps = {s.id: bool(s.done) for s in (onboarding.steps if onboarding else [])}

    def _done(sid: str) -> bool:
        return steps.get(sid, True)

    tasks: list[dict] = []

    # 0) Payment / trial — blocks ALL automation
    if trial and getattr(trial, "show_pay_cta", False):
        expired = bool(getattr(trial, "expired", False))
        tasks.append(
            {
                "id": "pay",
                "icon": "💳",
                "severity": "high",
                "priority": 0,
                "title": (
                    "Plan activate karo (UPI)"
                    if expired
                    else "Trial chal raha — abhi pay karke pakka karo"
                ),
                "why": (
                    "Trial khatam — roz ka automation ruk jayega"
                    if expired
                    else f"Trial me {int(getattr(trial, 'days_left', 0))} din bache"
                ),
                "impact": "content + calls + leads — sab chalu rahega",
                "cta_label": "Pay karo",
                "cta_target": "billingCard",
            }
        )

    # 1) Business profile (naam + phone) — sab products
    if not _done("profile"):
        tasks.append(
            {
                "id": "profile",
                "icon": "🏢",
                "severity": "high",
                "priority": 1,
                "title": "Business profile pura karo",
                "why": "AI ke paas aapka naam/phone/detail nahi",
                "impact": "sahi branding + lead pe turant contact",
                "cta_label": "Profile bharo",
                "cta_target": "onboardWrap",
            }
        )

    # 2) Website -> Knowledge Base (helps BOTH content + voice grounding)
    if not _done("setup"):
        tasks.append(
            {
                "id": "website",
                "icon": "🌐",
                "severity": "high",
                "priority": 2,
                "title": "Website / business detail do",
                "why": "AI ko aapka kaam abhi theek se samajh nahi",
                "impact": "behtar content + accurate jawab (calls + chat)",
                "cta_label": "Website do",
                "cta_target": "onboardWrap",
            }
        )

    # 3) Mini-site live — lead capture (marketing/combo)
    if is_mkt and not _done("minisite"):
        tasks.append(
            {
                "id": "minisite",
                "icon": "🔗",
                "severity": "medium",
                "priority": 3,
                "title": "Mini-site live karo",
                "why": "Aapka lead-capture page abhi band hai",
                "impact": "website visitors se direct enquiries",
                "cta_label": "Live karo",
                "cta_target": "webToolsCard",
            }
        )

    # 4) Pending content approvals (marketing/combo)
    if is_mkt and approvals_pending > 0:
        tasks.append(
            {
                "id": "approvals",
                "icon": "✅",
                "severity": "high",
                "priority": 1,
                "title": f"{approvals_pending} post approve karo",
                "why": "Posts taiyaar hain par approval ke bina ruke hain",
                "impact": "approve karte hi auto-publish ho jayenge",
                "cta_label": "Dekho + approve",
                "cta_target": "approvalCard",
            }
        )

    # 5) Call routing (voice/combo) — kis team-member ko lead jaaye
    if is_voice and not routing_set:
        tasks.append(
            {
                "id": "routing",
                "icon": "👥",
                "severity": "medium",
                "priority": 3,
                "title": "Call routing set karo (team numbers)",
                "why": "Lead aane pe kise bheje — abhi set nahi",
                "impact": "koi lead miss nahi hoga (round-robin)",
                "cta_label": "Set karo",
                "cta_target": "routingCard",
            }
        )

    # 6) Hot leads waiting (voice/combo) — abhi contact karo
    if is_voice and hot_leads > 0:
        tasks.append(
            {
                "id": "hotleads",
                "icon": "🔥",
                "severity": "high",
                "priority": 2,
                "title": f"{hot_leads} hot lead{'s' if hot_leads > 1 else ''} — jaldi call/WhatsApp karo",
                "why": "Inka intent high hai, der = customer chala jayega",
                "impact": "fast contact = zyada deals close",
                "cta_label": "Leads dekho",
                "cta_target": "leadsCard",
            }
        )

    # 7) First test enquiry (brand-new, low priority nudge)
    if not _done("leads"):
        tasks.append(
            {
                "id": "testlead",
                "icon": "🧪",
                "severity": "low",
                "priority": 5,
                "title": "Ek test enquiry bhej kar dekho",
                "why": "Abhi tak koi lead/enquiry nahi aayi",
                "impact": "poora flow (lead -> alert -> follow-up) confirm",
                "cta_label": "Kaise?",
                "cta_target": "webToolsCard",
            }
        )

    _sev = {"high": 0, "medium": 1, "low": 2}
    tasks.sort(key=lambda t: (t.get("priority", 9), _sev.get(t.get("severity"), 9)))
    return tasks


def _office_activity(client_id: str, rec: dict | None, limit: int = 12) -> list[dict]:
    """Derived "AI team ne aapke liye kya kiya" feed — inquiries + content posts,
    real per-client data, chronological. No agent_events client-scoping needed."""
    items: list[dict] = []
    try:
        for r in _inquiries_for_client(client_id, rec)[:40]:
            dt = _parse_dt(r)
            nm = str(r.get("name") or "Koi").strip()[:40] or "Koi"
            city = str(r.get("city") or "").strip()
            loc = f" ({city})" if city else ""
            tier = _lead_score_from_inquiry(r)
            items.append(
                {
                    "_dt": dt,
                    "when": _rel_time(dt),
                    "who": "📥 Mini-site",
                    "did": f"Nayi enquiry: {nm}{loc}" + (" — 🔥 hot" if tier == "Hot" else ""),
                    "status": "ok",
                }
            )
    except Exception:
        pass
    try:
        from app.marketing.auto_content import list_queue

        rid = str((rec or {}).get("id") or client_id or "").strip()
        if rid:
            for q in list_queue(rid, limit=40) or []:
                if not isinstance(q, dict):
                    continue
                dt = _parse_dt(q)
                st = str(q.get("status") or "").lower()
                if st in ("posted", "published"):
                    verb = "publish hua"
                elif st in ("approved",):
                    verb = "approve hua"
                elif st in ("pending", "draft", "awaiting"):
                    verb = "approval ka wait"
                else:
                    verb = "taiyaar"
                ch = str(q.get("channel") or q.get("platform") or "social").strip() or "social"
                items.append(
                    {
                        "_dt": dt,
                        "when": _rel_time(dt),
                        "who": "✍️ Isha",
                        "did": f"{ch.title()} post {verb}",
                        "status": "ok",
                    }
                )
    except Exception:
        pass
    items.sort(key=lambda x: x.get("_dt") or datetime.min, reverse=True)
    for it in items:
        it.pop("_dt", None)
    return items[:limit]


def _office_call_stats(client_id: str) -> tuple[int, int]:
    """Client-scoped (calls_completed, bookings) for the office summary.

    Deliberately does NOT reuse ``_calls_from_events`` — that helper counts ALL
    platform "swara" call events (call events don't carry client_id in meta_json
    today), which would show every customer the same platform-wide number under
    their own name. Uses CallLog.client_id (properly scoped, same source as the
    DB-backed dashboard builder) instead. Never raises — (0, 0) on any failure,
    including "no DB rows for this client" (honest zero, not someone else's data)."""
    try:
        from app.models.base import get_db_session
        from app.models.call_log import CallLog
        from app.models.lead import Lead, LeadStatus

        with get_db_session() as db:
            connected = (
                db.query(CallLog)
                .filter(CallLog.client_id == client_id)
                .filter(CallLog.duration_seconds > 0)
                .count()
            )
            bookings = (
                db.query(Lead)
                .filter(Lead.assigned_to == client_id)
                .filter(Lead.status == LeadStatus.APPOINTMENT)
                .count()
            )
            return int(connected), int(bookings)
    except Exception:
        return 0, 0


def _build_office(client_id: str) -> dict:
    """Assemble the full "Aapka Office" payload (never raises). Product-aware."""
    try:
        rec = _client_record(client_id)
        try:
            from app.marketing.clients_store import resolve_product

            product = resolve_product(rec or {})
        except Exception:
            product = "marketing"

        inquiries = _inquiries_for_client(client_id, rec)
        leads_count = len(inquiries)
        content_count = _content_posts_count(client_id, rec)
        onboarding = _build_onboarding_checklist(client_id, rec, leads_count, content_count)

        approvals_pending = 0
        try:
            from app.marketing import content_approval

            # `rec` ab canonical marketing record hai (alias-aware _client_record);
            # approvals usi marketing id pe keyed hain, raw login id pe nahi.
            _mcid = str((rec or {}).get("id") or client_id or "").strip()
            approvals_pending = len(content_approval.pending(_mcid) or [])
        except Exception:
            approvals_pending = 0

        plan = str((rec or {}).get("plan") or "").lower()
        has_paid = plan not in ("", "trial", "free")
        trial = _trial_banner(rec, has_paid_plan=has_paid)

        routing_set = False
        try:
            from app.platform import lead_distribution as ld

            cfg = ld.get_config(client_id) or {}
            routing_set = bool(cfg.get("members"))
        except Exception:
            routing_set = False

        hot_leads = sum(1 for r in inquiries if _lead_score_from_inquiry(r) == "Hot")
        calls_completed, bookings = _office_call_stats(client_id)

        tasks = _office_tasks(
            rec, product, onboarding, approvals_pending, trial, routing_set, hot_leads
        )
        activity = _office_activity(client_id, rec)
        high = [t for t in tasks if t.get("severity") == "high"]

        if not tasks:
            headline = "✅ Sab set hai — aapki AI team kaam pe lagi hai"
        elif high:
            headline = f"⚠️ {len(high)} zaroori kaam aapke taraf — neeche dekho"
        else:
            headline = f"📋 {len(tasks)} chhota kaam baaki — baaki AI team sambhaal rahi"

        next_best_action = (
            {
                "title": tasks[0]["title"],
                "why": tasks[0]["why"],
                "cta_target": tasks[0]["cta_target"],
            }
            if tasks
            else {
                "title": "Abhi kuch nahi karna",
                "why": "Sab set hai — AI team kaam pe lagi hai",
                "cta_target": "",
            }
        )

        from app.platform.office_schema import UNITY_OFFICE_SCHEMA_VERSION

        return {
            "ok": True,
            "schema_version": UNITY_OFFICE_SCHEMA_VERSION,
            "enabled": True,
            "product": product,
            "headline": headline,
            "next_best_action": next_best_action,
            "your_tasks": tasks,
            "activity": activity,
            "summary": {
                "posts_ready": content_count,
                "approvals_pending": approvals_pending,
                "new_leads": leads_count,
                "hot_leads": hot_leads,
                "calls_completed": calls_completed,
                "bookings": bookings,
                "onboarding_pct": float(getattr(onboarding, "pct", 0) or 0),
            },
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        }
    except Exception as e:
        logger.debug("customer office build failed: %s", e)
        from app.platform.office_schema import UNITY_OFFICE_SCHEMA_VERSION

        return {
            "ok": False,
            "schema_version": UNITY_OFFICE_SCHEMA_VERSION,
            "enabled": True,
            "product": "marketing",
            "headline": "",
            "next_best_action": None,
            "your_tasks": [],
            "activity": [],
            "summary": {},
        }
