"""Tests for LeadGen per-lead routing (LeadGen-only scope).

Covers:
  - round-robin DID allocation across 5 enabled DIDs
  - campaign resolution (single LeadGen campaign)
  - Swara script scoping (LeadGen only — never LearningChain)
  - DND / opt-out / consent gating (all three must be green)
  - Follow-up derivation from outcome + retry budget
  - Pure routing: same inputs → same output (reproducible)
  - Project isolation: must refuse to route any non-LeadGen project
"""
from __future__ import annotations

import pytest

from app.platform.leadgen_lead_routing import (
    LEADGEN_DIDS,
    FollowUpKind,
    Outcome,
    perform_consent_checks,
    resolve_campaign,
    resolve_swara_script_id,
    round_robin_did,
    route_lead,
)


def test_round_robin_did_returns_5_dids():
    seen = set()
    for i in range(50):
        seen.add(round_robin_did(i))
    assert seen == set(LEADGEN_DIDS)
    assert len(LEADGEN_DIDS) == 5


def test_round_robin_did_cycles():
    seq = [round_robin_did(i) for i in range(10)]
    # First 5 unique, then repeats
    assert len(set(seq[:5])) == 5
    assert seq[5] == seq[0]
    assert seq[9] == seq[4]


def test_round_robin_did_rejects_negative():
    with pytest.raises(ValueError):
        round_robin_did(-1)


def test_resolve_campaign_default():
    assert resolve_campaign(None) == "leadgen_default_outbound"
    assert resolve_campaign("") == "leadgen_default_outbound"
    assert resolve_campaign("instagram_dm") == "leadgen_default_outbound"


def test_resolve_swara_script_rejects_non_leadgen():
    with pytest.raises(ValueError):
        resolve_swara_script_id("learningchain_default_outbound")


def test_resolve_swara_script_accepts_leadgen():
    sid = resolve_swara_script_id("leadgen_default_outbound")
    assert sid.startswith("swara_script__leadgen_ai__")
    assert sid.endswith("__v1")


def test_consent_check_passed_when_all_green():
    c = perform_consent_checks(
        has_consent_record=True,
        dnd_registry_match=False,
        opt_out_registry_match=False,
    )
    assert c.passed is True
    assert c.reasons_to_block == []


def test_consent_check_blocks_when_consent_missing():
    c = perform_consent_checks(
        has_consent_record=False,
        dnd_registry_match=False,
        opt_out_registry_match=False,
    )
    assert c.passed is False
    assert "consent_record_missing" in c.reasons_to_block


def test_consent_check_blocks_when_dnd_set():
    c = perform_consent_checks(
        has_consent_record=True,
        dnd_registry_match=True,
        opt_out_registry_match=False,
    )
    assert c.passed is False
    assert "dnd_registry_hit" in c.reasons_to_block


def test_consent_check_blocks_when_opt_out_set():
    c = perform_consent_checks(
        has_consent_record=True,
        dnd_registry_match=False,
        opt_out_registry_match=True,
    )
    assert c.passed is False
    assert "opt_out_registry_hit" in c.reasons_to_block


def test_route_lead_blocks_on_missing_consent():
    consent = perform_consent_checks(
        has_consent_record=False,
        dnd_registry_match=False,
        opt_out_registry_match=False,
    )
    r = route_lead(rr_index=0, lead_source=None, consent=consent)
    assert r.project == "leadgen_ai"
    assert r.can_dial is False
    assert "consent_missing" in r.reasons_to_block


def test_route_lead_passes_when_consent_green():
    consent = perform_consent_checks(
        has_consent_record=True,
        dnd_registry_match=False,
        opt_out_registry_match=False,
    )
    r = route_lead(rr_index=0, lead_source=None, consent=consent)
    assert r.can_dial is True
    assert r.did in LEADGEN_DIDS
    assert r.campaign == "leadgen_default_outbound"
    assert r.swara_script_id.startswith("swara_script__leadgen_ai__")


def test_route_lead_did_round_robin_deterministic():
    consent = perform_consent_checks(True, False, False)
    # Same input twice → same output (pure routing)
    a = route_lead(rr_index=7, lead_source="instagram_dm", consent=consent)
    b = route_lead(rr_index=7, lead_source="instagram_dm", consent=consent)
    assert a.did == b.did
    assert a.campaign == b.campaign
    assert a.swara_script_id == b.swara_script_id


def test_route_lead_5_dids_distributed_across_50_leads():
    consent = perform_consent_checks(True, False, False)
    counts = dict.fromkeys(LEADGEN_DIDS, 0)
    for i in range(50):
        r = route_lead(rr_index=i, lead_source=None, consent=consent)
        counts[r.did] += 1
    # Each DID gets exactly 10 (50/5)
    for did, n in counts.items():
        assert n == 10, f"DID {did} got {n} leads (expected 10)"


def test_follow_up_connected_routes_to_manual_review():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.CONNECTED,
        retry_budget_remaining=2,
    )
    # Connected != revenue. Don't push to RETRY. Manual review waits for CDR.
    assert r.follow_up == FollowUpKind.MANUAL_REVIEW


def test_follow_up_invalid_routes_to_suppress():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.INVALID,
    )
    # INVALID = DND / consent / opt-out → SUPPRESS (no retry, no revenue)
    assert r.follow_up == FollowUpKind.SUPPRESS


def test_follow_up_no_answer_with_budget_routes_to_same_day_retry():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.NO_ANSWER,
        retry_budget_remaining=2,
    )
    assert r.follow_up == FollowUpKind.RETRY_SAME_DAY


def test_follow_up_no_answer_no_budget_routes_to_next_day():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.NO_ANSWER,
        retry_budget_remaining=0,
    )
    assert r.follow_up == FollowUpKind.RETRY_NEXT_DAY


def test_follow_up_error_routes_to_manual_review():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.ERROR,
    )
    assert r.follow_up == FollowUpKind.MANUAL_REVIEW


def test_follow_up_busy_uses_budget_when_available():
    consent = perform_consent_checks(True, False, False)
    r = route_lead(
        rr_index=0, lead_source=None, consent=consent,
        outcome_for_follow_up=Outcome.BUSY,
        retry_budget_remaining=1,
    )
    assert r.follow_up == FollowUpKind.RETRY_SAME_DAY


def test_route_lead_never_returns_learningchain_script():
    """Project isolation invariant: even under weird inputs, the script_id
    MUST stay inside LeadGen's namespace. LearningChain scripts never surface."""
    consent = perform_consent_checks(True, False, False)
    for i in range(20):
        for src in (None, "", "instagram", "linkedin", "whatsapp"):
            r = route_lead(rr_index=i, lead_source=src, consent=consent)
            assert "learningchain" not in r.swara_script_id.lower()
            assert "leadgen_ai" in r.swara_script_id


def test_route_lead_project_is_always_leadgen():
    consent = perform_consent_checks(True, False, False)
    for i in range(10):
        r = route_lead(rr_index=i, lead_source=None, consent=consent)
        assert r.project == "leadgen_ai"
