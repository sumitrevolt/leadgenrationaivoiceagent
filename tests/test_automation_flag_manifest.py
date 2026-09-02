"""Typed AUTOMATION_FLAGS manifest — explicit kinds; no mass enablement."""

from __future__ import annotations

from app.api.automation_flags import AUTOMATION_FLAGS
from app.platform.automation_flag_manifest import (
    FlagGovernance,
    FlagLifecycle,
    FlagValueKind,
    build_manifest,
    describe_flag,
    enrich_flag_row,
)


def test_manifest_covers_every_registry_entry():
    m = build_manifest()
    assert m["count"] == len(AUTOMATION_FLAGS)
    assert m["unique"] == len(AUTOMATION_FLAGS)
    assert m["count"] >= 300
    allowed = {k.value for k in FlagValueKind}
    for name in AUTOMATION_FLAGS:
        assert name in m["flags"]
        assert m["flags"][name]["kind"] in allowed
        assert m["flags"][name]["governance"] in {g.value for g in FlagGovernance}


def test_no_entry_left_without_explicit_kind_and_governance():
    m = build_manifest()
    for name, row in m["flags"].items():
        assert row["kind"], name
        assert row["governance"], name
        # legacy unclassified string must not appear
        assert row["governance"] != "unclassified"
        assert row["kind"] != "unknown"


def test_safety_invariants_classified():
    for name in (
        "REPLY_AUTO_SEND_HARD_OFF",
        "ALLOW_TOS_SCRAPE",
        "UPI_AUTO_ACTIVATE",
        "SALES_AUTOPILOT_WHATSAPP_ENABLED",
        "VOICE_LAUNCH_KILL",
    ):
        meta = describe_flag(name)
        assert meta.governance == FlagGovernance.SAFETY_INVARIANT
        assert meta.lifecycle == FlagLifecycle.SAFETY_INVARIANT
        assert meta.kind == FlagValueKind.BOOLEAN


def test_platform_dial_daily_is_boolean_not_cap():
    dial = describe_flag("PLATFORM_DIAL_DAILY")
    assert dial.kind == FlagValueKind.BOOLEAN
    assert dial.governance == FlagGovernance.PRODUCTION_PROVEN
    limit = describe_flag("PLATFORM_DIAL_LIMIT")
    assert limit.kind == FlagValueKind.CAPACITY_LIMIT
    assert limit.governance == FlagGovernance.CONFIGURATION_NOT_SWITCH


def test_secret_names_never_expose_as_plain_switch_semantics():
    row = enrich_flag_row("LITELLM_MASTER_KEY", {"set": True, "on": True, "value": "***"})
    assert row["secret"] is True
    assert row["kind"] == FlagValueKind.SECRET.value
    assert row["governance"] == FlagGovernance.SECRET_NEVER_EXPOSE.value
    assert row["switch_on"] is None


def test_non_boolean_switch_on_is_null():
    row = enrich_flag_row("VOICE_DAILY_CALL_CAP", {"set": True, "on": True, "value": "100"})
    assert row["kind"] == FlagValueKind.CAPACITY_LIMIT.value
    assert row["switch_on"] is None
    assert row["configured"] is True


def test_external_agent_dual_gate_canary():
    for name in ("EXTERNAL_AGENT_ORCHESTRATOR", "EXTERNAL_AGENT_RUNNER"):
        assert describe_flag(name).governance == FlagGovernance.CANARY_ONLY


def test_new_registry_entry_without_override_is_reviewable_not_invented():
    """Drift: undeclared overlay still gets a kind; governance stays review."""
    meta = describe_flag("TOTALLY_FAKE_FLAG_FOR_CONTRACT_XYZ")
    assert meta.kind in FlagValueKind
    assert meta.governance == FlagGovernance.UNKNOWN_REQUIRES_REVIEW


def test_boolean_on_semantics_exclude_limits():
    m = build_manifest()
    # capacity/duration/url/secret must not be treated as switches in helpers
    for name in ("PLATFORM_DIAL_LIMIT", "SEARXNG_URL", "LITELLM_MASTER_KEY", "COUNCIL_TIMEOUT_S"):
        assert m["flags"][name]["kind"] != FlagValueKind.BOOLEAN.value


def test_high_risk_classifications_locked():
    assert describe_flag("ALLOW_TOS_SCRAPE").governance == FlagGovernance.SAFETY_INVARIANT
    assert describe_flag("UPI_AUTO_ACTIVATE").governance == FlagGovernance.SAFETY_INVARIANT
    assert (
        describe_flag("SALES_AUTOPILOT_WHATSAPP_ENABLED").governance
        == FlagGovernance.SAFETY_INVARIANT
    )
    assert describe_flag("REPLY_AUTO_SEND").governance == FlagGovernance.SAFETY_INVARIANT


def test_onboarding_and_builder_flags_are_canary_off():
    for name in ("ONBOARDING_PIPELINE", "FORM_BUILDER", "PROPOSAL_BUILDER"):
        meta = describe_flag(name)
        assert meta.kind == FlagValueKind.BOOLEAN
        assert meta.governance == FlagGovernance.CANARY_ONLY
        assert meta.default_hint == "0"
        assert name in AUTOMATION_FLAGS


def test_dunning_engine_is_owner_gated_not_safe_default():
    """Issue #307: retention dunning stays owner-gated / dormant."""
    meta = describe_flag("DUNNING_ENGINE")
    assert meta.kind == FlagValueKind.BOOLEAN
    assert meta.governance == FlagGovernance.OWNER_APPROVAL_REQUIRED
    assert meta.default_hint == "0"
