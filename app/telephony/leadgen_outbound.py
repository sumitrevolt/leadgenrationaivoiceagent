"""LeadGen outbound wrapper — wires preflight + channel lease + retry budget
into a single call-attempt boundary.

Architecture (per owner directive):
  - Pure decision logic lives in ``app/platform/leadgen_daily_window.py``
    (preflight, channel ledger, retry ledger — SQLite-backed, durable).
  - This module is the THIN wire that ties preflight + Tata SmartFlo
    ``place_call`` + ack/release. It does NOT introduce a new orchestrator.
  - CallManager's existing outbound loop (``call_manager._process_call``)
    can call ``dispatch_leadgen_outbound(...)`` for LeadGen-bound calls;
    existing Vobiz / generic outbound flow remains untouched.

Safety (per owner directive — Unlimited FUP does NOT remove these):
  - per-call throttle (per-second, per-minute) — handled upstream by
    ``tata_smartflo_handler.PlaceCallThrottle``
  - per-lead retry budget (3/day, per (lead, channel, day)) — RetryLedger
  - per-day per-DID anti-abuse — ChannelLedger 5-channel cap
  - DND / opt-out / consent check — passed in by caller as booleans
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.platform.leadgen_daily_window import (
    ChannelLedger,
    RetryLedger,
    ack,
    evaluate_window,
    preflight,
)


@dataclass
class LeadGenOutboundRequest:
    """All inputs dispatch_leadgen_outbound needs from the worker."""

    lead_id: str
    channel_id: str                  # one of the 5 DIDs
    destination_number: str         # customer phone
    day: str                         # YYYY-MM-DD
    dnd_check_passed: bool
    consent_check_passed: bool


@dataclass
class LeadGenOutboundResult:
    """Outcome of a single dispatch attempt — never raises, always structured."""

    attempted_provider_request: bool
    status_code: int                 # 0 = blocked locally; >=200 = provider HTTP
    body: dict[str, Any]            # provider response or block reason
    channel_acquired: bool
    channel_released: bool
    retry_budget_consumed: bool
    follow_up_action: str
    preflight_reasons: list[str] = field(default_factory=list)
    window_reason: str = ""


async def dispatch_leadgen_outbound(
    request: LeadGenOutboundRequest,
    *,
    channel_ledger: ChannelLedger,
    retry_ledger: RetryLedger,
    place_call_fn,                  # async (to, customer_number, ...) -> dict
    now: datetime | None = None,
) -> LeadGenOutboundResult:
    """Single-call dispatch with preflight, provider call, ack/release.

    Never raises. Returns a structured result the caller can route to
    follow-up queue, retry ledger, or suppress.
    """
    # Step 1: preflight (window + capacity + retry + DND + consent).
    pf = preflight(
        channel_id=request.channel_id,
        lead_id=request.lead_id,
        day=request.day,
        dnd_check_passed=request.dnd_check_passed,
        consent_check_passed=request.consent_check_passed,
        channel_ledger=channel_ledger,
        retry_ledger=retry_ledger,
        now=now,
    )
    blocked = not pf.can_dial
    preflight_reasons = list(pf.reasons_to_block)
    window_reason = pf.window.reason

    if blocked:
        # No provider call. Slot may have been acquired — release it so we
        # don't leak a channel.
        if pf.channel_acquired:
            ack(request.channel_id, request.lead_id, (channel_ledger, retry_ledger))
        return LeadGenOutboundResult(
            attempted_provider_request=False,
            status_code=0,
            body={"error": "preflight_blocked", "reasons": preflight_reasons},
            channel_acquired=pf.channel_acquired,
            channel_released=pf.channel_acquired,  # we just released it above
            retry_budget_consumed=pf.retry_allowed,  # True means attempt was counted
            follow_up_action=_derive_block_follow_up(pf.reasons_to_block),
            preflight_reasons=preflight_reasons,
            window_reason=window_reason,
        )

    # Step 2: provider call (Tata SmartFlo place_call).
    provider_resp: dict[str, Any]
    try:
        provider_resp = await place_call_fn(request.destination_number)
    except Exception as exc:  # noqa: BLE001
        # Provider transport error — release channel, mark retry budget consumed.
        ack(request.channel_id, request.lead_id, (channel_ledger, retry_ledger))
        return LeadGenOutboundResult(
            attempted_provider_request=True,
            status_code=0,
            body={"error": f"provider_transport: {type(exc).__name__}: {exc}"},
            channel_acquired=True,
            channel_released=True,
            retry_budget_consumed=True,
            follow_up_action="manual_review",
            preflight_reasons=preflight_reasons,
            window_reason=window_reason,
        )

    # Step 3: release channel (the call attempt is over; outcome will be
    # determined by the webhook / CDR event, not by this synchronous call).
    ack(request.channel_id, request.lead_id, (channel_ledger, retry_ledger))

    status_code = int(provider_resp.get("status_code", 0))
    body = provider_resp.get("body", {})

    # Map provider response to a follow-up action.
    # Per owner directive: CONNECTED != revenue. Don't push to RETRY. Manual review
    # waits for CDR; revenue is verified collection, not call outcome.
    if status_code and 200 <= status_code < 300:
        if str(body.get("success", "")).lower() in ("true", "1", "yes"):
            follow_up = "manual_review"  # connected call → wait for CDR
        else:
            follow_up = "manual_review"  # queued successfully → wait for CDR
    elif status_code == 422:
        follow_up = "suppress"  # permanent schema/parameter error → don't retry
    elif status_code == 401 or status_code == 403:
        follow_up = "manual_review"  # auth / entitlement issue — human review
    else:
        # 4xx/5xx: retry if budget remains, else next-day
        retry_remaining = retry_ledger.remaining(request.lead_id, request.channel_id, request.day)
        follow_up = "retry_same_day" if retry_remaining > 0 else "retry_next_day"

    return LeadGenOutboundResult(
        attempted_provider_request=True,
        status_code=status_code,
        body=body,
        channel_acquired=True,
        channel_released=True,
        retry_budget_consumed=True,
        follow_up_action=follow_up,
        preflight_reasons=preflight_reasons,
        window_reason=window_reason,
    )


def _derive_block_follow_up(reasons: list[str]) -> str:
    """Map a preflight block to a follow-up action."""
    if any("post-20:00" in r for r in reasons):
        return "retry_next_day"
    if any("outside" in r for r in reasons):
        return "retry_next_day"
    if any("retry_budget_exhausted" in r for r in reasons):
        return "retry_next_day"
    if "channel_unavailable" in " ".join(reasons) or "cap_reached" in " ".join(reasons):
        # Cap reached → don't retry same DID; surface to operator.
        return "manual_review"
    if "dnd_check_failed" in reasons or "consent_check_failed" in reasons:
        return "suppress"
    return "manual_review"
