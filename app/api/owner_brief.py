"""Owner Brief — single-call operational intelligence for the owner admin.

GET /api/admin/owner-brief → unified operational snapshot answering:
  - What is happening right now?
  - What failed?
  - What needs owner action?
  - What produced revenue?
  - What should happen next?

Composes EXISTING modules (today_overview, automation_health, command_center,
paid_activations, upi_payments, customer_delivery) — never raises, partial data
is fine.  require_admin-gated.

Mounted in app/main.py via include_router.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Owner Brief"])


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Severity classification (§19 Failure Taxonomy)
# ---------------------------------------------------------------------------
_SEVERITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3, "info": 4}


def _classify_exception(item: dict) -> str:
    """Map a problem/finding to a severity level (P0-P3)."""
    text = str(item.get("kya") or item.get("symptom") or item.get("label") or "").lower()
    if any(w in text for w in ("security", "secret", "data leak", "breach")):
        return "p0"
    if any(w in text for w in ("fail", "fallback", "crash", "broken", "down", "error", "stuck")):
        return "p1"
    if any(w in text for w in ("overdue", "late", "slow", "backlog", "retry")):
        return "p2"
    if any(w in text for w in ("warn", "degraded", "approaching")):
        return "p3"
    return "info"


# ---------------------------------------------------------------------------
# Builder — one composite dict, every sub-block in its own try/except
# ---------------------------------------------------------------------------
def _build_owner_brief() -> dict[str, Any]:
    """Build the owner brief. Never raises — partial data is fine."""
    out: dict[str, Any] = {
        "ok": True,
        "at": _now_iso(),
        "headline": "",
        # §5 Business
        "revenue": {
            "mrr": 0,
            "paid_customers": 0,
            "paid_today": 0,
            "activations_today": 0,
            "pending_payments": 0,
            "invoices_pending": 0,
        },
        # §9 Customer journey
        "customers": {
            "total": 0,
            "active": 0,
            "stuck_in_setup": 0,
            "receiving_value": 0,
            "at_risk": 0,
            "pending_approvals": 0,
            "failed_automation": 0,
        },
        # §4 Automation
        "automation": {
            "jobs_total": 0,
            "jobs_ok": 0,
            "jobs_overdue": 0,
            "jobs_failed": 0,
            "queue_depth": 0,
            "dlq_depth": 0,
            "dead_depth": 0,
            "runs_today": 0,
        },
        # §15 AI Workforce
        "workforce": {
            "total": 0,
            "active": 0,
            "actions_today": 0,
            "errors_today": 0,
        },
        # §6 Exception-driven admin
        "exceptions": [],
        # §37 Next action
        "next_actions": [],
    }

    # ---- 1) Revenue ----
    try:
        from app.api.admin_dashboard_builders import _build_command_center, _has_paid_evidence

        cc = _build_command_center() or {}
        summary = cc.get("summary") or {}
        revenue = cc.get("revenue") or {}
        out["revenue"]["mrr"] = int(revenue.get("mrr_total") or 0)
        out["revenue"]["paid_customers"] = int(summary.get("paying_customers") or 0)
        out["revenue"]["pending_payments"] = int(summary.get("pending_approvals_total") or 0)
        out["customers"]["total"] = int(summary.get("total_customers") or 0)
        out["customers"]["active"] = int(summary.get("total_customers") or 0)
        out["customers"]["stuck_in_setup"] = int(summary.get("stuck_in_setup") or 0)
        out["customers"]["receiving_value"] = int(summary.get("receiving_value") or 0)
        out["customers"]["at_risk"] = int(summary.get("at_risk_count") or 0)
        out["customers"]["failed_automation"] = int(summary.get("failed_automation_count") or 0)
        out["customers"]["pending_approvals"] = int(summary.get("pending_approvals_total") or 0)
    except Exception:
        pass

    # ---- 2) Paid today (ledger-backed) ----
    try:
        from app.billing import paid_activations

        paid = paid_activations.daily_paid_activations()
        out["revenue"]["paid_today"] = int(paid.get("paid_today") or 0)
        out["revenue"]["activations_today"] = int(paid.get("activations_today") or 0)
    except Exception:
        pass

    # ---- 3) Pending UPI payments (owner queue) ----
    try:
        from app.platform import upi_payments

        actionable = upi_payments.list_actionable() or []
        out["revenue"]["pending_payments"] = len(actionable)
        # Surface actionable items as exceptions requiring owner decision
        for row in actionable[:5]:
            out["exceptions"].append(
                {
                    "type": "owner_decision",
                    "category": "payment",
                    "label": f"UPI payment pending: {row.get('plan', '?')} from {row.get('payer_name', 'unknown')}",
                    "detail": f"Ref: {row.get('upi_ref', '?')} · ID: {row.get('id', '?')}",
                    "action": "Approve/Reject in Admin → UPI queue",
                    "severity": "p1",
                }
            )
    except Exception:
        pass

    # ---- 4) Automation health ----
    try:
        from app.platform import automation_health

        h = automation_health.health() or {}
        jobs = h.get("jobs") or []
        out["automation"]["jobs_total"] = len(jobs)
        out["automation"]["jobs_ok"] = sum(1 for j in jobs if j.get("status") == "ok")
        overdue = h.get("overdue") or []
        out["automation"]["jobs_overdue"] = len(overdue)
        failed_jobs = [j for j in jobs if j.get("status") == "last_failed"]
        out["automation"]["jobs_failed"] = len(failed_jobs)

        q = h.get("queue") or {}
        out["automation"]["queue_depth"] = int(q.get("celery") or 0)
        out["automation"]["dlq_depth"] = int(q.get("dlq") or 0)
        out["automation"]["dead_depth"] = int(q.get("dead") or 0)

        # Surface overdue jobs as exceptions
        for j in overdue[:3]:
            out["exceptions"].append(
                {
                    "type": "automation",
                    "category": "job_overdue",
                    "label": f"Job overdue: {j.get('job', '?')}",
                    "detail": f"Last run: {j.get('last_run', 'never')}",
                    "action": "Check worker/scheduler health",
                    "severity": "p2",
                }
            )

        # Surface failed jobs
        for j in failed_jobs[:3]:
            out["exceptions"].append(
                {
                    "type": "automation",
                    "category": "job_failed",
                    "label": f"Job failed: {j.get('job', '?')}",
                    "detail": f"Last run: {j.get('last_run', '?')}",
                    "action": "Check error logs + retry",
                    "severity": "p1",
                }
            )

        # Surface DLQ
        if out["automation"]["dlq_depth"] > 0:
            out["exceptions"].append(
                {
                    "type": "automation",
                    "category": "dlq_backlog",
                    "label": f"DLQ has {out['automation']['dlq_depth']} tasks",
                    "detail": "Dead-letter queue has unprocessed failed tasks",
                    "action": "Inspect DLQ → manual retry or root-cause fix",
                    "severity": "p2",
                }
            )

        # Surface dead tasks
        if out["automation"]["dead_depth"] > 0:
            out["exceptions"].append(
                {
                    "type": "automation",
                    "category": "dead_tasks",
                    "label": f"{out['automation']['dead_depth']} tasks dead/exhausted",
                    "detail": "Retry budget exhausted — these tasks will not auto-recover",
                    "action": "Root-cause investigation required",
                    "severity": "p1",
                }
            )
    except Exception:
        pass

    # ---- 5) Workforce / AI staff ----
    try:
        from app.platform import team

        ts = team.team_status() or {}
        members = ts.get("members") or []
        totals = ts.get("totals") or {}
        out["workforce"]["total"] = len(members)
        out["workforce"]["active"] = int(totals.get("active_members") or 0)
        out["workforce"]["actions_today"] = int(totals.get("actions_today") or 0)
        out["workforce"]["errors_today"] = int(totals.get("errors_today") or 0)

        if out["workforce"]["errors_today"] > 5:
            out["exceptions"].append(
                {
                    "type": "workforce",
                    "category": "high_errors",
                    "label": f"{out['workforce']['errors_today']} agent errors today",
                    "detail": f"Out of {out['workforce']['actions_today']} total actions",
                    "action": "Check agent health in Team Dashboard",
                    "severity": "p2",
                }
            )
    except Exception:
        pass

    # ---- 6) Today overview (headline + problems) ----
    try:
        from app.platform import today_overview

        ov = today_overview.build() or {}
        out["headline"] = str(ov.get("headline") or "")
        problems = ov.get("problems") or []
        # Classify and add to exceptions
        for p in problems[:10]:
            sev = _classify_exception(p)
            out["exceptions"].append(
                {
                    "type": "platform",
                    "category": "problem",
                    "label": p.get("kya", ""),
                    "detail": p.get("fix", ""),
                    "action": p.get("fix", "Investigate"),
                    "severity": sev,
                }
            )
    except Exception:
        pass

    # ---- 7) At-risk customers (from command_center health) ----
    try:
        from app.api.admin_dashboard_builders import _build_command_center

        cc = _build_command_center() or {}
        for cust in cc.get("per_customer") or []:
            health = cust.get("health") or {}
            state = health.get("state", "")
            if state in ("at_risk", "blocked"):
                out["exceptions"].append(
                    {
                        "type": "customer",
                        "category": "health_" + state,
                        "label": f"Customer {cust.get('id', '?')}: {health.get('label_hi', state)}",
                        "detail": health.get("reason", ""),
                        "action": health.get("next_action_hint", "Review customer"),
                        "severity": "p1" if state == "at_risk" else "p2",
                    }
                )
    except Exception:
        pass

    # ---- 8) Sort exceptions by severity ----
    out["exceptions"].sort(key=lambda e: _SEVERITY_ORDER.get(e.get("severity", "info"), 99))

    # ---- 9) Next actions (derived from exceptions + state) ----
    if out["revenue"]["pending_payments"] > 0:
        out["next_actions"].append(
            {
                "priority": 1,
                "action": "Review pending UPI payments",
                "detail": f"{out['revenue']['pending_payments']} payment(s) awaiting approval",
            }
        )
    if out["customers"]["at_risk"] > 0:
        out["next_actions"].append(
            {
                "priority": 2,
                "action": "Address at-risk customers",
                "detail": f"{out['customers']['at_risk']} customer(s) need attention",
            }
        )
    if out["automation"]["jobs_overdue"] > 0:
        out["next_actions"].append(
            {
                "priority": 3,
                "action": "Investigate overdue automation jobs",
                "detail": f"{out['automation']['jobs_overdue']} job(s) overdue",
            }
        )
    if out["customers"]["stuck_in_setup"] > 0:
        out["next_actions"].append(
            {
                "priority": 4,
                "action": "Complete customer onboarding",
                "detail": f"{out['customers']['stuck_in_setup']} customer(s) stuck in setup",
            }
        )
    if out["customers"]["pending_approvals"] > 0:
        out["next_actions"].append(
            {
                "priority": 5,
                "action": "Process pending content approvals",
                "detail": f"{out['customers']['pending_approvals']} approval(s) waiting",
            }
        )
    if not out["next_actions"]:
        out["next_actions"].append(
            {
                "priority": 99,
                "action": "All clear — no immediate actions required",
                "detail": "System operating normally",
            }
        )

    # ---- 10) Overall status ----
    p0_count = sum(1 for e in out["exceptions"] if e.get("severity") == "p0")
    p1_count = sum(1 for e in out["exceptions"] if e.get("severity") == "p1")
    if p0_count > 0:
        out["status"] = "red"
    elif p1_count > 0:
        out["status"] = "amber"
    else:
        out["status"] = "green"

    return out


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------
@router.get("/admin/owner-brief")
async def owner_brief(_user=Depends(require_admin)) -> dict[str, Any]:
    """Single-call owner operational intelligence. Never raises (partial data OK).

    Returns a unified snapshot answering:
    - What is happening right now? (headline, workforce, automation)
    - What failed? (exceptions by severity)
    - What needs owner action? (next_actions)
    - What produced revenue? (revenue metrics)
    - What should happen next? (prioritized next_actions)
    """
    return _build_owner_brief()


__all__ = ["router"]
