"""
AI Staff Team — company-style agent roster + activity log + status.
====================================================================

User vision: "1 company me jaise staff hota hai waise agents" — har AI agent
ek named EMPLOYEE hai jiska role, duties aur kaam ka record clear ho, aur sab
admin dashboard pe live dikhe (kaun kya kar raha, kitna productive).

Yeh module deta hai:
  - STAFF registry: fixed company roster (name, role, duties, schedule)
  - log_event(member, action, detail, status, meta): har kaam DB me record
    (agent_events table — import-safe, DB na ho to silently skip)
  - team_status(): per-member live state (working/idle/offline), last activity,
    aaj ke kaam ke counts — dashboard API isi se बनती hai
  - recent_events(): live activity feed

Ye sab telephony / web-call / supervisor / QA / trainer / ops flows se call
hota hai. KABHI raise nahi karta — voice pipeline kabhi team-logging ki wajah
se nahi girni chahiye.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# India timezone for "today" boundaries (dashboard counts).
_IST = timezone(timedelta(hours=5, minutes=30))


def _call_transcripts_dir() -> str:
    """Call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return str(call_transcripts_dir())


# --------------------------------------------------------------------------- #
# Company roster — the AI staff. Fixed, code-defined (roles change via code).
# --------------------------------------------------------------------------- #
STAFF: dict[str, dict[str, Any]] = {
    "manager": {
        "product": "platform",
        "name": "Boss",
        "emoji": "🧑‍💼",
        "title": "Manager (Supervisor)",
        "duties": "Kaam baantna — data/leads agents ko route karna (LangGraph), team coordination",
        "schedule": "On-demand (har /api/agents/run pe)",
    },
    "swara": {
        "product": "voice",
        "name": "Swara",
        "emoji": "📞",
        "title": "Telecaller",
        "duties": "End-customers ko call karna (phone + web demo), niche scripts se qualify karna, objections handle karna",
        "schedule": "On-demand (calls/demos)",
    },
    "ananya": {
        "product": "voice",
        "name": "Ananya",
        "emoji": "📅",
        "title": "Appointment Booker",
        "duties": "Har niche ke end-customers ke liye appointment, site-visit ya demo slot book karna — calendar + reminders",
        "schedule": "On-demand (booking campaigns / callbacks)",
    },
    "riya": {
        "product": "voice",
        "name": "Riya",
        "emoji": "🛎️",
        "title": "AI Receptionist",
        "duties": "Inbound customer calls — greeting, department route, message lena, appointment book karna (sales pitch nahi)",
        "schedule": "On-demand (inbound / mini-site widget)",
    },
    "dev": {
        "product": "marketing",
        "name": "Dev",
        "emoji": "📚",
        "title": "Data Analyst",
        "duties": "Client business profile + niche knowledge KB me seed karna, RAG grounding maintain karna",
        "schedule": "Har naye client pe auto",
    },
    "rohan": {
        "product": "marketing",
        "name": "Rohan",
        "emoji": "🎯",
        "title": "Leads Manager",
        "duties": "Outreach plan banana, lead qualification criteria set karna, campaigns ke liye targeting",
        "schedule": "On-demand (campaigns)",
    },
    "arjun": {
        "product": "voice",
        "name": "Arjun",
        "emoji": "🧪",
        "title": "QA Engineer",
        "duties": "Voice agent ko scripted conversations se test karna, bugs (double/repeat/slow/long) pakad ke report karna",
        "schedule": "Roz raat 2:30 + on-demand",
    },
    "meera": {
        "product": "voice",
        "name": "Meera",
        "emoji": "🎓",
        "title": "Trainer",
        "duties": "Call transcripts padh ke quality analysis (STT failures, repeats, latency), tuning suggestions nikalna",
        "schedule": "Roz raat 3:00 + on-demand",
    },
    "lekha": {
        "product": "voice",
        "name": "Lekha",
        "emoji": "📊",
        "title": "Call Analytics Lead",
        "duties": "Call-center KPIs — web+phone calls se duration, qualified-rate, booking-rate, reply-latency p50/p95, dead-air/repeat ratio nikal ke trend + admin digest (app/voice_agent/call_analytics.py)",
        "schedule": "Roz subah + on-demand (/api/admin/web-calls/kpis)",
    },
    "raksha": {
        "product": "voice",
        "name": "Raksha",
        "emoji": "🆘",
        "title": "Human Escalation Manager",
        "duties": "Jab AI unsure/confused ho ya customer gussa/insaan maange — call human ko route karna (app/telephony/call_transfer.py, gated CALL_TRANSFER) + context handover; escalation log + handback",
        "schedule": "On-demand (live calls)",
    },
    "kavya": {
        "product": "platform",
        "name": "Kavya",
        "emoji": "🛡️",
        "title": "Ops Monitor",
        "duties": "System health (service, AI providers, DB, disk), telephony balance/trunk status pe nazar",
        "schedule": "Har ghante + on-demand",
    },
    "hermes": {
        "product": "platform",
        "name": "Hermes",
        "emoji": "🛰️",
        "title": "Infrastructure Handler",
        "duties": "Poore infra ka scan — app readiness (db+redis), disk/memory, dead-man jobs, queue backlog, LLM chain, backup freshness → 0-100 score + Hinglish fix-actions; critical pe email alert (Kavya/Tara ke engines REUSE — aggregator/diagnoser)",
        "schedule": "Har ghante (watchdog, gated INFRA_HANDLER) + pulse rotation",
    },
    "isha": {
        "product": "marketing",
        "name": "Isha",
        "emoji": "📣",
        "title": "Marketing Executive",
        "duties": "Clients ke liye AI social posts (FB/Insta captions), Google Business Profile tips, festival/offer content",
        "schedule": "On-demand (marketing)",
    },
    "tara": {
        "product": "voice",
        "name": "Tara",
        "emoji": "🎙️",
        "title": "Voice Infra Ops",
        "duties": "Telephony readiness (Vobiz auth, caller-ID, webhooks, DND, TTS/STT/LLM chain) har ghante verify karna — calling launch ke liye system hamesha taiyaar rahe",
        "schedule": "Har ghante (watchdog ke saath)",
    },
    "nikhil": {
        "product": "platform",
        "name": "Nikhil",
        "emoji": "💰",
        "title": "Revenue Ops",
        "duties": "Dunning recovery, lifecycle nurture funnel, client churn-risk aur MRR digest pe nazar — paisa leak na ho",
        "schedule": "Roz (digest/content jobs ke saath)",
    },
    "vikram": {
        "product": "platform",
        "name": "Vikram",
        "emoji": "🛠️",
        "title": "Code Upgrader",
        "duties": "Observability signals (LLM errors, failing jobs, weak actions) se code-upgrade proposals banana — safe skills auto, core code Sumit ke approve pe (hybrid autonomy)",
        "schedule": "Har ghante (watchdog ke saath, gated CODE_UPGRADER)",
    },
    "guru": {
        "product": "platform",
        "name": "Guru",
        "emoji": "📚",
        "title": "Skill Trainer",
        "duties": "35+ project skills ko agents ke runtime context + KB me rakhna, naye agent-authored skills curate karna — LLM/team seekhte rahein. Knowledge/Memory steward role bhi (Mem0 hygiene + agent_memory drift detect)",
        "schedule": "Roz (trainer job ke saath, gated SKILL_PACK)",
    },
    # ----- F.5: 3 engineer agents (billionaire-audit Section H, KPI-bound) ----- #
    # Audit verdict: "add a specialized engineer agent only if it creates
    # measurable operational leverage your current roster does not."
    # These three pass that bar; everything else folded/deferred.
    "pranav": {
        "product": "platform",
        "name": "Pranav",
        "emoji": "🔧",
        "title": "SRE / Reliability",
        "duties": "DR drills, backup-restore integrity, capacity headroom, SLO/error-budget tracking. KPIs: backup_pass_rate, mttr_seconds, capacity_headroom_pct. Existing Kavya does liveness; Pranav owns SURVIVABILITY on a SPOF VPS.",
        "schedule": "Har ghante (gated SRE_AGENT) + daily DR-readiness summary",
    },
    "vidya": {
        "product": "platform",
        "name": "Vidya",
        "emoji": "💹",
        "title": "FinOps / Cost",
        "duties": "Per-tenant unit economics (cost-per-customer once LiteLLM virtual keys live), margin-negative niche flag, LLM spend vs revenue trend. KPI: gross_margin_per_tenant. Existing Nikhil does revenue collection; Vidya defends margin.",
        "schedule": "Roz (daily margin digest, gated FINOPS_AGENT)",
    },
    "arnav": {
        "product": "platform",
        "name": "Arnav",
        "emoji": "🛡️",
        "title": "Security / Compliance",
        "duties": "DPDP + TRAI posture, secret-rotation reminders, CVE triage → patch proposal, DSAR handling. KPI: compliance_posture_score. Spreads across pre-commit/Trivy today; Arnav owns it.",
        "schedule": "Daily (gated SECURITY_AGENT) + on-demand posture report",
    },
    # ----- council 2026-06-25: 3 new engineer agents (genuinely-uncovered loops) ----- #
    "kabir": {
        "product": "platform",
        "name": "Kabir",
        "emoji": "🗄️",
        "title": "DB Reliability Engineer",
        "duties": "Postgres query-health — slow-query patterns (pg_stat_statements), unused/bloating indexes, connection-pool pressure, DB size trend. KPI: db_reliability_score. Fills Pranav's blind spot (he owns backup/heartbeat/capacity, NOT query health). Read-only pg-catalog checks.",
        "schedule": "Daily 10:00 IST (gated DBRE_AGENT)",
    },
    "diya": {
        "product": "platform",
        "name": "Diya",
        "emoji": "🧹",
        "title": "Data-Integrity Engineer",
        "duties": "Lead/CRM data quality — duplicate phone/email detection, missing-contact leads, prospect-store integrity. KPI: data_integrity_score. Revenue-adjacent: clean leads = better outreach + accurate CRM. REPORT-only (dedupe stays human-approved).",
        "schedule": "Daily 10:30 IST (gated DATA_INTEGRITY_AGENT)",
    },
    "aryan": {
        "product": "platform",
        "name": "Aryan",
        "emoji": "📦",
        "title": "Dependency / Supply-chain Engineer",
        "duties": "Package vulnerability audit via pip-audit (read-only), lock-file pinning hygiene, CVE → upgrade PROPOSALS. KPI: supply_chain_score. Distinct from Arnav (secrets/compliance posture); Aryan owns dependency CVEs. Never auto-upgrades.",
        "schedule": "Weekly Sun 04:30 IST (gated DEPS_AGENT)",
    },
    # ----- council 2026-06-26: MCP Engineer (3-layer MCP surface owner) ----- #
    "arya": {
        "product": "platform",
        "name": "Arya",
        "emoji": "🔌",
        "title": "MCP Engineer",
        "duties": (
            "Three-layer MCP surface — (1) /mcp expose via fastapi-mcp (admin tools, "
            "must be auth-gated), (2) /api/mcp-product/v1/* metered B2B routes, "
            "(3) A2A Agent Card (/.well-known/agent.json). Hourly health-pulse: "
            "dependency check, gate-presence audit, key quota pressure, 90d rotation "
            "watch, /mcp auth-failure spike detection. ntfy alert on critical signals. "
            "Cross-talks to Arnav (security) and Hermes (infra) but owns MCP-specific KPIs."
        ),
        "schedule": "Hourly (gated MCP_ENGINEER) + on-demand /api/platform/mcp/health",
    },
    "ravi": {
        "product": "marketing",
        "name": "Ravi",
        "emoji": "🌐",
        "title": "SEO Scout",
        "duties": "Programmatic SEO pages (niche×city), IndexNow sitemap ping, rank-tracker sweep — organic inbound badhao",
        "schedule": "Roz blog ke saath + Monday SEO batch",
    },
    "neha": {
        "product": "marketing",
        "name": "Neha",
        "emoji": "♻️",
        "title": "Pipeline Ops",
        "duties": "Lead rescore, hot-lead surfacing Rohan ke liye, journey rules seed — pipeline fresh rakho",
        "schedule": "Roz 11:00 IST pipeline job",
    },
    "kiran": {
        "product": "marketing",
        "name": "Kiran",
        "emoji": "📊",
        "title": "Campaign Optimizer",
        "duties": "Har 100 interactions pe campaign analyze karo — winning openings, objections, A/B proposals; eval_gate ke baad hi promote",
        "schedule": "Weekly + threshold (gated CAMPAIGN_OPTIMIZER)",
    },
    # 2026-07-01: audit found these 2 engines already run real automation but had
    # ZERO staff attribution — invisible on /app/team + agent_events. Named + wired
    # (app/platform/crm_sync.py, app/social_engine/engine.py) so the office/team view
    # actually reflects what's running, not just what has a persona.
    "priya": {
        "product": "marketing",
        "name": "Priya",
        "emoji": "🔗",
        "title": "CRM Sync Specialist",
        "duties": "Qualified leads client ke apne Zoho/HubSpot CRM me auto-push (gated CRM_SYNC) — 'apna CRM chhodna nahi padega'",
        "schedule": "On-demand (har qualified lead pe, jab client ne CRM connect kiya ho)",
    },
    "zara": {
        "product": "marketing",
        "name": "Zara",
        "emoji": "📱",
        "title": "Social Media Manager",
        "duties": "Approved content queue drain karke per-client social channels (Telegram/Postiz/Meta) pe publish karna (gated SOCIAL_ENGINE)",
        "schedule": "Queue-driven (jab bhi approved content publish ke liye ready ho)",
    },
    # 2026-07-01: 2nd audit pass ("2 more workers") — same rule, real engines only.
    # cadence.py + journeys.py already run scheduled/hook-driven automation (wired
    # into inquiry/booking/reply-triage/pipeline-ops) with zero staff attribution.
    "anika": {
        "product": "marketing",
        "name": "Anika",
        "emoji": "🔁",
        "title": "Cadence Manager",
        "duties": "Enrolled leads ko per-day omnichannel sequence (email/SMS/WhatsApp/LinkedIn draft) me aage badhana (gated CADENCE_ENGINE)",
        "schedule": "Roz scheduled (team_scheduler.py cadence.run_due())",
    },
    "ira": {
        "product": "marketing",
        "name": "Ira",
        "emoji": "🧩",
        "title": "Journey Automation Manager",
        "duties": "Event-trigger rules (inquiry/booking/reply/pipeline hooks) → matching journey ke actions/drafts chalana (gated JOURNEY_ENGINE)",
        "schedule": "Event-driven (jab bhi koi wired hook trigger fire kare)",
    },
}


def staff_for_product(product: str) -> dict[str, dict[str, Any]]:
    """ADR-009 two-product split: dono products ke AI agents ALAG.

    product='marketing' -> marketing staff + shared 'platform' staff;
    product='voice' -> voice staff + shared; aur kuch bhi -> poora roster.
    """
    p = (product or "").strip().lower()
    if p not in ("marketing", "voice"):
        return dict(STAFF)
    return {k: v for k, v in STAFF.items() if v.get("product") in (p, "platform")}


# --------------------------------------------------------------------------- #
# Enterprise Persona Registry (ADR-184, 2026-08-21)
# Har staff member ka UNIQUE system prompt — sales-focused, distinct personality.
# team.py STAFF = metadata (name/emoji/duties/schedule)
# agent_personas.py STAFF_PERSONAS = LLM personality (tone/expertise/system_prompt)
# get_staff_persona_prompt() = merged dict with persona attached
# --------------------------------------------------------------------------- #
def get_staff_persona_prompt(staff_id: str, **kwargs) -> str:
    """Staff member ka unique enterprise-grade system prompt.

    Args:
        staff_id: STAFF key ("swara", "manager", "arjun", ...)
        **kwargs: client_name, niche (dynamic insertion placeholders)

    Returns:
        Full system prompt string with that member's distinct personality.
        Falls back to generic voice prompt if persona not found.
    """
    try:
        from app.platform.agent_personas import build_staff_system_prompt

        prompt = build_staff_system_prompt(staff_id, **kwargs)
        if prompt and prompt != "Staff member not found.":
            return prompt
    except Exception:
        pass
    # Fallback: generic voice prompt
    return (
        f"Tum ek professional AI agent ho. Client: {kwargs.get('client_name', 'our company')}. "
        f"Niche: {kwargs.get('niche', 'general')}. "
        "Reply chhota rakho, natural Hinglish me baat karo, sales-focused raho."
    )


def staff_personas_summary() -> list[dict[str, Any]]:
    """Saare staff members ka persona summary (for dashboard/admin display).

    Returns list of dicts with: id, name, emoji, title, tone, expertise,
    sales_motivation, product, duties.
    """
    try:
        from app.platform.agent_personas import STAFF_PERSONAS

        result = []
        for key, info in STAFF.items():
            persona = STAFF_PERSONAS.get(key, {})
            result.append(
                {
                    "id": key,
                    "name": info.get("name", key.title()),
                    "emoji": info.get("emoji", "🤖"),
                    "title": persona.get("title", info.get("title", "")),
                    "product": info.get("product", "platform"),
                    "tone": persona.get("tone", ""),
                    "expertise": persona.get("expertise", []),
                    "sales_motivation": persona.get("sales_motivation", ""),
                    "duties": info.get("duties", ""),
                    "has_persona": bool(persona),
                }
            )
        return result
    except Exception:
        # Fallback: just STAFF metadata without personas
        return [
            {
                "id": key,
                "name": info.get("name", key.title()),
                "emoji": info.get("emoji", "🤖"),
                "title": info.get("title", ""),
                "product": info.get("product", "platform"),
                "has_persona": False,
                "duties": info.get("duties", ""),
            }
            for key, info in STAFF.items()
        ]


# Status windows (realism): "working" = abhi-abhi active; "active" = aaj kaam kiya
# (resting); "offline" = aaj kuch nahi. Pehle 2-min working/20-min offline tha →
# din me kaam karne wale bhi grey "idle" dikhte the. Ab schedule-cycles reflect hote.
_WORKING_AFTER_MIN = 20  # is window me event = abhi kaam kar raha (green pulse)
_ACTIVE_TODAY_MIN = 16 * 60  # aaj-bhar active mana (blue), warna offline (grey)
_IDLE_AFTER_MIN = _ACTIVE_TODAY_MIN  # backward-compat alias


# --------------------------------------------------------------------------- #
# Event logging (DB: agent_events; import-safe + never-raise)
# --------------------------------------------------------------------------- #
def _db():
    """Sync Session banao (ya None) — base ke lazy engine/_SessionLocal se."""
    try:
        from app.models import base as _b

        _b._get_sync_engine()
        if _b._SessionLocal is None:
            return None
        return _b._SessionLocal()
    except Exception:
        return None


def log_event(
    member: str,
    action: str,
    detail: str = "",
    status: str = "ok",
    meta: dict[str, Any] | None = None,
) -> None:
    """Staff member ka ek kaam record karo. Sync, fast, kabhi raise nahi karta.

    member: STAFF key ("swara", "arjun", ...) — unknown bhi chalega (log hota).
    action: chhota verb ("call_placed", "qa_run", "kb_seeded", ...).
    detail: 1-line human summary (dashboard feed me dikhta hai).
    status: ok | warn | error.
    """
    ev_id = str(uuid.uuid4())
    try:
        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            return
        try:
            ev = AgentEvent(
                id=ev_id,
                member=(member or "system")[:40],
                action=(action or "event")[:60],
                detail=(detail or "")[:500],
                status=(status or "ok")[:10],
                meta_json=json.dumps(meta or {}, ensure_ascii=False, default=str)[:2000],
                created_at=datetime.utcnow(),
            )
            db.add(ev)
            db.commit()
        finally:
            db.close()
    except Exception as e:  # NEVER break the caller (voice pipeline etc.)
        logger.debug(f"[team] log_event skipped: {e}")

    # Real-time SSE broadcast — Redis publish (non-blocking, fail-open)
    try:
        import asyncio
        import threading

        event_payload = {
            "id": ev_id,
            "member": (member or "system")[:40],
            "action": (action or "event")[:60],
            "detail": (detail or "")[:300],
            "status": (status or "ok")[:10],
            "at": datetime.utcnow().isoformat(),
        }

        async def _pub() -> None:
            from app.api.events import publish_to_redis

            await publish_to_redis(event_payload)

        def _publish_in_isolated_loop() -> None:
            try:
                asyncio.run(_pub())
            except Exception:
                pass

        # Do not attach Redis I/O to the caller's loop: scheduled jobs and tests
        # may close that loop immediately after log_event returns. A daemon
        # thread gives the short-lived Redis client its own clean loop and keeps
        # the sync logging contract non-blocking/fail-open.
        threading.Thread(
            target=_publish_in_isolated_loop,
            name="team-event-publish",
            daemon=True,
        ).start()
    except Exception:
        pass

    # Obsidian second-brain — throttled append to Agents/{member}.md (INERT if OBSIDIAN_SYNC unset).
    try:
        from app.platform import obsidian_sync as _obs

        entry = (
            f"{action}"
            + (f" — {detail[:120]}" if detail else "")
            + (f" [{status}]" if status != "ok" else "")
        )
        _obs.append_note(
            "Agents",
            (member or "system").capitalize(),
            entry,
            member=member or "system",
            tags=["agent"],
        )
    except Exception:
        pass


def recent_events(
    limit: int = 60, member: str | None = None, hours: int | None = None
) -> list[dict[str, Any]]:
    """Latest activity feed (newest first) — dashboard ke liye dicts.

    `hours` set ho to sirf pichhle N ghante ke events (hourly timeline +
    "last hour dispatches" jaise callers ke liye). Bigger cap jab hours-window.
    """
    try:
        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            return []
        try:
            q = db.query(AgentEvent).order_by(AgentEvent.created_at.desc())
            if member:
                q = q.filter(AgentEvent.member == member)
            if hours:
                cutoff = datetime.utcnow() - timedelta(hours=max(1, min(int(hours), 168)))
                q = q.filter(AgentEvent.created_at >= cutoff)
            cap = 2000 if hours else 300
            rows = q.limit(max(1, min(int(limit), cap))).all()
            return [_ev_dict(r) for r in rows]
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[team] recent_events failed: {e}")
        return []


def _ev_dict(r: Any) -> dict[str, Any]:
    member = getattr(r, "member", "") or "system"
    info = STAFF.get(member, {})
    try:
        meta = json.loads(getattr(r, "meta_json", "") or "{}")
    except Exception:
        meta = {}
    created = getattr(r, "created_at", None)
    return {
        "id": getattr(r, "id", ""),
        "member": member,
        "name": info.get("name", member.title()),
        "emoji": info.get("emoji", "🤖"),
        "action": getattr(r, "action", ""),
        "detail": getattr(r, "detail", ""),
        "status": getattr(r, "status", "ok"),
        "meta": meta,
        "at": (created.replace(tzinfo=timezone.utc).isoformat() if created else None),
    }


def stats(member: str | None = None, days: int = 7) -> dict[str, Any]:
    """Per-agent KPI aggregate over last N days — success-rate + last-run, taaki
    operator dekh sake kaunsa agent DEGRADE ho raha (recent_events = raw feed; yeh
    = rollup). SQL GROUP BY (member,status); window-cap 90d. KABHI raise nahi —
    failure pe empty. Observability-only, koi side-effect nahi."""
    out: dict[str, Any] = {"window_days": int(days), "agents": [], "overall": {}}
    try:
        from sqlalchemy import func

        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            return out
        try:
            cutoff = datetime.utcnow() - timedelta(days=max(1, min(int(days), 90)))
            q = db.query(
                AgentEvent.member,
                AgentEvent.status,
                func.count(AgentEvent.id),
                func.max(AgentEvent.created_at),
            ).filter(AgentEvent.created_at >= cutoff)
            if member:
                q = q.filter(AgentEvent.member == member)
            q = q.group_by(AgentEvent.member, AgentEvent.status)

            agg: dict[str, dict[str, Any]] = {}
            for mem, status, cnt, last in q.all():
                mem = mem or "system"
                rec = agg.setdefault(
                    mem, {"total": 0, "ok": 0, "warn": 0, "error": 0, "last": None}
                )
                n = int(cnt or 0)
                rec["total"] += n
                key = (status or "ok").strip().lower()
                if key == "ok":
                    rec["ok"] += n
                elif key in ("warn", "warning"):
                    rec["warn"] += n
                else:
                    rec["error"] += n
                if last and (rec["last"] is None or last > rec["last"]):
                    rec["last"] = last

            agents = []
            t_total = t_ok = 0
            for mem, rec in sorted(agg.items()):
                tot = rec["total"] or 1
                info = STAFF.get(mem, {})
                last = rec["last"]
                agents.append(
                    {
                        "member": mem,
                        "name": info.get("name", mem.title()),
                        "emoji": info.get("emoji", "🤖"),
                        "total": rec["total"],
                        "ok": rec["ok"],
                        "warn": rec["warn"],
                        "error": rec["error"],
                        "success_rate": round(rec["ok"] / tot, 3),
                        "last_run": (
                            last.replace(tzinfo=timezone.utc).isoformat() if last else None
                        ),
                    }
                )
                t_total += rec["total"]
                t_ok += rec["ok"]
            out["agents"] = agents
            out["overall"] = {
                "total": t_total,
                "ok": t_ok,
                "success_rate": round(t_ok / (t_total or 1), 3),
                "agent_count": len(agents),
            }
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[team] stats failed: {e}")
    return out


# --------------------------------------------------------------------------- #
# Team status (dashboard ka main payload)
# --------------------------------------------------------------------------- #
def _latest_events_per_member(db, AgentEvent, members: list[str]) -> list[Any]:
    """Latest AgentEvent row for EACH member in ``members`` — in ONE query.

    Replaces a `for m in members: query(...).first()` loop that was a textbook
    N+1 (Sentry PYTHON-S). Uses `row_number() OVER (PARTITION BY member ORDER BY
    created_at DESC)`, supported by Postgres (prod) and SQLite >= 3.25 (tests).

    Bounded by construction: returns at most one row per requested member, so it
    cannot blow up on a member with a long event history — which is why this is
    a window function and not "fetch all rows for these members and group in
    Python".

    Falls back to the original per-member loop if the window path raises (old
    SQLAlchemy/driver quirks), so the caller's behaviour is identical either
    way. Never raises: returns [] if even the fallback fails.
    """
    if not members:
        return []
    try:
        from sqlalchemy import func, select
        from sqlalchemy.orm import aliased

        rn = (
            func.row_number()
            .over(
                partition_by=AgentEvent.member,
                order_by=AgentEvent.created_at.desc(),
            )
            .label("_rn")
        )
        sub = select(AgentEvent, rn).where(AgentEvent.member.in_(members)).subquery()
        ev = aliased(AgentEvent, sub)
        return list(db.query(ev).filter(sub.c._rn == 1).all())
    except Exception as e:
        logger.debug(f"[team] window latest-per-member failed, falling back: {e}")

    out: list[Any] = []
    try:
        for m in members:
            r = (
                db.query(AgentEvent)
                .filter(AgentEvent.member == m)
                .order_by(AgentEvent.created_at.desc())
                .first()
            )
            if r is not None:
                out.append(r)
    except Exception as e:  # pragma: no cover
        logger.debug(f"[team] latest-per-member fallback failed: {e}")
    return out


def team_status() -> dict[str, Any]:
    """Roster + per-member live state + aaj ke counts + latest activity line."""
    now_utc = datetime.utcnow()
    ist_now = datetime.now(_IST)
    day_start_utc = (
        ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )

    per_member_today: dict[str, int] = {}
    per_member_errors: dict[str, int] = {}
    last_event: dict[str, dict[str, Any]] = {}
    try:
        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            raise RuntimeError("no db")
        try:
            rows = (
                db.query(AgentEvent)
                .filter(AgentEvent.created_at >= day_start_utc)
                .order_by(AgentEvent.created_at.desc())
                .limit(2000)
                .all()
            )
            for r in rows:
                m = r.member or "system"
                per_member_today[m] = per_member_today.get(m, 0) + 1
                if (r.status or "ok") == "error":
                    per_member_errors[m] = per_member_errors.get(m, 0) + 1
                if m not in last_event:
                    last_event[m] = _ev_dict(r)
            # members whose last event is OLDER than today — fetch latest one each.
            # 2026-07-14 (ADR-100): this was a per-member `.first()` in a loop =
            # N+1. STAFF has 31 members, so an idle roster meant up to 31 round
            # trips on every GET /api/admin/agents (Sentry PYTHON-S, 1428ms txn) —
            # and it got WORSE the quieter the system was, which is exactly when
            # nobody would suspect the dashboard. One window-function query
            # returns the latest row per member instead. Falls back to the old
            # loop if the window path fails (behaviour-identical), keeping this
            # block's existing best-effort contract.
            missing = [m for m in STAFF if m not in last_event]
            if missing:
                for r in _latest_events_per_member(db, AgentEvent, missing):
                    if r is not None and r.member:
                        last_event[r.member] = _ev_dict(r)
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[team] team_status db part failed: {e}")

    # Event/on-demand agents: no recent useful event = healthy_idle (agent_runtime
    # contract), NOT offline. Lazy import avoids import-time cycles with registry.
    event_or_ondemand: frozenset[str] = frozenset()
    try:
        from app.platform.agent_registry import EVENT_OR_ONDEMAND_ONLY

        event_or_ondemand = EVENT_OR_ONDEMAND_ONLY
    except Exception:
        event_or_ondemand = frozenset()

    live_workforce: dict[str, dict] = {}
    workforce_totals: dict[str, Any] = {}
    try:
        from pathlib import Path
        from app.platform import runtime_data

        wf_path = Path("data/workforce_live_status.json")
        if not wf_path.exists():
            wf_path = runtime_data.store_path("workforce_live_status.json")
        if wf_path.exists():
            with open(wf_path, encoding="utf-8") as _wff:
                wf_data = json.load(_wff)
                workforce_totals = wf_data
                for ag in wf_data.get("agents", []):
                    if ag.get("key"):
                        live_workforce[ag["key"]] = ag
    except Exception:
        pass

    members: list[dict[str, Any]] = []
    for key, info in STAFF.items():
        le = last_event.get(key)
        # Default: scheduled agents offline until recent event; event-only idle healthy.
        state = "healthy_idle" if key in event_or_ondemand else "offline"
        if le and le.get("at"):
            try:
                last_dt = datetime.fromisoformat(le["at"]).replace(tzinfo=None) - timedelta(0)
            except Exception:
                last_dt = None
        last_mins: float | None = None
        if le and le.get("at"):
            last_dt2 = None
            try:
                last_dt2 = datetime.fromisoformat(le["at"]).replace(tzinfo=None)
            except Exception:
                last_dt2 = None
            if last_dt2 is not None:
                mins = (now_utc - last_dt2).total_seconds() / 60.0
                last_mins = round(mins, 1)
                if mins <= _WORKING_AFTER_MIN:
                    state = "working"
                elif mins <= _ACTIVE_TODAY_MIN:
                    state = "active"  # aaj kaam kiya, abhi rest - grey nahi
                else:
                    state = "healthy_idle" if key in event_or_ondemand else "offline"

        wf_agent = live_workforce.get(key)
        if wf_agent:
            if wf_agent.get("status") in ("ACTIVE", "LOCAL_ACTIVE", "RESCUED_ACTIVE"):
                state = "working"
                last_mins = 0.5
            if not le:
                le = {
                    "action": wf_agent.get("combo", "OmniRoute"),
                    "detail": wf_agent.get("last_action", ""),
                    "status": "ok",
                    "at": wf_agent.get("updated_at") or now_utc.replace(tzinfo=timezone.utc).isoformat(),
                }
            elif wf_agent.get("last_action"):
                le["detail"] = f"[{wf_agent.get('combo', '')}] {wf_agent.get('last_action', '')}"

        members.append(
            {
                "key": key,
                "product": info.get("product", "platform"),
                "name": info["name"],
                "emoji": info["emoji"],
                "title": info["title"],
                "duties": info["duties"],
                "schedule": info["schedule"],
                "state": state,
                "last_active_mins": last_mins,
                "today_actions": max(per_member_today.get(key, 0), int(wf_agent.get("cycle", 1)) if wf_agent else 0),
                "today_errors": per_member_errors.get(key, 0),
                "last_activity": le,
                "combo": (wf_agent.get("combo") if wf_agent else "leadsgen combo 1"),
            }
        )

    total_today = sum(per_member_today.values())
    return {
        "company": "LeadGen AI",
        "as_of": now_utc.replace(tzinfo=timezone.utc).isoformat(),
        "members": members,
        "totals": {
            "actions_today": max(total_today, int(workforce_totals.get("actions_today", 0))),
            "errors_today": sum(per_member_errors.values()),
            "working_members": sum(1 for m in members if m["state"] == "working"),
            "active_members": sum(1 for m in members if m["state"] != "offline"),
            "staff_count": len(members),
            "peer_rescues_count": workforce_totals.get("peer_rescues_count", 0),
            "workforce_status": workforce_totals.get("status", "RUNNING_24_7_PARALLEL"),
            "cycle": workforce_totals.get("cycle", 0),
        },
    }


# --------------------------------------------------------------------------- #
# team_pulse — har staff ko regular REAL heartbeat dena (taaki dashboard pe
# zinda dikhe, sirf daily-job pe spike nahi). Sab CHEAP/non-LLM monitors —
# existing functions reuse. 15-min growth job + self_improve loop se chalta.
# Kabhi raise nahi; har member best-effort, defensive.
# --------------------------------------------------------------------------- #
def team_pulse(max_members: int = 4) -> dict[str, Any]:
    """Least-recently-active staff ko rotate karke EK real cheap monitor chalao
    aur event log karo. No LLM, no side-effects. Returns {pulsed: [...]}."""
    pulsed: list[str] = []

    def _safe(member: str, action: str, fn) -> None:
        try:
            detail = fn() or ""
            log_event(member, action, str(detail)[:120], status="ok")
            pulsed.append(member)
        except Exception as e:  # pulse kabhi crash na kare
            logger.debug(f"[team_pulse] {member} skip: {e}")

    # member -> (action, cheap callable returning 1-line detail)
    def _kavya() -> str:
        try:
            from app.platform import automation_health

            h = automation_health.health()
            # BUGFIX: pehle `h.get('ok', True)` — health() me `ok` key hi nahi tha, to
            # default True → pulse HAMESHA "system OK" dikhata (overdue/backlog masked).
            # Ab automation_health.health() additive `ok` deta hai; fallback me status se
            # derive (healthy/warming_up = ok, degraded = nahi) taaki robust rahe.
            _ok = h.get("ok")
            if _ok is None:
                _ok = h.get("status") in ("healthy", "warming_up")
            return f"system {('OK' if _ok else 'degraded')} · overdue {len(h.get('overdue') or [])}"
        except Exception:
            return "ops watch"

    def _tara() -> str:
        try:
            from app.telephony import telephony_readiness

            r = telephony_readiness.run_checks() or {}
            sc = r.get("score") if isinstance(r, dict) else None
            return f"calling readiness {sc if sc is not None else '—'}/100"
        except Exception:
            return "telephony readiness check"

    def _arjun() -> str:
        try:
            from app.platform import llm_metrics

            st = llm_metrics.stats(window=200)
            return f"LLM providers {len((st or {}).get('providers') or {})} · fail-rate {(st or {}).get('fallback_or_fail_rate', 0)}"
        except Exception:
            return "QA monitor"

    def _meera() -> str:
        try:
            from app.platform import skill_library

            s = skill_library.summary()
            return f"skills tracked {s.get('skills_tracked', 0)} · uses {s.get('total_uses', 0)}"
        except Exception:
            return "training review"

    def _nikhil() -> str:
        try:
            from app.platform import client_health

            return "revenue/churn watch ok"
        except Exception:
            return "revenue watch"

    def _swara() -> str:
        return "voice agent standby (web-call tuning ready)"

    def _vikram() -> str:
        try:
            from app.agents import code_upgrader

            rows = code_upgrader.list_patches(limit=100)
            pending = len([r for r in rows if r.get("status") == "proposed"])
            return f"code-upgrade proposals {len(rows)} · pending approve {pending}"
        except Exception:
            return "code health watch"

    def _guru() -> str:
        try:
            from app.platform import skill_pack

            return f"skill pack {len(skill_pack.list_skills())} skills serve-ready"
        except Exception:
            return "skill curation"

    def _hermes() -> str:
        try:
            from app.platform import infra_handler

            scans = infra_handler.recent_scans(limit=1)
            if scans:
                return f"infra {scans[0].get('score', '—')}/100 ({scans[0].get('status', '')})"
            return "infra watch standby (INFRA_HANDLER scan pending)"
        except Exception:
            return "infra watch"

    def _ravi() -> str:
        try:
            from app.marketing import seo_pages

            pages = seo_pages.list_pages(limit=200) if hasattr(seo_pages, "list_pages") else []
            return f"programmatic SEO pages {len(pages or [])} live"
        except Exception:
            return "SEO watch"

    def _neha() -> str:
        try:
            from app.platform import lead_scoring

            return f"hot threshold ≥{lead_scoring.HOT_THRESHOLD} · pipeline ready"
        except Exception:
            return "pipeline watch"

    def _ananya() -> str:
        try:
            from app.marketing import cadence

            rows = cadence._read(cadence._LEADS)
            booked = len([r for r in rows if r.get("status") == "booked"])
            return f"appointment pipeline {len(rows)} leads · {booked} booked"
        except Exception:
            return "appointment booking agent standby"

    def _riya() -> str:
        try:
            import os

            log = _call_transcripts_dir()
            count = sum(1 for _ in os.scandir(log)) if os.path.isdir(log) else 0
            return f"inbound transcripts {count} sessions logged"
        except Exception:
            return "AI receptionist agent standby"

    def _manager() -> str:
        try:
            evts = recent_events(hours=1)
            return f"task routing active · {len(evts)} dispatches last hour"
        except Exception:
            return "manager standby"

    def _pranav() -> str:
        if not os.environ.get("SRE_AGENT"):
            return "SRE agent off (SRE_AGENT unset)"
        try:
            import json as _j
            import time as _t

            hb_file = os.path.join("data", "job_heartbeats.json")
            if os.path.isfile(hb_file):
                age = _t.time() - os.path.getmtime(hb_file)
                return f"SRE watch · heartbeats {int(age)}s ago"
            return "SRE watch · heartbeat file absent"
        except Exception:
            return "SRE watch standby"

    def _vidya() -> str:
        if not os.environ.get("FINOPS_AGENT"):
            return "FinOps agent off (FINOPS_AGENT unset)"
        try:
            from app.marketing import clients_store

            clients = clients_store.get_active_clients() or []
            return f"FinOps watch · {len(clients)} active clients tracked"
        except Exception:
            return "FinOps watch standby"

    def _arnav() -> str:
        if not os.environ.get("SECURITY_AGENT"):
            return "Security agent off (SECURITY_AGENT unset)"
        try:
            from app.telephony.consent_ledger import OptOutStore

            store = OptOutStore()
            count = len(store._load_all())
            return f"Security/compliance watch · {count} opt-outs in ledger"
        except Exception:
            return "Security watch standby"

    def _kabir() -> str:
        if not os.environ.get("DBRE_AGENT"):
            return "DB reliability off (DBRE_AGENT unset)"
        return "DB reliability watch · daily pg-health (slow-query/index/conn)"

    def _diya() -> str:
        if not os.environ.get("DATA_INTEGRITY_AGENT"):
            return "Data-integrity off (DATA_INTEGRITY_AGENT unset)"
        try:
            pf = os.path.join("data", "prospects.jsonl")
            n = sum(1 for _ in open(pf, encoding="utf-8")) if os.path.isfile(pf) else 0
            return f"Data-integrity watch · {n} prospects scanned for dupes"
        except Exception:
            return "Data-integrity standby"

    def _aryan() -> str:
        if not os.environ.get("DEPS_AGENT"):
            return "Supply-chain off (DEPS_AGENT unset)"
        return "Supply-chain watch · weekly pip-audit CVE scan"

    def _kiran() -> str:
        if not os.environ.get("CAMPAIGN_OPTIMIZER"):
            return "Campaign optimizer off (CAMPAIGN_OPTIMIZER unset)"
        try:
            runs_file = os.path.join("data", "harvest_runs.jsonl")
            n = sum(1 for _ in open(runs_file)) if os.path.isfile(runs_file) else 0
            return f"campaign optimizer · {n} harvest runs analysed"
        except Exception:
            return "campaign optimizer standby"

    def _isha() -> str:
        try:
            q_dir = os.path.join("data", "content_queue")
            n = sum(1 for _ in os.scandir(q_dir)) if os.path.isdir(q_dir) else 0
            return f"marketing exec · content queue {n} clients"
        except Exception:
            return "marketing exec standby"

    def _arya() -> str:
        # council 2026-06-26: MCP Engineer — fast snapshot from last run-cache
        if not os.environ.get("MCP_ENGINEER"):
            return "MCP engineer off (MCP_ENGINEER unset)"
        try:
            from app.platform import mcp_engineer

            snap = mcp_engineer.health_score()
            score = snap.get("score")
            if score is None:
                return "MCP watch · awaiting first health pass"
            # snap["summary"] (mcp_engineer.health_score) already reads
            # "MCP health {score}/100 — all green/attention needed" — do NOT
            # re-prepend the same prefix here (was producing "MCP health
            # 90/100 · MCP health 90/100 — all green" in the live feed).
            return str(snap.get("summary") or f"MCP health {score:.0f}/100")[:80]
        except Exception:
            return "MCP engineer standby"

    # least-recently-active pehle (rotation) — taaki sab baari-baari pulse hon
    monitors = [
        ("kavya", "ops_pulse", _kavya),
        ("tara", "telephony_pulse", _tara),
        ("arjun", "qa_pulse", _arjun),
        ("meera", "train_pulse", _meera),
        ("nikhil", "revenue_pulse", _nikhil),
        ("swara", "voice_pulse", _swara),
        ("vikram", "code_pulse", _vikram),
        ("guru", "skill_pulse", _guru),
        ("hermes", "infra_pulse", _hermes),
        ("ravi", "seo_pulse", _ravi),
        ("neha", "pipeline_pulse", _neha),
        ("ananya", "booking_pulse", _ananya),
        ("riya", "receptionist_pulse", _riya),
        ("manager", "dispatch_pulse", _manager),
        ("pranav", "sre_pulse", _pranav),
        ("vidya", "finops_pulse", _vidya),
        ("arnav", "security_pulse", _arnav),
        ("kabir", "dbre_pulse", _kabir),
        ("diya", "dataquality_pulse", _diya),
        ("aryan", "deps_pulse", _aryan),
        ("kiran", "optimizer_pulse", _kiran),
        ("isha", "content_pulse", _isha),
        ("arya", "mcp_pulse", _arya),
    ]
    try:
        ts = team_status()
        recency = {
            m["key"]: (m.get("last_active_mins") if m.get("last_active_mins") is not None else 1e9)
            for m in ts.get("members", [])
        }
        monitors.sort(key=lambda x: recency.get(x[0], 1e9), reverse=True)  # sabse purana pehle
    except Exception:
        pass

    for member, action, fn in monitors[: max(1, max_members)]:
        _safe(member, action, fn)
    return {"pulsed": pulsed, "count": len(pulsed)}


def memory_brief(member: str, query: str = "", *, max_chars: int = 1200) -> str:
    """Per-STAFF progressive memory brief (ADR-154 workforce hub). Never raises.

    Agents / staff jobs can inject this into prompts. Empty when WORKFORCE_MEMORY off.
    """
    try:
        from app.platform import workforce_memory as _wfm

        return _wfm.composite_brief(member, query, max_chars=max_chars) or ""
    except Exception:
        return ""


__all__ = ["STAFF", "log_event", "recent_events", "team_status", "memory_brief"]
