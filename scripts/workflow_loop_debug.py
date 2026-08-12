#!/usr/bin/env python3
"""Full workflow + loop debugger — all major automation loops (NDJSON → debug-6e326c.log).

Loops checked:
  A cadence enroll path   B journey engine + ensure_active_defaults
  C staff job heartbeats  D cadence run_due stats
  E self-improve loop     F inquiry→cadence→journey chain (dry)
  G celery/DLQ backlog

Run: python scripts/workflow_loop_debug.py
VPS: docker exec leadgen_app python scripts/workflow_loop_debug.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "debug-6e326c.log"
SESSION = "6e326c"
RUN = os.environ.get("WORKFLOW_DEBUG_RUN", "loop1")


def _log(hid: str, loc: str, msg: str, data: dict | None = None) -> None:
    row = {
        "sessionId": SESSION,
        "hypothesisId": hid,
        "location": loc,
        "message": msg,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": RUN,
    }
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    flag = "OK" if not data or data.get("broken") is not True else "BROKEN"
    print(f"[{hid}][{flag}] {msg} | {data or {}}")


def probe_cadence() -> None:
    from app.marketing import cadence

    st = cadence.stats()
    broken = (
        bool(st.get("engine_on"))
        and int(st.get("active") or 0) > 0
        and not (st.get("step_touches") or {})
    )
    _log("D", "loop:cadence", "cadence loop", {**st, "broken": broken})


def probe_journey() -> None:
    from app.marketing import journeys

    before = [r for r in journeys.list_journeys() if r.get("enabled")]
    n = journeys.ensure_active_defaults()
    after = [r for r in journeys.list_journeys() if r.get("enabled")]
    _log(
        "B",
        "loop:journey",
        "journey ensure_active_defaults",
        {
            "engine_on": journeys._enabled(),
            "enabled_before": len(before),
            "enabled_after": len(after),
            "activated": n,
            "broken": journeys._enabled() and len(after) == 0,
            "triggers": [r.get("trigger") for r in journeys.list_journeys()[:5]],
        },
    )


def probe_heartbeats() -> None:
    from app.platform import automation_health

    h = automation_health.health()
    never = [j["job"] for j in (h.get("jobs") or []) if j.get("status") == "never_ran"]
    q = h.get("queue") or {}
    _log(
        "C",
        "loop:scheduler",
        "staff job heartbeats",
        {
            "never_ran": never,
            "overdue": [j["job"] for j in (h.get("jobs") or []) if j.get("status") == "overdue"],
            "celery": q.get("celery"),
            "dlq": q.get("dlq"),
            "backlogged": h.get("queue_backlogged"),
            "broken": bool(h.get("queue_backlogged")),
        },
    )


async def probe_self_improve() -> None:
    from app.agents import self_improve

    on = self_improve.enabled()
    if not on:
        _log("E", "loop:self_improve", "self-improve OFF", {"enabled": False, "broken": False})
        return
    try:
        hb_path = os.path.join("data", "self_improve_heartbeat.json")
        hb = {}
        if os.path.isfile(hb_path):
            hb = json.loads(open(hb_path, encoding="utf-8").read())
        _log(
            "E",
            "loop:self_improve",
            "self-improve state",
            {
                "enabled": True,
                "heartbeat_status": hb.get("status"),
                "runs_today": hb.get("runs_today"),
                "broken": hb.get("status") == "stale",
            },
        )
    except Exception as e:
        _log("E", "loop:self_improve", "heartbeat read fail", {"error": str(e)[:120]})


async def probe_inquiry_chain() -> None:
    """Dry-run inquiry funnel pieces (no HTTP)."""
    from app.marketing import cadence, journeys

    lead = {
        "phone": "9888877776",
        "name": "loop-debug",
        "source": "inquiry",
        "niche": "solar",
        "city": "Mumbai",
    }
    c = cadence.enroll(lead)
    journeys.ensure_active_defaults()
    runs = await journeys.emit_event(
        "inquiry_received", {"name": "loop-debug", "phone": lead["phone"], "niche": "solar"}
    )
    _log(
        "F",
        "loop:inquiry_chain",
        "inquiry → cadence + journey emit",
        {
            "cadence_id": c.get("id"),
            "journey_runs": len(runs),
            "broken": journeys._enabled() and len(runs) == 0,
        },
    )


async def probe_pipeline() -> None:
    from app.platform import pipeline_ops

    r = await pipeline_ops.run_daily()
    _log(
        "G",
        "loop:pipeline",
        "pipeline daily tick",
        {
            "ok": r.get("ok"),
            "rescore": (r.get("rescore") or {}).get("ok"),
            "journeys_activated": r.get("journeys_activated"),
        },
    )


async def main_async() -> int:
    print("=== WORKFLOW LOOP DEBUG ===")
    probe_cadence()
    probe_journey()
    probe_heartbeats()
    await probe_self_improve()
    await probe_inquiry_chain()
    await probe_pipeline()
    print(f"Logs -> {LOG}")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
