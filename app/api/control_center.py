"""Control Center — enterprise ops cockpit L1 (Executive) read-side aggregator.

ONE call powers the whole "Control Center" dashboard L1 view so the frontend
doesn't fan out to 6 separate admin endpoints (each its own round-trip + auth).

This is a THIN read-only aggregator: it fans IN over existing modules
(today_overview + automation_health + llm_metrics + activation + eval_gate +
flow_dispatch), each in its OWN try/except — partial data is fine, NEVER raises.
Every import is lazy (inside the function) so a broken downstream module can
never break app import. On total failure the top-level guard still returns a
minimal `{ok: true, ...defaults}` shell.

API: GET /api/control-center/overview (admin) → /app/control-center page.
Mounted via app.include_router(..., prefix="/api") in app/main.py.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Control Center"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _control_center_enabled() -> bool:
    """CONTROL_CENTER nav-surface gate (INERT default). The overview API itself
    stays admin-reachable for ops, but this flag tells the frontend whether the
    Control Center nav entry / page should be surfaced to users (default OFF)."""
    return (os.getenv("CONTROL_CENTER", "0") or "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _defaults() -> dict[str, Any]:
    """Safe baseline — every block degrades to this without changing the shape."""
    return {
        "ok": True,
        "at": _now_iso(),
        # nav-surface gate (CONTROL_CENTER flag) — frontend hides the page entry
        # when False. INERT default: the cockpit is opt-in until the flag is set.
        "nav_enabled": False,
        "headline": "",
        "problems": [],
        "metrics": {
            "staff": {"total": 0, "active": 0},
            "jobs": {"total": 0, "ok": 0, "issues": 0},
            "runs": {"total": 0, "running": 0},
            "queue": {"depth": 0, "dlq": 0},
            "heartbeat": {"up": 0, "total": 0},
            "llm": {"ok_rate": 0.0, "primary": "mistral"},
        },
        "staff": [],
        "jobs": [],
        "flags_off": [],
        "activation": {"ready_for_paid": False, "blockers": 0},
        "eval_gate": {"status": "neutral", "regression": False},
        # Provider chain order if cheaply available, else the live free-stack order.
        "providers": ["mistral", "groq", "cerebras", "gemini"],
        # The project has NO cost telemetry — never fabricate a number.
        "cost": {"available": False, "note": "instrument pending"},
    }


@router.get("/control-center/overview")
async def control_center_overview(_user=Depends(require_admin)) -> dict[str, Any]:
    """L1 Executive snapshot in one call. Never raises (partial data OK)."""
    out = _defaults()
    out["at"] = _now_iso()
    out["nav_enabled"] = _control_center_enabled()

    # ---- 1) today_overview: headline / problems / staff / jobs / flags_off / totals ----
    try:
        from app.platform import today_overview

        t = today_overview.build() or {}
        out["headline"] = t.get("headline") or ""
        out["problems"] = t.get("problems") or []
        staff = t.get("staff") or []
        jobs = t.get("jobs") or []
        out["staff"] = staff
        out["jobs"] = jobs
        out["flags_off"] = t.get("flags_off") or []
        totals = t.get("totals") or {}
        # staff.total from totals.staff (fallback len(staff)); active from totals.working.
        out["metrics"]["staff"]["total"] = int(totals.get("staff") or len(staff))
        out["metrics"]["staff"]["active"] = int(totals.get("working") or 0)
    except Exception:
        pass

    # ---- 2) automation_health: jobs rollup + queue + heartbeat ----
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        hjobs = h.get("jobs") or []
        total = len(hjobs)
        ok = sum(1 for j in hjobs if j.get("status") == "ok")
        # issues = overdue + last_failed + never_ran-but-due. health() only emits
        # never_ran once a job is actually due (not-yet-due → scheduled_off), so a
        # plain status-set membership count is correct (no extra due-filter needed).
        issues = sum(
            1 for j in hjobs if j.get("status") in ("overdue", "last_failed", "never_ran")
        )
        out["metrics"]["jobs"] = {"total": total, "ok": ok, "issues": issues}

        q = h.get("queue") or {}
        # Clamp redis-down sentinel (-1) to 0 so it never surfaces on the dashboard.
        out["metrics"]["queue"] = {
            "depth": max(0, int(q.get("celery", 0) or 0)),
            "dlq": max(0, int(q.get("dlq", 0) or 0)),
        }
        # heartbeat: health() has no heartbeat object → derive. up = jobs that are
        # neither overdue nor never_ran (i.e. have a live recent beat).
        overdue = len(h.get("overdue") or [])
        never_ran = len(h.get("never_ran") or [])
        out["metrics"]["heartbeat"] = {
            "up": max(0, total - overdue - never_ran),
            "total": total,
        }
    except Exception:
        pass

    # ---- 3) llm_metrics: ok_rate + primary provider ----
    try:
        from app.platform import llm_metrics

        st = llm_metrics.stats(1000) or {}
        fb = float(st.get("fallback_or_fail_rate") or 0.0)
        out["metrics"]["llm"]["ok_rate"] = round(1.0 - fb, 2)
        provs = st.get("providers") or {}
        if isinstance(provs, dict) and provs:
            # most-used provider by call count
            primary = max(
                provs.items(),
                key=lambda kv: int((kv[1] or {}).get("calls", 0) or 0),
            )[0]
            out["metrics"]["llm"]["primary"] = str(primary) or "mistral"
    except Exception:
        pass

    # ---- 4) activation: ready_for_paid + blocker count (async helper, never-raises) ----
    try:
        from app.api.activation import get_activation_summary

        a = await get_activation_summary() or {}
        # ready_for_paid: prefer the paid-customer flag, fall back to launch-ready.
        ready = bool(
            a.get("ready_for_first_paid_customer")
            or a.get("production_ready")
            or a.get("ready_for_launch")
        )
        out["activation"] = {
            "ready_for_paid": ready,
            "blockers": int(a.get("blocker_count") or 0),
        }
    except Exception:
        pass

    # ---- 5) eval_gate: status + regression (derived from recent_decisions) ----
    try:
        from app.agents import eval_gate as _eval_gate

        s = _eval_gate.summary() or {}
        rec = s.get("recent_decisions") or {}
        rejects = int(rec.get("reject") or 0)
        enabled = bool(s.get("enabled"))
        regression = rejects > 0
        # green = recording on + no recent rejects; warn = recent rejects present;
        # neutral = not recording yet (observe-only / no baseline).
        if rejects:
            status = "warn"
        elif enabled:
            status = "green"
        else:
            status = "neutral"
        out["eval_gate"] = {"status": status, "regression": regression}
    except Exception:
        pass

    # ---- 6) runs: total + running (process/flow runs) ----
    try:
        from app.agents import flow_dispatch

        runs = flow_dispatch.list_runs(50) or []
        running = sum(1 for r in runs if r.get("status") == "running")
        out["metrics"]["runs"] = {"total": len(runs), "running": running}
    except Exception:
        pass

    return out


__all__ = ["router"]
