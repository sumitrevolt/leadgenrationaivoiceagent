"""Customer Delivery Assurance — read-only missed-deliverable detection (GREEN lane).

WHY (2026-07-19, Agent-OS upgrade slice 1 — priority: customer delivery): the
delivery-assurance building blocks all existed but were never composed. Detection
was scattered and none of it returned an admin-readable, evidence-backed answer to
the one question that matters for a paying customer: *"which paid customers are NOT
getting what they paid for, why, and what's the proof?"*
  - ``customer_delivery.find_undelivered_paid_clients()`` = boolean detector (raw dicts)
  - ``product_one_delivery.run_health_and_recovery_sweep()`` = side-effects + counts only
  - ``product_one_delivery.customer_delivery_status(cid)`` = rich per-customer object,
    but per-single-customer (no filtered aggregate)
  - ``delivery_ledger.recent_counts/timeline`` = evidence, not wired into a report

This module composes those existing primitives into the ONE missing thing: a
structured, tenant-safe, evidence-backed list of missed / at-risk paid customers.

SAFETY CONTRACT (enforced by tests):
  - PURE READ. Calls only read functions. Never sends WhatsApp/email, never mutates
    ``delivery_state`` or any customer record. Actual delivery sends stay in the
    existing ``AUTO_DELIVER_VALUE``-gated ``customer_delivery.deliver_client_value``
    path, which this module does NOT touch.
  - TENANT-SAFE. Every id is normalised through ``clients_store.canonical_client_id``
    (resolves the billing/login alias -> marketing id, e.g. d79d690f61b3 -> jiya-makeover)
    so a customer is never double-counted or mis-attributed.
  - NEVER RAISES. Every client is best-effort; one bad record cannot sink the scan.
  - VOICE-FREE. Imports no telephony / STT / TTS / call-runtime module; strictly
    marketing-domain (out of scope: the voice calling stack).

OBSERVABILITY: a scan emits ONE ``team.log_event`` under ``nikhil`` (Revenue Ops) —
an undelivered paid customer is revenue-leak / churn-risk, which is nikhil's lane —
so the run is visible on the existing team activity feed with a real owner (no new
persona invented). Escalation target for a missed item is the owner (human).

Lane: GREEN (read-only detection + report). Autonomy: L0/L1 (observe + recommend).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Observability owner for delivery-assurance runs. Revenue Ops owns "paid customer
# not getting value = revenue leak / churn risk". Kept as a module constant so the
# attribution is explicit and testable (NOT a new persona — one of the 31).
_OWNER_MEMBER = "nikhil"

# health_status values from customer_delivery_status that mean trouble.
_SEVERE = "red"
_AT_RISK = frozenset({"red", "yellow"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _canonical_id(cid: str) -> str:
    """Normalise any id/alias to the marketing client id. Never raises."""
    try:
        from app.marketing import clients_store

        return str(clients_store.canonical_client_id(cid) or cid or "").strip()
    except Exception:
        return str(cid or "").strip()


def _paid_active_clients() -> list[dict[str, Any]]:
    """Active clients that are delivery-eligible paid customers. Read-only."""
    try:
        from app.marketing import clients_store, customer_delivery

        out: list[dict[str, Any]] = []
        for c in clients_store.list_clients(status="active"):
            try:
                if customer_delivery.has_paid_evidence(c):
                    out.append(c)
            except Exception:
                # Fall back to the softer eligibility check; never drop silently.
                try:
                    if customer_delivery.is_paid_client(c):
                        out.append(c)
                except Exception:
                    continue
        return out
    except Exception as exc:
        logger.warning("delivery_assurance _paid_active_clients err: %s", exc)
        return []


def _evidence(cid: str) -> dict[str, Any]:
    """Ledger-backed proof for a client: windowed failure counts + last events.
    Read-only. Degrades to an empty-but-shaped dict on any error."""
    ev: dict[str, Any] = {"failures_24h": None, "value_events_7d": None, "last_events": []}
    try:
        from app.marketing import delivery_ledger

        try:
            rc = delivery_ledger.recent_counts(cid, hours=168) or {}
            ev["failures_24h"] = rc.get("failures_24h")
            ev["value_events_7d"] = rc.get("value_events_in_window")
        except Exception:
            pass
        try:
            tl = delivery_ledger.timeline(cid, limit=5) or []
            ev["last_events"] = [
                {
                    "event": e.get("event"),
                    "at": e.get("at") or e.get("created_at"),
                    "detail": (e.get("detail") or "")[:160],
                }
                for e in tl
            ]
        except Exception:
            pass
    except Exception as exc:
        logger.debug("delivery_assurance _evidence skip (%s): %s", cid, exc)
    return ev


def assess_client_delivery(client: dict[str, Any]) -> dict[str, Any]:
    """Structured, tenant-safe, evidence-backed delivery assessment for ONE paid
    client. Pure READ. Never raises — returns a shaped record even on partial
    failure (so one bad customer can't break the aggregate scan)."""
    raw_id = str((client or {}).get("id") or "").strip()
    cid = _canonical_id(raw_id) or raw_id
    rec: dict[str, Any] = {
        "canonical_id": cid,
        "raw_id": raw_id,
        "billing_ids": list((client or {}).get("billing_client_ids") or []),
        "business_name": (client or {}).get("business_name"),
        "plan": (client or {}).get("plan"),
        "delivery_state": (client or {}).get("delivery_state"),
        "missed": False,
        "at_risk": False,
        "severity": "unknown",
        "reasons": [],
        "health_score": None,
        "sla_hours_remaining": None,
        "deliverable_completion_pct": None,
        "mini_site_ready": False,
        "evidence": {},
        "escalation": "owner",
    }
    reasons: list[str] = []

    # never-delivered signal (does not require the heavier status derivation)
    try:
        from app.marketing import customer_delivery

        rec["mini_site_ready"] = bool(customer_delivery.mini_site_url(client))
        if not customer_delivery.is_delivered(client):
            reasons.append("value_not_yet_delivered")
    except Exception:
        pass

    # rich per-customer status (canonicalises id internally too) — read-only
    try:
        from app.marketing import product_one_delivery

        st = product_one_delivery.customer_delivery_status(cid, client) or {}
        if st.get("ok") is not False:
            health = str(st.get("health_status") or "").strip().lower()
            rec["severity"] = health or "unknown"
            rec["health_score"] = st.get("health_score")
            rec["sla_hours_remaining"] = st.get("sla_hours_remaining")
            rec["deliverable_completion_pct"] = st.get("deliverable_completion_pct")
            if st.get("delivery_state") is not None:
                rec["delivery_state"] = st.get("delivery_state")
            if health == _SEVERE:
                reasons.append("health_red")
            elif health in _AT_RISK:
                reasons.append("health_yellow")
            fa = st.get("failed_automations")
            if fa:
                reasons.append(f"failed_automations:{fa}")
            for r in st.get("health_reasons") or []:
                reasons.append(str(r)[:80])
        else:
            reasons.append("status_unavailable")
    except Exception as exc:
        logger.debug("delivery_assurance status skip (%s): %s", cid, exc)
        reasons.append("status_error")

    rec["evidence"] = _evidence(cid)
    if rec["evidence"].get("failures_24h"):
        reasons.append(f"ledger_failures_24h:{rec['evidence']['failures_24h']}")

    # de-dup reasons, keep order
    seen: set[str] = set()
    rec["reasons"] = [r for r in reasons if not (r in seen or seen.add(r))]

    sev = rec["severity"]
    rec["at_risk"] = bool(sev in _AT_RISK or "value_not_yet_delivered" in rec["reasons"])
    rec["missed"] = bool(
        sev == _SEVERE
        or "value_not_yet_delivered" in rec["reasons"]
        or (rec["evidence"].get("failures_24h") or 0)
    )
    return rec


def scan_missed_deliverables(limit: int = 100, include_healthy: bool = False) -> dict[str, Any]:
    """READ-ONLY aggregator: the structured, tenant-safe, evidence-backed list of
    paid customers whose delivery is missed / at-risk. AgentRunResult-shaped.

    No sends, no state mutation. Emits one observability event (nikhil). Never
    raises — returns a shaped record with status='error' + error string on failure.
    """
    run_id = str(uuid.uuid4())
    started = _now()
    result: dict[str, Any] = {
        "run_id": run_id,
        "agent_id": "delivery_assurance",
        "domain": "customer_success",
        "lane": "GREEN",
        "status": "success",
        "started_at": _iso(started),
        "completed_at": None,
        "latency_ms": 0,
        "checked": 0,
        "missed_count": 0,
        "at_risk_count": 0,
        "items": [],
        "error": None,
    }
    try:
        clients = _paid_active_clients()
        result["checked"] = len(clients)
        items: list[dict[str, Any]] = []
        for c in clients[: max(1, int(limit))]:
            rec = assess_client_delivery(c)
            if include_healthy or rec["missed"] or rec["at_risk"]:
                items.append(rec)
        # severest first: missed before at-risk, then lower completion first
        items.sort(
            key=lambda r: (
                0 if r["missed"] else 1,
                0 if r["at_risk"] else 1,
                (
                    r.get("deliverable_completion_pct")
                    if r.get("deliverable_completion_pct") is not None
                    else 999
                ),
            )
        )
        result["items"] = items
        result["missed_count"] = sum(1 for r in items if r["missed"])
        result["at_risk_count"] = sum(1 for r in items if r["at_risk"])
    except Exception as exc:
        logger.warning("delivery_assurance scan err: %s", exc)
        result["status"] = "error"
        result["error"] = str(exc)

    completed = _now()
    result["completed_at"] = _iso(completed)
    result["latency_ms"] = int((completed - started).total_seconds() * 1000)

    # observability — one team event under the revenue-ops owner (no new persona)
    try:
        from app.platform import team

        status = "ok" if result["status"] == "success" else "error"
        if result["missed_count"] or result["at_risk_count"]:
            status = "warn"
        detail = (
            f"delivery assurance: {result['missed_count']} missed / "
            f"{result['at_risk_count']} at-risk of {result['checked']} paid"
        )
        team.log_event(
            _OWNER_MEMBER,
            "delivery_assurance_scan",
            detail[:160],
            status=status,
            meta={
                "run_id": run_id,
                "missed": result["missed_count"],
                "at_risk": result["at_risk_count"],
                "checked": result["checked"],
            },
        )
    except Exception as exc:
        logger.debug("delivery_assurance observability skip: %s", exc)

    return result


def missed_deliverables_summary() -> dict[str, Any]:
    """Compact admin-readable summary (counts + minimal item view). Read-only."""
    scan = scan_missed_deliverables()
    return {
        "generated_at": scan["completed_at"],
        "checked": scan["checked"],
        "missed": scan["missed_count"],
        "at_risk": scan["at_risk_count"],
        "customers": [
            {
                "id": r["canonical_id"],
                "name": r["business_name"],
                "plan": r["plan"],
                "severity": r["severity"],
                "reasons": r["reasons"][:4],
                "completion_pct": r["deliverable_completion_pct"],
            }
            for r in scan["items"]
        ],
    }


__all__ = [
    "assess_client_delivery",
    "scan_missed_deliverables",
    "missed_deliverables_summary",
]
