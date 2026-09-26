"""LeadGen per-lead routing — LeadGen-only (LearningChain removed from scope).

Each consented lead has a deterministic routing decision:
  - project = LEADGEN_AI (single project, hard-coded; no mix with LearningChain)
  - campaign = looked up from consent + lead.source; default `leadgen_default_outbound`
  - DID = round-robin allocation across the 5 enabled DIDs (capacity-aware)
  - Swara script = project/campaign-typed (never LearningChain's scripts)
  - outcome = driven by webhook CDR (no premature "revenue" claim)
  - follow-up = derived from outcome; not revenue until verified collection

Per owner directive:
  - Unlimited FUP per Tata partner dashboard = monthly FUP cap removed.
    Per-call throttle, DND-check, fraud-suppression, consent check remain.
  - 5 channels max concurrent (matches the 5 DIDs visible in CloudPhone).
  - Project isolation: do NOT mix LeadGen's customer data or scripts with
    any other project's data/scripts.

This module is PURE — no I/O, no API calls. It's consumed by the call
scheduler which feeds it lead context + consent state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


PROJECT = "leadgen_ai"  # single project, hard-coded; no project mixing


class Outcome(str, Enum):
    """Outcome buckets. NOT revenue labels — revenue requires verified collection."""
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    REJECTED = "rejected"
    CONNECTED = "connected"
    VOICEMAIL = "voicemail"
    INVALID = "invalid"     # DND / opt-out / no consent
    ERROR = "error"          # transport / 5xx / 4xx


class FollowUpKind(str, Enum):
    NONE = "none"
    RETRY_SAME_DAY = "retry_same_day"      # within today's budget
    RETRY_NEXT_DAY = "retry_next_day"      # push to tomorrow
    MANUAL_REVIEW = "manual_review"        # human queue
    SUPPRESS = "suppress"                  # DND / consent / out-of-FUP-policy


@dataclass(frozen=True)
class ConsentCheck:
    """Result of consent + DND + opt-out checks (all three must be green)."""
    consent_present: bool
    dnd_clear: bool
    opt_out_clear: bool
    reasons_to_block: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.consent_present
            and self.dnd_clear
            and self.opt_out_clear
            and not self.reasons_to_block
        )


@dataclass(frozen=True)
class LeadRouting:
    """Pure routing decision. All fields immutable so a route is reproducible."""
    project: str
    campaign: str
    did: str
    swara_script_id: str
    follow_up: FollowUpKind
    reasons_to_block: list[str] = field(default_factory=list)
    consent_check: ConsentCheck | None = None

    @property
    def can_dial(self) -> bool:
        return (
            self.consent_check is not None
            and self.consent_check.passed
            and not self.reasons_to_block
        )


# 5 DIDs visible in CloudPhone /manage-did-numbers (v3 evidence).
LEADGEN_DIDS: tuple[str, ...] = (
    "+918065606872",
    "+918065606874",
    "+918065606875",
    "+918065606877",
    "+918065606881",
)


# Round-robin index — picked externally to keep this module pure.
def round_robin_did(rr_index: int) -> str:
    """Pure: maps rr_index → one of the 5 DIDs. Caller maintains the index."""
    if rr_index < 0:
        raise ValueError("rr_index must be >= 0")
    return LEADGEN_DIDS[rr_index % len(LEADGEN_DIDS)]


def resolve_campaign(lead_source: str | None) -> str:
    """Project/campaign naming — single campaign default, source-scoped overrides allowed later.

    For now: every LeadGen lead uses the default campaign. Per-lead source tagging
    is captured in CDR for analytics but does NOT split into separate campaigns
    (would dilute the 5-channel concurrent allocation).
    """
    if not lead_source:
        return "leadgen_default_outbound"
    # Reserved future splits: must be approved by owner before activation.
    return "leadgen_default_outbound"


def resolve_swara_script_id(campaign: str) -> str:
    """Project-scoped Swara script lookup. NEVER returns LearningChain scripts."""
    if campaign != "leadgen_default_outbound":
        # Defensive: anything outside LeadGen defaults is rejected.
        raise ValueError(f"campaign {campaign!r} not in LeadGen scope")
    return "swara_script__leadgen_ai__v1"


def derive_follow_up(outcome: Outcome, retry_budget_remaining: int) -> FollowUpKind:
    """Map call outcome + remaining retry budget to a follow-up action.

    Per owner directive: do NOT count pending payments as revenue. This
    function does NOT consider payment state at all — only call outcomes.
    """
    if outcome == Outcome.INVALID:
        return FollowUpKind.SUPPRESS
    if outcome == Outcome.CONNECTED:
        # Connected ≠ revenue. Revenue is verified collection, not call
        # outcome. Don't push to MANUAL_REVIEW as 'qualified' — wait for CDR.
        return FollowUpKind.MANUAL_REVIEW
    if outcome in (Outcome.NO_ANSWER, Outcome.BUSY, Outcome.REJECTED, Outcome.VOICEMAIL):
        if retry_budget_remaining > 0:
            return FollowUpKind.RETRY_SAME_DAY
        return FollowUpKind.RETRY_NEXT_DAY
    if outcome == Outcome.ERROR:
        return FollowUpKind.MANUAL_REVIEW
    return FollowUpKind.NONE


def route_lead(
    *,
    rr_index: int,
    lead_source: str | None,
    consent: ConsentCheck,
    outcome_for_follow_up: Outcome | None = None,
    retry_budget_remaining: int = 0,
) -> LeadRouting:
    """Pure: build a LeadRouting for one lead.

    ``consent`` must be passed; the caller runs DND/opt-out/consent gates
    BEFORE this function. If consent fails, the returned routing still
    has `can_dial=False` so the call scheduler can skip it.
    """
    blocked: list[str] = []
    if not consent.consent_present:
        blocked.append("consent_missing")
    if not consent.dnd_clear:
        blocked.append("dnd_set")
    if not consent.opt_out_clear:
        blocked.append("opt_out_set")

    campaign = resolve_campaign(lead_source)
    did = round_robin_did(rr_index)
    script_id = resolve_swara_script_id(campaign)
    follow_up = (
        derive_follow_up(outcome_for_follow_up, retry_budget_remaining)
        if outcome_for_follow_up is not None
        else FollowUpKind.NONE
    )

    return LeadRouting(
        project=PROJECT,
        campaign=campaign,
        did=did,
        swara_script_id=script_id,
        follow_up=follow_up,
        reasons_to_block=blocked,
        consent_check=consent,
    )


def perform_consent_checks(
    has_consent_record: bool,
    dnd_registry_match: bool,
    opt_out_registry_match: bool,
) -> ConsentCheck:
    """Caller passes pre-resolved lookup results; this module stays pure.

    Real implementation will fetch consent + DND + opt-out state from
    upstream services — that's owner / VPS-gated work. For now the contract
    is: caller looks up, this function aggregates.
    """
    reasons: list[str] = []
    if not has_consent_record:
        reasons.append("consent_record_missing")
    if dnd_registry_match:
        reasons.append("dnd_registry_hit")
    if opt_out_registry_match:
        reasons.append("opt_out_registry_hit")
    return ConsentCheck(
        consent_present=has_consent_record,
        dnd_clear=not dnd_registry_match,
        opt_out_clear=not opt_out_registry_match,
        reasons_to_block=reasons,
    )
