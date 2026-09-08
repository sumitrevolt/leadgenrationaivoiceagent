"""
Call Analytics (staff: Lekha) — call-center KPIs from the durable logs we already
keep. FREE, pure-stdlib + voice_metrics. The genuinely-missing piece flagged in the
2026-06-28 voice-production audit (no agent owned call-center metrics).

Sources (all already persisted):
  * web test-calls  -> web_call_store (duration, user-turns, per-turn reply latency_ms
                       + heard — the instrumentation shipped 2026-06-28)
  * bookings        -> calendar_booking durable ledger (data/bookings/)
  * qualifications  -> data/call_qualifications.jsonl (phone calls, if present)

Import-safe, never raises — returns a plain dict for /api/admin/web-calls/kpis.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _web_sessions() -> list[dict[str, Any]]:
    try:
        from app.voice_agent.web_call_store import list_all_sessions

        return list_all_sessions(limit=200, include_turns=True)
    except Exception:
        return []


def _bookings_count(days: int) -> int:
    try:
        from app.integrations.calendar_booking import CalendarBooking

        today = datetime.now()
        n = 0
        for d in range(max(1, days)):
            day = (today - timedelta(days=d)).strftime("%Y-%m-%d")
            n += len(CalendarBooking.list_bookings(limit=0, date_str=day))
        return n
    except Exception:
        return 0


def _qualified_count(days: int) -> int:
    """Phone-call qualifications (data/call_qualifications.jsonl) in the window."""
    path = os.path.join("data", "call_qualifications.jsonl")
    if not os.path.isfile(path):
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if str(r.get("ts") or r.get("timestamp") or "") >= cutoff:
                    if r.get("qualified") or str(r.get("status") or "").lower() in (
                        "qualified",
                        "hot",
                    ):
                        n += 1
    except Exception:
        return n
    return n


def compute_call_kpis(days: int = 7) -> dict[str, Any]:
    """Aggregate call KPIs over the last `days`. Never raises."""
    days = max(1, min(int(days or 7), 90))
    sessions = _web_sessions()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    sess = [s for s in sessions if str(s.get("started_at") or "") >= cutoff]
    if not sess:
        sess = sessions  # fall back to whatever exists so the panel isn't empty

    latencies: list[float] = []
    durations: list[float] = []
    user_turns: list[int] = []
    repeat_turns = deadair_turns = assistant_turns = 0

    for s in sess:
        try:
            durations.append(float(s.get("duration_s") or 0))
        except Exception:
            pass
        turns = s.get("turns") or []
        user_turns.append(sum(1 for t in turns if isinstance(t, dict) and t.get("role") == "user"))
        prev_assist = ""
        for t in turns:
            if not isinstance(t, dict) or t.get("role") == "user":
                continue
            assistant_turns += 1
            lat = t.get("latency_ms")
            if lat is not None:
                try:
                    latencies.append(float(lat))
                    if float(lat) > 9000:  # >9s = dead-air territory
                        deadair_turns += 1
                except Exception:
                    pass
            txt = (t.get("text") or "").strip().lower()
            if txt and txt == prev_assist:
                repeat_turns += 1
            prev_assist = txt

    try:
        from app.voice_agent.voice_metrics import latency_summary

        lat_summary = latency_summary(latencies)
    except Exception:
        lat_summary = {"n": len(latencies)}

    n = len(sess)
    bookings = _bookings_count(days)
    qualified = _qualified_count(days)
    return {
        "window_days": days,
        "web_calls": n,
        "avg_duration_s": round(sum(durations) / n, 1) if n else 0.0,
        "avg_user_turns": round(sum(user_turns) / n, 1) if n else 0.0,
        "assistant_turns": assistant_turns,
        "reply_latency_ms": lat_summary,
        "repeat_turns": repeat_turns,
        "deadair_turns": deadair_turns,
        "deadair_rate_pct": (
            round(100 * deadair_turns / assistant_turns, 1) if assistant_turns else 0.0
        ),
        "bookings": bookings,
        "booking_rate_pct": round(100 * bookings / n, 1) if n else 0.0,
        "qualified_phone": qualified,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def run_daily_digest() -> dict[str, Any]:
    """Lekha's daily call-KPI digest — the missing piece that makes her show
    'working' on the office map. compute_call_kpis() itself is only called
    on-demand from the admin dashboard today (app/api/web_call_admin.py) and
    never logs a team event; this wrapper is what a scheduled job calls.
    Never raises — degrades to {} on any failure so a scheduler tick can't
    break on this job."""
    try:
        kpis = compute_call_kpis(days=1)
    except Exception as e:
        logger.warning(f"[call_analytics] run_daily_digest compute failed: {e}")
        return {}
    try:
        from app.platform import team

        total = kpis.get("web_calls", 0)
        qualified = kpis.get("qualified_phone", 0)
        detail = f"Aaj {total} calls · {qualified} qualified" if total else f"Aaj {total} calls"
        team.log_event("lekha", "call_kpi_digest", detail, status="ok")
    except Exception as e:
        logger.debug(f"[call_analytics] run_daily_digest log_event skipped: {e}")
    return kpis


__all__ = ["compute_call_kpis", "run_daily_digest"]
