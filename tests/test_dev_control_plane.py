"""In-tree coverage for the dev control plane core (pure layers).

Restores the missing dev-control test coverage: state machine, ownership
locks, gateway routing/admission with a FAKE provider (no real LLM call),
usage-row building, provider-health snapshot, and the hard invariant gate.
Hermetic: no app.main import, no network, no DB.
"""

from __future__ import annotations

import asyncio
import time
from decimal import Decimal

import pytest

from app.dev_control import locks
from app.dev_control.gateway import invoke
from app.dev_control.health import healthy_providers, provider_health_snapshot
from app.dev_control.registry import MODEL_CATALOG, route_preview
from app.dev_control.service import (
    InvalidTransition,
    TaskState,
    admit_cost,
    create_task_record,
    transition,
)
from app.dev_control.usage import build_usage_rows


# ---------------------------------------------------------------- state machine
def test_happy_path_transitions_are_legal():
    record = {"state": TaskState.PROPOSED.value}
    for target in (
        TaskState.APPROVED,
        TaskState.QUEUED,
        TaskState.CLAIMED,
        TaskState.RUNNING,
        TaskState.REVIEW_REQUIRED,
        TaskState.TESTS_RUNNING,
        TaskState.STAGING_READY,
        TaskState.STAGING_DEPLOYED,
        TaskState.PRODUCTION_APPROVAL_REQUIRED,
        TaskState.PRODUCTION_DEPLOYED,
        TaskState.DELIVERY_VERIFICATION,
        TaskState.COMPLETED,
    ):
        transition(record, target)
    assert record["state"] == TaskState.COMPLETED.value


def test_gate_skipping_transition_is_rejected():
    record = {"state": TaskState.QUEUED.value}
    with pytest.raises(InvalidTransition):
        transition(record, TaskState.PRODUCTION_DEPLOYED)
    assert record["state"] == TaskState.QUEUED.value  # unchanged on failure


def test_terminal_states_allow_nothing():
    for terminal in (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED):
        with pytest.raises(InvalidTransition):
            transition({"state": terminal.value}, TaskState.QUEUED)


def test_create_task_record_is_idempotent():
    a = create_task_record("objective x", "idem-plane-1")
    b = create_task_record("objective x", "idem-plane-1")
    assert a["task_id"] == b["task_id"]
    assert a["reused"] is False and b["reused"] is True


# ---------------------------------------------------------------- ownership locks
def test_lock_conflict_and_release():
    lock = locks.InMemoryOwnershipLock()
    assert lock.acquire("w1", ["app/a.py", "app/b.py"])["acquired"] is True
    conflict = lock.acquire("w2", ["app/b.py"])
    assert conflict["acquired"] is False and conflict["conflict"] == ["app/b.py"]
    lock.release("w1", ["app/a.py", "app/b.py"])
    assert lock.acquire("w2", ["app/b.py"])["acquired"] is True


def test_lock_expires_after_ttl():
    lock = locks.InMemoryOwnershipLock()
    assert lock.acquire("w1", ["app/x.py"], ttl=0)["acquired"] is True
    time.sleep(0.01)
    assert lock.acquire("w2", ["app/x.py"], ttl=60)["acquired"] is True  # stale lock reclaimed


def test_overlapping_is_pure_set_math():
    assert locks.overlapping(["a", "b"], ["b", "c"]) == ["b"]
    assert locks.overlapping([], ["b"]) == []


# ---------------------------------------------------------------- routing + admission
def test_sensitive_routing_never_leaves_local():
    rp = route_preview(task_type="code", sensitivity="sensitive", complexity="high")
    assert rp["selected_provider"] == "local"
    assert all(c == "local" for c in rp["candidates"])


def test_admit_cost_denies_over_task_budget():
    out = admit_cost(
        provider="claude",
        estimated_input_tokens=1_000_000,
        estimated_output_tokens=100_000,
        task_budget_usd=Decimal("0.01"),
        daily_remaining_usd=Decimal("100"),
    )
    assert out["allowed"] is False and out["reason"] == "task_budget_exceeded"


def test_admit_cost_unknown_provider_denied():
    out = admit_cost(
        provider="nope",
        estimated_input_tokens=10,
        estimated_output_tokens=10,
        task_budget_usd=Decimal("1"),
        daily_remaining_usd=Decimal("1"),
    )
    assert out["allowed"] is False and out["reason"] == "unknown_provider"


def test_gateway_success_with_fake_provider_records_cost():
    async def fake_call(provider, model, system, messages, **kw):
        return "diff --git a/x b/x", provider, {"prompt_tokens": 100, "completion_tokens": 50}

    result = asyncio.run(
        invoke(
            task_id="t-1",
            task_type="code",
            sensitivity="normal",
            complexity="medium",
            system="s",
            messages=[{"role": "user", "content": "fix"}],
            max_tokens=200,
            task_budget_usd=Decimal("1"),
            daily_remaining_usd=Decimal("5"),
            provider_call=fake_call,
        )
    )
    assert result["ok"] is True
    assert "actual_cost_usd" in result["usage"]


def test_gateway_falls_through_on_provider_error():
    async def broken_call(provider, model, system, messages, **kw):
        raise RuntimeError("boom-429")

    result = asyncio.run(
        invoke(
            task_id="t-2",
            task_type="code",
            sensitivity="normal",
            complexity="medium",
            system="s",
            messages=[{"role": "user", "content": "fix"}],
            max_tokens=100,
            task_budget_usd=Decimal("1"),
            daily_remaining_usd=Decimal("5"),
            provider_call=broken_call,
        )
    )
    assert result["ok"] is False
    attempted = {a["provider"]: a for a in result["attempted"]}
    assert "local" in attempted and "boom-429" in attempted["local"].get("error", "")


# ---------------------------------------------------------------- usage ledger rows
def test_usage_rows_capture_attempts_and_success():
    rows = build_usage_rows(
        "t-3",
        {
            "ok": True,
            "provider": "local",
            "model": "local-coding",
            "attempted": [{"provider": "deepseek", "skipped": "unconfigured"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "actual_cost_usd": "0"},
        },
    )
    outcomes = [r["outcome"] for r in rows]
    assert outcomes == ["skipped_unconfigured", "success"]


def test_usage_rows_capture_budget_denial():
    rows = build_usage_rows(
        "t-4",
        {
            "ok": False,
            "reason": "task_budget_exceeded",
            "selected_provider": "claude",
            "attempted": [],
            "usage": {"estimated_cost_usd": "9.99"},
        },
    )
    assert rows[-1]["outcome"] == "budget_denied"
    assert rows[-1]["cost_usd"] == Decimal("9.99")


# ---------------------------------------------------------------- provider health
def test_health_snapshot_merges_catalog_and_breaker():
    def fake_breaker(alias):
        return {
            "state": "cooling" if alias == "deepseek" else "closed",
            "cooldown_remaining_s": 30,
            "trip_streak": 2,
        }

    rows = provider_health_snapshot(breaker_lookup=fake_breaker)
    by_name = {r["provider_name"]: r for r in rows}
    assert set(by_name) == set(MODEL_CATALOG)
    assert by_name["deepseek"]["circuit_breaker_state"] == "cooling"
    assert by_name["local"]["cost_class"] == "free"
    for row in rows:
        for field in (
            "provider_name",
            "model_name",
            "task_capabilities",
            "privacy_class",
            "cost_class",
            "enabled",
            "circuit_breaker_state",
            "last_health_check",
        ):
            assert field in row


def test_healthy_providers_excludes_cooling_and_disabled():
    snapshot = [
        {"provider_name": "a", "enabled": True, "circuit_breaker_state": "closed"},
        {"provider_name": "b", "enabled": True, "circuit_breaker_state": "cooling"},
        {"provider_name": "c", "enabled": False, "circuit_breaker_state": "closed"},
    ]
    assert healthy_providers(snapshot) == ["a"]


# ---------------------------------------------------------------- hard invariant gate
def test_dev_control_gate_invariants_hold():
    from scripts.dev_control_gate import invariants

    violations = invariants(env={})
    assert violations == [], f"invariant gate reported: {violations}"
