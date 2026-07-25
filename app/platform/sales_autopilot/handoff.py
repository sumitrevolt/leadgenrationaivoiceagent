"""Sales Autopilot payment / onboarding / first-value handoff adapters.

These are thin ADAPTERS to the platform's EXISTING activation/onboarding paths — this
engine never rebuilds billing or CRM, never fakes a payment, and never auto-activates.
Each function records a durable handoff intent and (best-effort) points at the existing
path so a human/owner completes it. Publishing stays approval-gated separately. Never
raises.
"""

from __future__ import annotations

from typing import Any

from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def payment_reminder(prospect_id: str) -> dict[str, Any]:
    """Record a payment-reminder handoff. Gated by the payment-reminder kill switch.

    Points at the existing manual-UPI /start path; never mutates billing. Owner kill
    ``owner_payment_mutation`` also blocks. Returns an intent record. Never raises.
    """
    out: dict[str, Any] = {"prospect_id": str(prospect_id), "kind": "payment_reminder"}
    try:
        pol = _policy_mod.get_policy()
        if pol.kill("payment_reminders"):
            out["action"] = "blocked"
            out["reason"] = "payment_reminders_killed"
            return out
        try:
            from app.platform.owner_os import kill_engaged

            if kill_engaged("owner_payment_mutation"):
                out["action"] = "blocked"
                out["reason"] = "owner_payment_mutation_killed"
                return out
        except Exception:
            pass
        _store.record_attempt(
            {
                "idempotency_key": f"sap_payrem_{prospect_id}",
                "prospect_id": str(prospect_id),
                "channel": "handoff",
                "step": "payment_reminder",
                "status": "handoff_recorded",
                "target_path": "/start",
            }
        )
        out["action"] = "handoff_recorded"
        out["target_path"] = "/start"  # existing manual-UPI activation path
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.handoff] payment_reminder failed: %s", e)
        out["action"] = "error"
        out["error"] = str(e)[:120]
        return out


def to_onboarding(prospect_id: str, *, client_id: str | None = None) -> dict[str, Any]:
    """Record an onboarding handoff for a converted prospect.

    Does NOT auto-onboard: it records the intent and references the existing
    ``staff_jobs.onboard_client`` path so the owner (or an explicitly-enabled onboarding
    flow) completes it. Never enqueues on its own. Never raises.
    """
    out: dict[str, Any] = {"prospect_id": str(prospect_id), "kind": "onboarding"}
    try:
        _store.mark_status(prospect_id, _store.STATUS_CONVERTED, converted_client_id=client_id)
        _store.record_attempt(
            {
                "idempotency_key": f"sap_onboard_{prospect_id}",
                "prospect_id": str(prospect_id),
                "channel": "handoff",
                "step": "onboarding",
                "status": "handoff_recorded",
                "client_id": client_id,
                "target_path": "app.tasks.staff_jobs.onboard_client",
            }
        )
        out["action"] = "handoff_recorded"
        out["target"] = "app.tasks.staff_jobs.onboard_client"
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.handoff] to_onboarding failed: %s", e)
        out["action"] = "error"
        out["error"] = str(e)[:120]
        return out


def first_value(prospect_id: str) -> dict[str, Any]:
    """Record a first-value (seed content) handoff intent for a new customer.

    References the existing ``staff_jobs.seed_first_week`` path; does not run it. Content
    publishing remains approval-gated by the existing content-approval queue. Never raises.
    """
    out: dict[str, Any] = {"prospect_id": str(prospect_id), "kind": "first_value"}
    try:
        _store.record_attempt(
            {
                "idempotency_key": f"sap_firstvalue_{prospect_id}",
                "prospect_id": str(prospect_id),
                "channel": "handoff",
                "step": "first_value",
                "status": "handoff_recorded",
                "target_path": "app.tasks.staff_jobs.seed_first_week",
            }
        )
        out["action"] = "handoff_recorded"
        out["target"] = "app.tasks.staff_jobs.seed_first_week"
        out["note"] = "publishing stays approval-gated (content_approval queue)"
        return out
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("[sales_autopilot.handoff] first_value failed: %s", e)
        out["action"] = "error"
        out["error"] = str(e)[:120]
        return out


__all__ = ["payment_reminder", "to_onboarding", "first_value"]
