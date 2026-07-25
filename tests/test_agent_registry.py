"""Contract + reconciliation tests for the canonical Agent Runtime Contract
registry (app/platform/agent_registry.py).

These are the Phase-A acceptance tests: they assert the registry reconciles the
five previously-scattered sources into ONE truth and encodes the §5 compliance
gates as data. These tests import only pure/light modules and do not require a
DB or a running app.

NOTE (2026-07-21): "INERT" previously appeared here and in the module docstring
of agent_registry.py. That was wrong — the registry IS load-bearing at runtime
(agent_runtime.evaluate_policy L507/L516/L521 blocks RED-lane dispatch off it).
The tests below are therefore SAFETY tests, not documentation tests: if
test_cold_outbound_voice_is_red_and_hard_off or
test_lane_distribution_matches_scorecard_shape fails, cold outbound calling may
have become dispatchable. Do not "fix" such a failure by relaxing the assertion.
"""

from __future__ import annotations

import pytest

from app.platform import agent_registry as ar


def test_registry_builds_and_validates_clean():
    """The whole point: validate_registry() must be empty (no drift/contract gap)."""
    problems = ar.validate_registry()
    assert problems == [], "reconciliation problems:\n" + "\n".join(problems)


def test_canonical_count_is_31():
    reg = ar.build_registry()
    assert len(reg) == ar.CANONICAL_COUNT == 31


def test_every_staff_member_has_exactly_one_contract():
    from app.platform.team import STAFF

    reg = ar.build_registry()
    assert set(reg.keys()) == set(STAFF.keys())


def test_every_contract_has_required_governance_fields():
    reg = ar.build_registry()
    for aid, c in reg.items():
        assert c.team in {"platform", "marketing", "voice"}, aid
        assert c.lane in {"GREEN", "AMBER", "RED"}, aid
        assert c.autonomy.startswith("L"), aid
        assert c.trigger_types, f"{aid} has no trigger"
        assert c.kill_switches and "owner_all_agents" in c.kill_switches, aid
        assert c.escalation, aid
        assert c.test_ref, aid
        assert c.customer_contact_cap_day >= 0, aid


def test_boss_coordinator_contract():
    """Boss (manager) is the coordinator: reasoning, GREEN, may not do RED directly."""
    c = ar.get_contract("manager")
    assert c is not None
    assert c.name == "Boss"
    assert c.reasoning is True
    assert c.lane == "GREEN"
    assert c.autonomy == "L2_INTERNAL"
    assert "bypass_specialist_policy" in c.prohibited
    assert "perform_red_action_directly" in c.prohibited


def test_cold_outbound_voice_is_red_and_hard_off():
    """§5 invariant: platform_dial cold outbound is HARD-OFF. Swara/Ananya = RED."""
    for aid in ("swara", "ananya"):
        c = ar.get_contract(aid)
        assert c is not None
        assert c.lane == "RED", aid
        assert c.default_mode == ar.HARD_OFF, aid
    swara = ar.get_contract("swara")
    assert "platform_dial" in swara.kill_switches
    assert any("cold_outbound" in p for p in swara.prohibited)


def test_inbound_voice_separable_from_cold_outbound():
    """Riya (inbound) + Raksha (escalation) are enable-able independently of cold calls."""
    riya = ar.get_contract("riya")
    raksha = ar.get_contract("raksha")
    assert riya.default_mode == ar.INBOUND_READY
    assert riya.lane == "AMBER"  # inbound customer-facing, not RED cold-calling
    assert "fabricate_human_availability" in raksha.prohibited


def test_no_amber_or_red_agent_defaults_to_live():
    reg = ar.build_registry()
    for aid, c in reg.items():
        if c.lane in ("AMBER", "RED"):
            assert c.default_mode != ar.LIVE, f"{aid} ({c.lane}) must not start LIVE"


def test_escalation_targets_resolve():
    reg = ar.build_registry()
    valid = set(reg.keys()) | {"owner"}
    for aid, c in reg.items():
        assert c.escalation in valid, f"{aid} -> {c.escalation}"


def test_lane_distribution_matches_scorecard_shape():
    """Sanity: RED is a small set (calling), the bulk is GREEN internal."""
    s = ar.summary()
    lanes = s["by_lane"]
    assert lanes.get("RED", 0) == 2  # swara, ananya (cold outbound)
    assert lanes.get("GREEN", 0) >= 15  # majority internal/draft
    assert lanes.get("AMBER", 0) >= 6  # customer-outreach set


def test_control_plane_is_not_a_counted_persona():
    assert ar.CONTROL_PLANE["counts_toward_workforce"] is False
    reg = ar.build_registry()
    assert ar.CONTROL_PLANE["id"] not in reg


def test_known_drifts_documented():
    """Remaining reconciliation contradictions stay recorded (blog alias drift FIXED)."""
    loci = {d["locus"] for d in ar.KNOWN_DRIFTS}
    assert not any("ALIAS_TO_MEMBER['blog']" in x for x in loci)
    assert any("SCORECARD" in x.upper() for x in loci)
    for d in ar.KNOWN_DRIFTS:
        assert d["canonical"], d["locus"]


def test_blog_canonical_owner_is_isha_not_ravi():
    """JOB_META + ALIAS_TO_MEMBER agree: blog owner = isha."""
    from app.platform.agent_controls import ALIAS_TO_MEMBER

    assert ALIAS_TO_MEMBER.get("blog") == "isha"
    isha = ar.get_contract("isha")
    assert "blog" in isha.jobs
    ravi = ar.get_contract("ravi")
    assert "blog" not in ravi.jobs  # ravi = embedded SEO sub-engine, not blog owner


def test_reasoning_agents_are_the_expected_small_set():
    reg = ar.build_registry()
    reasoning = {aid for aid, c in reg.items() if c.reasoning}
    # honest: only a handful do genuine LLM reasoning; the rest are deterministic
    assert reasoning == {"manager", "swara", "ananya", "riya", "vikram", "isha"}
