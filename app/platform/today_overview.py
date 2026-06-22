"""
Today Overview — "Aaj kya hua?" plain-Hinglish admin snapshot (NO LLM, instant).
================================================================================

PROBLEM (user feedback 2026-06-12): automation command center technical tha —
heartbeat tables, flag names, job keys. Admin ko ek nazar me samajh nahi aata
tha ki (a) automations chal rahe hain ya nahi, (b) agents ne aaj kya kiya,
(c) kya tootha hai aur kaise theek karein.

YEH MODULE existing data ko (automation_health + team.team_status + llm_metrics
+ flags) PLAIN HINGLISH sentences me aggregate karta hai. Koi naya store nahi,
koi LLM call nahi (instant + free), kabhi raise nahi karta.

API: GET /api/growth/overview/today (growth.py) → /app/automation "🏠 Aaj" tab.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# weekday() 0=Mon … 6=Sun — weekly staff jobs (baaki daily = har din due)
_WEEKLY_ON: dict[str, int] = {
    "weekly_marketing": 2,  # Budh
    "saturday_hygiene": 5,  # Shani
    "kb_refresh": 6,  # Ravi
}
_DAY_HI = ("Som", "Mangal", "Budh", "Guru", "Shukr", "Shani", "Ravi")


def _job_due_today(job: str) -> bool:
    try:
        from zoneinfo import ZoneInfo

        wd = datetime.now(ZoneInfo("Asia/Kolkata")).weekday()
    except Exception:
        wd = datetime.now(timezone.utc).weekday()
    if job not in _WEEKLY_ON:
        return True
    return wd == _WEEKLY_ON[job]


# Har scheduled job ka insaani naam + "yeh kya karta hai" — admin-friendly.
JOB_INFO: dict[str, dict[str, str]] = {
    "growth": {
        "label": "Growth pulse (har 15 min)",
        "kya": "Funnel ki sehat check karke chhote auto-fix karta hai",
    },
    "ops": {
        "label": "Kavya — system health (hourly)",
        "kya": "Server/DB/queue sab theek hai ya nahi",
    },
    "reply_triage": {
        "label": "Reply agent (hourly)",
        "kya": "Aaye hue email replies padh ke hot leads flag + jawab draft karta hai",
    },
    "watchdog": {
        "label": "Ops watchdog (hourly)",
        "kya": "Kuch critical toote to Sumit ko email alert",
    },
    "onboard": {
        "label": "Auto onboarding (hourly)",
        "kya": "Naye paid client ka setup khud kar deta hai",
    },
    "qa": {"label": "Arjun — QA (raat 2:30)", "kya": "Voice agent ki quality test karta hai"},
    "trainer": {"label": "Meera — trainer (raat 3)", "kya": "Agents ko naya seekhata hai"},
    "blog": {"label": "SEO blog (subah 6:30)", "kya": "Roz ek SEO blog post banata hai"},
    "content": {
        "label": "Isha — content (subah 7)",
        "kya": "Apne + clients ke social posts/captions banata hai",
    },
    "digest": {"label": "Daily digest (subah 8:30)", "kya": "Din ka summary email Sumit ko"},
    "prospect": {
        "label": "Dev — scraping (subah 9:30)",
        "kya": "Naye business prospects dhundta hai (42 niches rotation)",
    },
    "email_outreach": {
        "label": "Rohan — cold email (subah 10:30)",
        "kya": "Roz 25 tak personalized cold emails + follow-ups bhejta hai",
    },
    "pipeline": {
        "label": "Neha — pipeline (11:00)",
        "kya": "Leads rescore + hot leads Rohan ko surface",
    },
    "midday_prospect": {
        "label": "Rohan — midday harvest (14:30)",
        "kya": "Dusra free lead-supply pass (websearch/opendata)",
    },
    "email_followup": {
        "label": "Rohan — afternoon followup (16:00)",
        "kya": "Day-3/Day-7 email follow-ups (naya cold batch nahi)",
    },
    "evening_wrap": {
        "label": "Boss — evening wrap (18:30)",
        "kya": "Din ka summary + hot leads EOD recap",
    },
    "weekly_marketing": {
        "label": "Isha — weekly packs (Wed 12:30)",
        "kya": "S-tier niche marketing content bank top-up",
    },
    "kb_refresh": {
        "label": "Dev — KB refresh (Sun 05:00)",
        "kya": "Client websites se contextual KB re-ingest",
    },
    "saturday_hygiene": {
        "label": "Kavya — Sat hygiene (04:00)",
        "kya": "DLQ sweep + stale celery queue trim",
    },
    "standup": {
        "label": "Boss standup (08:00)",
        "kya": "Team priorities plan (gated AGENT_STANDUP)",
    },
    "engineer_sre": {"label": "Pranav SRE (hourly)", "kya": "Backup/DR/capacity score"},
    "engineer_finops": {"label": "Vidya FinOps (09:00)", "kya": "Margin + LLM cost digest"},
    "engineer_security": {"label": "Arnav security (09:30)", "kya": "Compliance posture"},
    "readiness_digest": {
        "label": "Activation digest (08:30)",
        "kya": "First-paid-customer readiness ntfy",
    },
    "revenue_snapshot": {
        "label": "Revenue snapshot (raat 00:15)",
        "kya": "Roz ka MRR/churn record karta hai (admin revenue chart ke liye)",
    },
    "meter_watch": {
        "label": "Billing meter-watch (har ghante :55)",
        "kya": "Minute-billing meter fail ho to alert",
    },
    "process_autostart": {
        "label": "Process auto-start (~11:30)",
        "kya": "Process-engine workflows auto-shuru karta hai (gated)",
    },
    "flow_cron": {
        "label": "Flow runner cron (har 5 min)",
        "kya": "Customer/admin flows ke due cron triggers scan karta hai (gated)",
    },
}

# Important flags jo OFF hon to admin ko batana chahiye (flag -> Hinglish reason)
_IMPORTANT_FLAGS = {
    "AUTO_EMAIL_OUTREACH": "Cold email outreach band hai — naye leads ko mail nahi ja raha",
    "NICHE_ROTATION": "42-niche scraping rotation band hai — sirf default niches scrape ho rahe",
    "REPLY_AGENT": "Email replies koi nahi padh raha (hot leads miss ho sakte)",
    "OPS_WATCHDOG": "System toote to alert nahi aayega",
    "SELF_IMPROVE_LOOP": "Self-improve loop band hai — agents khud kaam nahi uthayenge",
    "DUNNING_ENGINE": "Payment fail hone par recovery emails nahi jayenge",
}


def _flag_on(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in ("1", "true", "yes", "on")


def _ago_minutes(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(str(iso))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds() // 60))
    except Exception:
        return None


def _ago_str(mins: int | None) -> str:
    if mins is None:
        return "kabhi nahi"
    if mins < 2:
        return "abhi-abhi"
    if mins < 60:
        return f"{mins} min pehle"
    if mins < 60 * 24:
        return f"{mins // 60} ghante pehle"
    return f"{mins // (60 * 24)} din pehle"


def build() -> dict[str, Any]:
    """Poora 'Aaj' snapshot — headline, problems[], staff[], jobs[], flags_off[].
    Har item plain Hinglish. Kabhi raise nahi karta (partial data theek hai)."""
    problems: list[dict[str, str]] = []
    jobs_out: list[dict[str, Any]] = []
    staff_out: list[dict[str, Any]] = []
    flags_off: list[dict[str, str]] = []
    totals = {"events_today": 0, "working": 0, "staff": 0}

    # ---- 1) Scheduled jobs (dead-man heartbeats) -> Hinglish status ----
    try:
        from app.platform import automation_health

        h = automation_health.health()
        for j in h.get("jobs", []):
            key = j.get("job", "")
            info = JOB_INFO.get(key, {"label": key, "kya": ""})
            mins = _ago_minutes(j.get("last_run"))
            status = j.get("status", "unknown")
            if status == "ok":
                line = f"✅ Chal raha hai — pichhli baar {_ago_str(mins)}"
            elif status == "overdue":
                if _job_due_today(key):
                    line = f"⚠️ Time par nahi chala (pichhli baar {_ago_str(mins)})"
                    problems.append(
                        {
                            "kya": f"{info['label']} time par nahi chala",
                            "fix": "Worker/scheduler container check karo — /app/ops me ya 'docker ps' se",
                        }
                    )
                else:
                    line = f"📅 Weekly job — agle din schedule ({_DAY_HI[_WEEKLY_ON[key]]})"
                    status = "scheduled_off"
            elif status == "last_failed":
                line = f"❌ Pichhla run FAIL hua ({_ago_str(mins)})"
                problems.append(
                    {
                        "kya": f"{info['label']} pichhli baar fail hua",
                        "fix": "Events tab me error dekho",
                    }
                )
            elif status == "never_ran":
                if key in _WEEKLY_ON and not _job_due_today(key):
                    line = f"📅 Aaj schedule nahi — har {_DAY_HI[_WEEKLY_ON[key]]} ko chalega"
                    status = "scheduled_off"
                else:
                    line = "⏳ Abhi tak nahi chala — deploy ke baad pehli run pending"
                    problems.append(
                        {
                            "kya": f"{info['label']} abhi tak heartbeat nahi mila",
                            "fix": "Scheduler/worker up hai? Mission Control se manual trigger ya worker logs dekho",
                        }
                    )
            elif status == "scheduled_off":
                day = _DAY_HI[_WEEKLY_ON[key]] if key in _WEEKLY_ON else "?"
                line = f"📅 Aaj schedule nahi — har {day} ko chalega"
            else:
                line = "❓ Status pata nahi"
            jobs_out.append({**info, "job": key, "status": status, "line": line})
        q = h.get("queue") or {}
        if h.get("queue_backlogged"):
            problems.append(
                {
                    "kya": f"Task queue me kaam atka hai (celery={q.get('celery')}, dlq={q.get('dlq')})",
                    "fix": "Worker container restart karo ya DLQ retry (Upgrader tab)",
                }
            )
    except Exception as e:
        logger.debug(f"[today] automation_health failed: {e}")

    # ---- 2) Staff — aaj kisne kya kiya ----
    try:
        from app.platform.team import team_status

        ts = team_status()
        members = ts.get("members") or []
        totals["staff"] = len(members)
        for m in members:
            today = int(m.get("today_actions") or 0)
            state = str(m.get("state") or "")
            le = m.get("last_activity") or {}
            last = ""
            if isinstance(le, dict) and (le.get("action") or le.get("detail")):
                last = f"{le.get('action', '')}: {le.get('detail', '')}".strip(": ")
            if state == "working":
                totals["working"] += 1
                line = "🟢 Abhi kaam kar raha hai"
            elif state == "active":
                line = "🔵 Aaj active tha"
            else:
                line = "⚪ Kaafi der se kuch nahi kiya"
            totals["events_today"] += today
            staff_out.append(
                {
                    "member": m.get("key", ""),
                    "name": m.get("name", ""),
                    "emoji": m.get("emoji", "🤖"),
                    "role": m.get("title", ""),
                    "today": today,
                    "line": line,
                    "last": str(last)[:140],
                }
            )
        staff_out.sort(key=lambda x: -x["today"])
    except Exception as e:
        logger.debug(f"[today] team_status failed: {e}")

    # ---- 3) LLM brain health (free providers) ----
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        fb = float(st.get("fallback_or_fail_rate") or 0)
        if int(st.get("total_calls") or 0) >= 20 and fb > 0.5:
            problems.append(
                {
                    "kya": f"AI brain struggle kar raha hai ({round(fb * 100)}% calls fail/fallback)",
                    "fix": "Free LLM quota khatam ho sakta hai — kal tak rukna ya naya key add karna",
                }
            )
    except Exception as e:
        logger.debug(f"[today] llm_metrics failed: {e}")

    # ---- 4) Important flags OFF ----
    for flag, reason in _IMPORTANT_FLAGS.items():
        if not _flag_on(flag):
            flags_off.append({"flag": flag, "matlab": reason})

    # ---- Headline ----
    if problems:
        headline = f"⚠️ {len(problems)} cheez dhyan maangti hai — neeche dekho"
    elif totals["events_today"] > 0:
        headline = (
            f"✅ Sab theek chal raha hai — aaj team ne {totals['events_today']} kaam kiye"
            f" ({totals['working']} agent abhi active)"
        )
    else:
        headline = "🌅 Aaj abhi tak koi kaam log nahi hua (subah ke jobs ka time dekho)"

    return {
        "headline": headline,
        "problems": problems,
        "staff": staff_out,
        "jobs": jobs_out,
        "flags_off": flags_off,
        "totals": totals,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


__all__ = ["build", "JOB_INFO"]
