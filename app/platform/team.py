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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# India timezone for "today" boundaries (dashboard counts).
_IST = timezone(timedelta(hours=5, minutes=30))


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
        "duties": "Telephony readiness (Exotel auth, caller-ID, webhooks, DND, TTS/STT/LLM chain) har ghante verify karna — calling launch ke liye system hamesha taiyaar rahe",
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
        "duties": "35+ project skills ko agents ke runtime context + KB me rakhna, naye agent-authored skills curate karna — LLM/team seekhte rahein",
        "schedule": "Roz (trainer job ke saath, gated SKILL_PACK)",
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


# Status windows (realism): "working" = abhi-abhi active; "active" = aaj kaam kiya
# (resting); "offline" = aaj kuch nahi. Pehle 2-min working/20-min offline tha →
# din me kaam karne wale bhi grey "idle" dikhte the. Ab schedule-cycles reflect hote.
_WORKING_AFTER_MIN = 20      # is window me event = abhi kaam kar raha (green pulse)
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

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_pub())  # fire-and-forget, never blocks caller
        except RuntimeError:
            pass  # no running loop (sync context) — SSE fallback polling handle karta hai
    except Exception:
        pass


def recent_events(limit: int = 60, member: str | None = None) -> list[dict[str, Any]]:
    """Latest activity feed (newest first) — dashboard ke liye dicts."""
    try:
        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            return []
        try:
            q = db.query(AgentEvent).order_by(AgentEvent.created_at.desc())
            if member:
                q = q.filter(AgentEvent.member == member)
            rows = q.limit(max(1, min(int(limit), 300))).all()
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


# --------------------------------------------------------------------------- #
# Team status (dashboard ka main payload)
# --------------------------------------------------------------------------- #
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
            # members whose last event is OLDER than today — fetch latest one each
            missing = [m for m in STAFF if m not in last_event]
            for m in missing:
                r = (
                    db.query(AgentEvent)
                    .filter(AgentEvent.member == m)
                    .order_by(AgentEvent.created_at.desc())
                    .first()
                )
                if r is not None:
                    last_event[m] = _ev_dict(r)
        finally:
            db.close()
    except Exception as e:
        logger.debug(f"[team] team_status db part failed: {e}")

    members: list[dict[str, Any]] = []
    for key, info in STAFF.items():
        le = last_event.get(key)
        state = "offline"
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
                    state = "active"   # aaj kaam kiya, abhi rest — grey nahi
                else:
                    state = "offline"
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
                "today_actions": per_member_today.get(key, 0),
                "today_errors": per_member_errors.get(key, 0),
                "last_activity": le,
            }
        )

    total_today = sum(per_member_today.values())
    return {
        "company": "LeadGen AI",
        "as_of": now_utc.replace(tzinfo=timezone.utc).isoformat(),
        "members": members,
        "totals": {
            "actions_today": total_today,
            "errors_today": sum(per_member_errors.values()),
            "working_members": sum(1 for m in members if m["state"] == "working"),
            "active_members": sum(1 for m in members if m["state"] != "offline"),
            "staff_count": len(members),
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
            return f"system {('OK' if h.get('ok', True) else 'degraded')} · overdue {len(h.get('overdue') or [])}"
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
    ]
    try:
        ts = team_status()
        recency = {m["key"]: (m.get("last_active_mins") if m.get("last_active_mins") is not None else 1e9) for m in ts.get("members", [])}
        monitors.sort(key=lambda x: recency.get(x[0], 1e9), reverse=True)  # sabse purana pehle
    except Exception:
        pass

    for member, action, fn in monitors[: max(1, max_members)]:
        _safe(member, action, fn)
    return {"pulsed": pulsed, "count": len(pulsed)}


__all__ = ["STAFF", "log_event", "recent_events", "team_status"]
