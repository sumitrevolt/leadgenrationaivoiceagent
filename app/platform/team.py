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
        "name": "Boss",
        "emoji": "🧑‍💼",
        "title": "Manager (Supervisor)",
        "duties": "Kaam baantna — data/leads agents ko route karna (LangGraph), team coordination",
        "schedule": "On-demand (har /api/agents/run pe)",
    },
    "swara": {
        "name": "Swara",
        "emoji": "📞",
        "title": "Telecaller",
        "duties": "End-customers ko call karna (phone + web demo), niche scripts se qualify karna, objections handle karna",
        "schedule": "On-demand (calls/demos)",
    },
    "dev": {
        "name": "Dev",
        "emoji": "📚",
        "title": "Data Analyst",
        "duties": "Client business profile + niche knowledge KB me seed karna, RAG grounding maintain karna",
        "schedule": "Har naye client pe auto",
    },
    "rohan": {
        "name": "Rohan",
        "emoji": "🎯",
        "title": "Leads Manager",
        "duties": "Outreach plan banana, lead qualification criteria set karna, campaigns ke liye targeting",
        "schedule": "On-demand (campaigns)",
    },
    "arjun": {
        "name": "Arjun",
        "emoji": "🧪",
        "title": "QA Engineer",
        "duties": "Voice agent ko scripted conversations se test karna, bugs (double/repeat/slow/long) pakad ke report karna",
        "schedule": "Roz raat 2:30 + on-demand",
    },
    "meera": {
        "name": "Meera",
        "emoji": "🎓",
        "title": "Trainer",
        "duties": "Call transcripts padh ke quality analysis (STT failures, repeats, latency), tuning suggestions nikalna",
        "schedule": "Roz raat 3:00 + on-demand",
    },
    "kavya": {
        "name": "Kavya",
        "emoji": "🛡️",
        "title": "Ops Monitor",
        "duties": "System health (service, AI providers, DB, disk), telephony balance/trunk status pe nazar",
        "schedule": "Har ghante + on-demand",
    },
    "isha": {
        "name": "Isha",
        "emoji": "📣",
        "title": "Marketing Executive",
        "duties": "Clients ke liye AI social posts (FB/Insta captions), Google Business Profile tips, festival/offer content",
        "schedule": "On-demand (marketing)",
    },
    "tara": {
        "name": "Tara",
        "emoji": "🎙️",
        "title": "Voice Infra Ops",
        "duties": "Telephony readiness (Exotel auth, caller-ID, webhooks, DND, TTS/STT/LLM chain) har ghante verify karna — calling launch ke liye system hamesha taiyaar rahe",
        "schedule": "Har ghante (watchdog ke saath)",
    },
    "nikhil": {
        "name": "Nikhil",
        "emoji": "💰",
        "title": "Revenue Ops",
        "duties": "Dunning recovery, lifecycle nurture funnel, client churn-risk aur MRR digest pe nazar — paisa leak na ho",
        "schedule": "Roz (digest/content jobs ke saath)",
    },
}

# member offline mana jaata hai agar itne minute se koi event nahi (scheduled wale).
_IDLE_AFTER_MIN = 20


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
    try:
        from app.models.agent_event import AgentEvent

        db = _db()
        if db is None:
            return
        try:
            ev = AgentEvent(
                id=str(uuid.uuid4()),
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
            if last_dt is not None:
                mins = (now_utc - last_dt).total_seconds() / 60.0
                if mins <= 2:
                    state = "working"
                elif mins <= _IDLE_AFTER_MIN:
                    state = "idle"
                else:
                    state = "offline"
        members.append(
            {
                "key": key,
                "name": info["name"],
                "emoji": info["emoji"],
                "title": info["title"],
                "duties": info["duties"],
                "schedule": info["schedule"],
                "state": state,
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
            "active_members": sum(1 for m in members if m["state"] != "offline"),
            "staff_count": len(members),
        },
    }


__all__ = ["STAFF", "log_event", "recent_events", "team_status"]
