"""Tests for the 10-state operational taxonomy (Wave 7 §3 deliverable)."""

from __future__ import annotations

import time

import pytest

from app.platform.operational_state import (
    DEFAULT_FRESHNESS,
    OperationalState,
    StateContract,
    classify,
    evaluate_entity,
)


def test_classify_unknown_when_credential_absent():
    s = classify(entity_class="email_poll", credential_present=False, env_flag_on=True)
    assert s == OperationalState.UNKNOWN


def test_classify_registered_when_config_present_no_heartbeat():
    s = classify(entity_class="agent_execution", registered=True, env_flag_on=False)
    assert s == OperationalState.REGISTERED


def test_classify_configured_when_env_flag_on_no_run():
    s = classify(entity_class="smartflo_idle", env_flag_on=True, credential_present=True)
    assert s == OperationalState.CONFIGURED


def test_classify_connected_with_recent_heartbeat():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,  # 5s ago
    )
    assert s == OperationalState.CONNECTED


def test_classify_verified_working_with_success_count():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,
        last_success_at=time.time() - 10.0,
        success_count=3,
    )
    assert s == OperationalState.VERIFIED_WORKING


def test_classify_running_when_running_now_no_success():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        is_running_now=True,
        success_count=0,
    )
    assert s == OperationalState.RUNNING


def test_classify_blocked_overrides_everything():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,
        last_success_at=time.time() - 10.0,
        success_count=5,
        is_running_now=True,
        is_blocked=True,
    )
    assert s == OperationalState.BLOCKED


def test_classify_failed_overrides_blocked():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,
        is_blocked=True,
        is_failed_terminal=True,
    )
    assert s == OperationalState.FAILED


def test_classify_degraded():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,
        is_degraded=True,
    )
    assert s == OperationalState.DEGRADED


def test_classify_stale_when_heartbeat_old():
    s = classify(
        entity_class="agent_execution",
        env_flag_on=True,
        credential_present=True,
        last_heartbeat_at=time.time() - 3600.0,  # 1h ago, freshness 2 min
    )
    assert s == OperationalState.STALE


def test_classify_fallback_unknown_when_nothing_matches():
    s = classify(
        entity_class="agent_execution",
        registered=False,
    )
    assert s == OperationalState.UNKNOWN


def test_evaluate_entity_returns_state_contract():
    c = evaluate_entity(
        entity_id="test_1",
        entity_class="agent_execution",
        source_system="automation_orchestrator",
        env_flag="TYPESAFE_INTAKE_GATE",
        credential_present=False,
    )
    assert isinstance(c, StateContract)
    assert c.state == OperationalState.UNKNOWN.value
    assert c.entity_id == "test_1"
    assert c.source_system == "automation_orchestrator"
    assert c.freshness_seconds == DEFAULT_FRESHNESS["agent_execution"]


def test_evaluate_entity_runs_only_after_heartbeat():
    c = evaluate_entity(
        entity_id="test_2",
        entity_class="agent_execution",
        source_system="automation_orchestrator",
        env_flag="TYPESAFE_INTAKE_GATE",
        credential_present=True,
        last_heartbeat_at=time.time() - 5.0,
        success_count=2,
        last_success_at=time.time() - 7.0,
    )
    assert c.state == OperationalState.VERIFIED_WORKING.value
    assert c.expected_next_run_at is not None
    assert c.expected_next_run_at > c.heartbeat_at


def test_state_contract_to_dict_round_trip():
    c = evaluate_entity(
        entity_id="test_3",
        entity_class="agent_execution",
        source_system="automation_orchestrator",
    )
    d = c.to_dict()
    assert d["entity_id"] == "test_3"
    assert "state" in d
    assert "freshness_seconds" in d


def test_no_state_ever_defaults_to_running():
    """Per §3 directive: missing data must NEVER default to healthy."""
    s = classify(entity_class="agent_execution", registered=False)
    assert s != OperationalState.RUNNING
    assert s != OperationalState.VERIFIED_WORKING
    assert s != OperationalState.CONNECTED


def test_no_state_ever_defaults_to_connected():
    """Without heartbeat, state must NOT be CONNECTED."""
    s = classify(entity_class="agent_execution", registered=True, env_flag_on=True)
    assert s != OperationalState.CONNECTED
    assert s != OperationalState.VERIFIED_WORKING


def test_evaluate_entity_with_env_flag_unset():
    """env_flag reads from os.environ at call-time (not capture-time)."""
    import os

    os.environ.pop("TEST_FLAG_XYZ", None)
    c = evaluate_entity(
        entity_id="x",
        entity_class="agent_execution",
        source_system="test",
        env_flag="TEST_FLAG_XYZ",
        credential_present=True,
    )
    assert c.state == OperationalState.REGISTERED.value

    os.environ["TEST_FLAG_XYZ"] = "1"
    c2 = evaluate_entity(
        entity_id="x",
        entity_class="agent_execution",
        source_system="test",
        env_flag="TEST_FLAG_XYZ",
        credential_present=True,
    )
    assert c2.state == OperationalState.CONFIGURED.value
    os.environ.pop("TEST_FLAG_XYZ", None)
