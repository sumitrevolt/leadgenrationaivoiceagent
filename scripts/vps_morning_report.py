#!/usr/bin/env python3
"""Read-only LIVE operational snapshot — run INSIDE the prod container:

    ssh root@VPS "docker exec -i leadgen_app python -" < scripts/vps_morning_report.py

Prints: today's emails sent, calls, agent job runs (heartbeats), key flags, and a
data-file inventory. Never mutates anything. Each section guarded (never crash).
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

IST = timezone(timedelta(hours=5, minutes=30))
now = datetime.now(IST)
today = now.strftime("%Y-%m-%d")
DATA = Path("data")


def hr(t):
    print("\n" + "=" * 56 + f"\n{t}\n" + "=" * 56)


print(f"LIVE OPS SNAPSHOT  —  {now.strftime('%Y-%m-%d %H:%M IST')}  (today={today})")

# ── key automation flags ────────────────────────────────────────────────────
hr("AUTOMATION FLAGS (what is ON)")
flags = [
    "AUTO_EMAIL_OUTREACH",
    "EMAIL_WARMUP",
    "REPLY_AGENT",
    "CADENCE_ENGINE",
    "LEAD_HARVESTER",
    "NICHE_ROTATION",
    "AUTO_ONBOARD",
    "TEAM_AUTOMATION",
    "RUN_IN_PROCESS_SCHEDULER",
    "SELF_IMPROVE_LOOP",
    "SALES_ENGINE",
    "AUTO_QUALIFY_CALLS",
    "TELEPHONY_PROVIDER",
    "VOBIZ_CALLER_ID",
    "USE_RERANKER",
    "USE_HYBRID_SEARCH",
    "USE_CONTEXTUAL_INGEST",
]
for f in flags:
    v = os.environ.get(f)
    print(f"  {f:28} = {v if v not in (None, '') else '(unset)'}")

# ── email outreach ──────────────────────────────────────────────────────────
hr("EMAIL OUTREACH (Rohan)")
try:
    from app.platform.auto_outreach import outreach_stats

    s = outreach_stats()
    print("  outreach_stats():", json.dumps(s, ensure_ascii=False, default=str)[:600])
except Exception as e:
    print(f"  outreach_stats unavailable: {e}")


def count_today(path: Path, ts_keys=("ts", "sent_at", "created_at", "emailed_at", "at")):
    """Count jsonl lines whose timestamp starts with today's date."""
    n_total = n_today = 0
    try:
        if not path.is_file():
            return (0, 0)
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line:
                continue
            n_total += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            for k in ts_keys:
                val = str(r.get(k, ""))
                if val.startswith(today):
                    n_today += 1
                    break
    except Exception:
        pass
    return (n_total, n_today)


for name in (
    "outreach_log.jsonl",
    "email_outreach.jsonl",
    "sent_emails.jsonl",
    "outreach.jsonl",
    "email_suppression.jsonl",
):
    p = DATA / name
    if p.exists():
        tot, tod = count_today(p)
        print(f"  {name:28} total={tot}  today={tod}")

# ── calls (cold-calling is DLT/Vobiz gated) ─────────────────────────────────
hr("CALLS (voice)")
try:
    tdir = DATA / "call_transcripts"
    tfile = tdir / f"{today}.jsonl"
    tot_t = sum(1 for _ in tfile.open(encoding="utf-8")) if tfile.exists() else 0
    print(f"  call_transcripts/{today}.jsonl  calls_today={tot_t}")
except Exception as e:
    print(f"  call_transcripts: {e}")
for name in ("call_qualifications.jsonl",):
    p = DATA / name
    tot, tod = count_today(p, ts_keys=("ts", "at", "created_at"))
    print(f"  {name:28} total={tot}  today={tod}")
try:
    from app.models.base import get_db_session
    from app.models.call_log import CallLog

    with get_db_session() as db:
        total = db.query(CallLog).count()
        print(f"  call_logs DB rows (all-time) = {total}")
except Exception as e:
    print(f"  call_logs DB: {e}")

# ── agent jobs: heartbeats (did the scheduler run today's jobs?) ─────────────
hr("AGENT JOB HEARTBEATS (last run per job)")
hb = DATA / "job_heartbeats.json"
try:
    if hb.is_file():
        data = json.loads(hb.read_text(encoding="utf-8"))
        nowts = time.time()
        for job, ts in sorted(data.items()):
            try:
                age_min = (nowts - float(ts)) / 60.0
                when = datetime.fromtimestamp(float(ts), IST).strftime("%H:%M")
                ran_today = datetime.fromtimestamp(float(ts), IST).strftime("%Y-%m-%d") == today
                mark = "TODAY" if ran_today else "stale"
                print(f"  {job:24} last={when} ({age_min:6.0f} min ago)  [{mark}]")
            except Exception:
                print(f"  {job:24} {ts}")
    else:
        print("  data/job_heartbeats.json missing (scheduler may not have a heartbeat yet)")
except Exception as e:
    print(f"  heartbeats error: {e}")

# ── agent activity feed (agent_events) ──────────────────────────────────────
hr("AGENT EVENTS (today, from DB)")
try:
    from sqlalchemy import text as _t

    from app.models.base import get_db_session

    with get_db_session() as db:
        rows = db.execute(
            _t(
                "SELECT agent, action, status, created_at FROM agent_events "
                "WHERE created_at::date = CURRENT_DATE ORDER BY created_at DESC LIMIT 25"
            )
        ).fetchall()
        print(f"  agent_events today = {len(rows)} (showing latest 25)")
        for r in rows:
            print(f"   - {str(r[3])[:16]}  {r[0]:10} {r[1]:18} {r[2]}")
except Exception as e:
    print(f"  agent_events query failed: {e}")

# ── data inventory ──────────────────────────────────────────────────────────
hr("DATA FILE INVENTORY (jsonl line counts)")
try:
    for p in sorted(DATA.glob("*.jsonl")):
        try:
            n = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
        except Exception:
            n = -1
        print(f"  {p.name:34} {n} lines")
except Exception as e:
    print(f"  inventory error: {e}")

print("\n--- end snapshot ---")
