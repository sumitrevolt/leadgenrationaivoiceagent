#!/usr/bin/env python3
"""Runtime workflow-gap probe — writes NDJSON to debug-6e326c.log (debug session).

Checks incomplete loops: cadence enroll, journey rules, job heartbeats, cadence queue.
Run: python scripts/workflow_gap_probe.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
LOG = ROOT / "debug-6e326c.log"
SESSION = "6e326c"


def _log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    row = {
        "sessionId": SESSION,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": "probe1",
    }
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception:
        pass
    print(f"[{hypothesis_id}] {message}", data or "")


def probe_cadence_enroll_kwarg() -> None:
    """Hypothesis A: public_site passes invalid source= kwarg → enroll never runs."""
    from app.marketing import cadence

    r = cadence.enroll({"phone": "9999999998", "name": "probe-ok", "source": "inquiry"})
    _log(
        "A",
        "probe:cadence",
        "enroll supported signature",
        {"id": r.get("id"), "status": r.get("status")},
    )


def probe_journey_rules() -> None:
    """Hypothesis B: JOURNEY_ENGINE on but all rules disabled → empty loops."""
    from app.marketing import journeys

    rules = journeys.list_journeys()
    enabled = [r for r in rules if r.get("enabled")]
    _log(
        "B",
        "probe:journeys",
        "journey rules inventory",
        {
            "engine_on": journeys._enabled(),
            "total": len(rules),
            "enabled": len(enabled),
            "names_enabled": [r.get("name") for r in enabled[:5]],
        },
    )


def probe_job_heartbeats() -> None:
    """Hypothesis C/D: jobs never_ran or overdue; queue backlog."""
    try:
        from app.platform import automation_health

        h = automation_health.health()
        jobs = h.get("jobs") or []
        never = [j["job"] for j in jobs if j.get("status") == "never_ran"]
        overdue = [j["job"] for j in jobs if j.get("status") == "overdue"]
        q = h.get("queue") or {}
        _log(
            "C",
            "probe:heartbeats",
            "scheduled job health",
            {
                "never_ran": never,
                "overdue": overdue,
                "celery": q.get("celery"),
                "dlq": q.get("dlq"),
                "backlogged": h.get("queue_backlogged"),
            },
        )
    except Exception as e:
        _log("C", "probe:heartbeats", "health check failed", {"error": str(e)[:120]})


def probe_cadence_queue() -> None:
    """Hypothesis D: cadence enrolled but run_due never advances."""
    try:
        from app.marketing import cadence

        st = cadence.stats()
        _log(
            "D",
            "probe:cadence",
            "cadence stats",
            st if isinstance(st, dict) else {"raw": str(st)[:200]},
        )
    except Exception as e:
        _log("D", "probe:cadence", "cadence stats failed", {"error": str(e)[:120]})


def main() -> int:
    print("=== WORKFLOW GAP PROBE ===")
    probe_cadence_enroll_kwarg()
    probe_journey_rules()
    probe_job_heartbeats()
    probe_cadence_queue()
    print(f"Logs -> {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
