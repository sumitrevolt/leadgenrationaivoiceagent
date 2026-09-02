"""Sales Autopilot eligibility — the ONE canonical gate function.

:func:`evaluate` returns a decision in
``ELIGIBLE | INELIGIBLE | DEFERRED | OWNER_EXCEPTION_REQUIRED`` plus machine-readable
``reason_codes``. Every gate is fail-closed: any error, missing data, or ambiguity
resolves to the *safer* outcome (INELIGIBLE/DEFERRED/OWNER_EXCEPTION_REQUIRED), never a
silent ELIGIBLE. This is the single place send + scheduler consult before any outreach.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.platform.sales_autopilot import policy as _policy_mod
from app.platform.sales_autopilot import store as _store
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Decisions
ELIGIBLE = "ELIGIBLE"
INELIGIBLE = "INELIGIBLE"
DEFERRED = "DEFERRED"
OWNER_EXCEPTION_REQUIRED = "OWNER_EXCEPTION_REQUIRED"

# Steps
STEP_INITIAL = "initial"
STEP_FOLLOWUP_1 = "followup_1"
STEP_FOLLOWUP_2 = "followup_2"

_IST = timezone(timedelta(hours=5, minutes=30))


def _now_ist() -> datetime:
    return datetime.now(_IST)


def _result(decision: str, *reasons: str, **extra: Any) -> dict[str, Any]:
    return {"decision": decision, "reason_codes": list(reasons), **extra}


def _canonical_suppressed(
    prospect: dict[str, Any], rec: dict[str, Any], channel: str, contact: str
) -> bool:
    """Consult the canonical suppression ledger. FAIL-CLOSED.

    An unavailable suppression ledger must block the send, not permit it: the
    cost of a false block is a delayed message, the cost of a false allow is
    contacting someone who explicitly told us to stop.
    """
    try:
        from app.platform import email_unsub

        pid = str(prospect.get("id") or rec.get("id") or "")
        if channel == "whatsapp":
            return email_unsub.is_contact_suppressed(
                phone=contact, prospect_id=pid, channel="whatsapp"
            )
        return email_unsub.is_contact_suppressed(email=contact, prospect_id=pid, channel="email")
    except Exception as e:  # fail-closed
        logger.warning("[sales_autopilot.eligibility] suppression check failed: %s", e)
        return True


def _owner_kill(name: str) -> bool:
    try:
        from app.platform.owner_os import kill_engaged

        return bool(kill_engaged(name))
    except Exception:
        # Fail-closed for compliance-sensitive kills: if we cannot read the kill board,
        # assume the killed state for outbound channels.
        return True


def _is_suppressed(phone: str) -> bool:
    if not phone:
        return False
    try:
        from app.marketing import wa_campaign_runner

        return bool(wa_campaign_runner.is_suppressed(phone))
    except Exception:
        # Fail-closed: cannot confirm suppression cleanliness ⇒ treat as suppressed.
        return True


def _channel_contact(prospect: dict[str, Any], channel: str) -> str:
    if channel == "whatsapp":
        return str(prospect.get("phone") or "")
    if channel == "email":
        return str(prospect.get("email") or "")
    return ""


def _icp_ok(prospect: dict[str, Any], pol: _policy_mod.Policy) -> bool:
    icp = pol.get("icp") or {}
    niches = [str(n).lower() for n in (icp.get("niches") or [])]
    cities = [str(c).lower() for c in (icp.get("cities") or [])]
    if niches and str(prospect.get("niche") or "").lower() not in niches:
        return False
    if cities and str(prospect.get("city") or "").lower() not in cities:
        return False
    return True


def evaluate(
    prospect: dict[str, Any],
    *,
    channel: str,
    step: str = STEP_INITIAL,
    pol: _policy_mod.Policy | None = None,
    now_ist: datetime | None = None,
) -> dict[str, Any]:
    """Canonical eligibility decision. Never raises.

    Order is deliberate: hard compliance/kill gates first, then identity/consent, then
    channel/ICP, then rate/time. The Estique manual-owner guard is a HARD early gate.
    """
    try:
        pol = pol or _policy_mod.get_policy()
        channel = (channel or "").lower()
        prospect = prospect or {}
        pid = str(prospect.get("id") or prospect.get("prospect_id") or "")
        now_ist = now_ist or _now_ist()

        # 1. Master engine gate.
        if not pol.enabled:
            return _result(INELIGIBLE, "engine_disabled")

        # 2. Owner global kills (all agents / schedulers) — fail-closed.
        if _owner_kill("owner_all_agents"):
            return _result(INELIGIBLE, "owner_all_agents_killed")
        if _owner_kill("owner_schedulers"):
            return _result(INELIGIBLE, "owner_schedulers_killed")

        # 3. Channel-specific owner kill.
        if channel == "whatsapp" and _owner_kill("owner_whatsapp_outbound"):
            return _result(INELIGIBLE, "owner_whatsapp_killed")
        if channel == "email" and _owner_kill("owner_bulk_email"):
            return _result(INELIGIBLE, "owner_bulk_email_killed")

        # 4. Per-stage engine kill switches.
        if step == STEP_INITIAL and pol.kill("new_outreach"):
            return _result(INELIGIBLE, "new_outreach_killed")
        if step in (STEP_FOLLOWUP_1, STEP_FOLLOWUP_2) and pol.kill("followups"):
            return _result(INELIGIBLE, "followups_killed")

        # 5. Channel enabled in policy?
        if channel not in [str(c).lower() for c in (pol.get("channels") or [])]:
            return _result(INELIGIBLE, "channel_not_in_policy", channel=channel)

        # 6. ESTIQUE / manual-owner-confirmed HARD guard.
        #    Owner already hand-contacted → NEVER auto-send the initial touch again.
        est_match = (
            pid == _store.ESTIQUE_ID
            or _store.digits(prospect.get("phone", "")) == _store.digits(_store.ESTIQUE_PHONE)
            or str(prospect.get("email", "")).lower() == _store.ESTIQUE_EMAIL
        )
        owner_confirmed = (
            est_match
            or _store.is_owner_confirmed(pid)
            or bool(prospect.get("manual_owner_confirmed"))
        )
        if owner_confirmed and step == STEP_INITIAL:
            return _result(
                OWNER_EXCEPTION_REQUIRED,
                "manual_owner_confirmed_initial_blocked",
                owner_confirmed=True,
            )

        # 7. Consent / opt-out state.
        rec = _store.get_prospect(pid) or {}
        status = rec.get("status") or prospect.get("status") or _store.STATUS_NEW
        if status == _store.STATUS_REMOVED:
            return _result(INELIGIBLE, "customer_removed")
        if status == _store.STATUS_OPTED_OUT or prospect.get("opted_out"):
            return _result(INELIGIBLE, "opted_out")
        if not (prospect.get("consent_basis") or rec.get("consent_basis")):
            # First-contact needs a lawful basis (DPDP purpose/consent). Fail-closed.
            return _result(INELIGIBLE, "no_consent_basis")

        # 8. Stop-on-reply / stop-on-payment.
        if pol.get("stop_on_reply", True) and (
            status == _store.STATUS_REPLIED or int(rec.get("reply_count", 0)) > 0
        ):
            return _result(INELIGIBLE, "already_replied")
        if pol.get("stop_on_payment", True) and status in (
            _store.STATUS_CONVERTED,
            getattr(_store, "STATUS_AWAITING_PAYMENT", "awaiting_payment"),
        ):
            return _result(INELIGIBLE, "already_converted")

        # 9. Channel contact present + suppression (fail-closed).
        contact = _channel_contact(prospect, channel)
        if not contact:
            return _result(INELIGIBLE, "no_channel_contact", channel=channel)
        if channel == "whatsapp" and _is_suppressed(contact):
            return _result(INELIGIBLE, "suppressed")
        # Canonical suppression authority — covers BOTH channels. The check above
        # only consults the WhatsApp campaign list, so an explicit opt-out (or a
        # hard bounce) recorded in the suppression ledger did not block this
        # engine at all, on either channel.
        if _canonical_suppressed(prospect, rec, channel, contact):
            return _result(INELIGIBLE, "suppressed_canonical", channel=channel)

        # 10. ICP match.
        if not _icp_ok(prospect, pol):
            return _result(INELIGIBLE, "icp_mismatch")

        # 11. Idempotency — step already completed?
        steps_done = list(rec.get("steps_done") or prospect.get("steps_done") or [])
        step_key = f"{step}_{channel}"
        if step_key in steps_done or step in steps_done:
            return _result(INELIGIBLE, "step_already_done", step=step_key)

        # 12. Follow-up cap.
        if step in (STEP_FOLLOWUP_1, STEP_FOLLOWUP_2):
            if int(rec.get("followup_count", 0)) >= pol.max_followups():
                return _result(INELIGIBLE, "followup_cap_reached")

        # 13. IST business-hours window (defer, not reject).
        hrs = pol.get("ist_hours") or {}
        start = int(hrs.get("start", 9))
        end = int(hrs.get("end", 19))
        if not (start <= now_ist.hour < end):
            return _result(DEFERRED, "outside_business_hours", ist_hour=now_ist.hour)

        # 14. Daily caps (defer).
        if step == STEP_INITIAL:
            cap = int((pol.get("caps") or {}).get("daily_new_outreach", 20))
            if _store.attempts_today(channel=channel) >= cap:
                return _result(DEFERRED, "daily_new_outreach_cap")
        else:
            cap = int((pol.get("caps") or {}).get("daily_followups", 40))
            if _store.attempts_today() >= cap:
                return _result(DEFERRED, "daily_followup_cap")

        return _result(ELIGIBLE, "ok", channel=channel, step=step)
    except Exception as e:  # pragma: no cover - defensive; fail-closed
        logger.warning("[sales_autopilot.eligibility] evaluate failed: %s", e)
        return _result(INELIGIBLE, "eligibility_error")


__all__ = [
    "ELIGIBLE",
    "INELIGIBLE",
    "DEFERRED",
    "OWNER_EXCEPTION_REQUIRED",
    "STEP_INITIAL",
    "STEP_FOLLOWUP_1",
    "STEP_FOLLOWUP_2",
    "evaluate",
]
