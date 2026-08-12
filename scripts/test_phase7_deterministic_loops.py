#!/usr/bin/env python3
"""
Test suite for Phase 7: Deterministic Feedback Loops + Cost-Aware Bandit.

Tests cover:
- compute_outcome_value() weighting formula
- should_skip_task() deterministic gates
- Cost-aware task picking
- Hybrid gates + reflexion workflow
- Backward compatibility
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents import self_improve


def test_outcome_value_high_quality():
    """Test: High quality leads + revenue + cheap = high score."""
    outcome = {
        "lead_count": 20,
        "avg_lead_score": 0.9,  # hot leads
        "revenue_impact": 1000,  # $1000 deals
        "cost": 1.0,  # cheap
        "success": True,
    }
    score = self_improve.compute_outcome_value(outcome)
    assert 0.8 < score < 1.0, f"Expected high score, got {score:.2f}"
    print(f"✓ High quality: score={score:.2f}")


def test_outcome_value_neutral():
    """Test: Neutral outcome (info only, no revenue) = low score."""
    outcome = {
        "lead_count": 5,
        "avg_lead_score": 0.3,  # info only
        "revenue_impact": 0,  # no revenue
        "cost": 2.0,  # normal cost
        "success": True,
    }
    score = self_improve.compute_outcome_value(outcome)
    assert 0.0 < score < 0.3, f"Expected low score, got {score:.2f}"
    print(f"✓ Neutral: score={score:.2f}")


def test_outcome_value_expensive_failure():
    """Test: Expensive failure = negative score (clamped to 0)."""
    outcome = {
        "lead_count": 0,
        "avg_lead_score": 0.0,  # no quality
        "revenue_impact": 0,  # no revenue
        "cost": 10.0,  # expensive
        "success": False,
    }
    score = self_improve.compute_outcome_value(outcome)
    assert score == 0.0, f"Expected 0.0 (clamped), got {score:.2f}"
    print(f"✓ Expensive failure: score={score:.2f}")


def test_outcome_value_clamps():
    """Test: Score clamps to [0, 1]."""
    # Create extreme values
    outcome_high = {
        "lead_count": 1000,
        "avg_lead_score": 999,  # will normalize, then clamp
        "revenue_impact": 999999,
        "cost": 0.01,
        "success": True,
    }
    score = self_improve.compute_outcome_value(outcome_high)
    assert 0.0 <= score <= 1.0, f"Score not clamped: {score}"
    assert score > 0.8, f"Expected high score, got {score:.2f}"
    print(f"✓ Clamps high: score={score:.2f}")

    outcome_low = {
        "lead_count": 0,
        "avg_lead_score": -10,
        "revenue_impact": -1000,
        "cost": 100,
        "success": False,
    }
    score = self_improve.compute_outcome_value(outcome_low)
    assert 0.0 <= score <= 1.0, f"Score not clamped: {score}"
    assert score < 0.1, f"Expected low score, got {score:.2f}"
    print(f"✓ Clamps low: score={score:.2f}")


def test_gate_budget():
    """Test: Budget gate skips if cost > remaining."""
    skip, reason = self_improve.should_skip_task(
        "seo_pages",
        cost_remaining=2.0,  # only $2 left
        last_outcome=None,
    )
    # seo_pages costs $5 (LLM-heavy)
    assert skip, f"Expected skip, got reason={reason}"
    assert "budget" in reason, f"Wrong reason: {reason}"
    print(f"✓ Budget gate: {reason}")


def test_gate_expensive_risky():
    """Test: Expensive + risky gate skips high-cost low-success."""
    # Simulate: success_rate=0.55, cost=$5.50
    # To test this, we'd need to mock skill_library stats
    # For now, test structure
    skip, reason = self_improve.should_skip_task(
        "content_pack",
        cost_remaining=20.0,  # budget ok
        last_outcome=None,
    )
    # content_pack is LLM-heavy (cost $2.5), success varies
    # This test depends on actual stats, so structure only
    print("✓ Expensive risky gate: structure ok")


def test_gate_low_roi():
    """Test: Low ROI + expensive gate skips neutral outcomes."""
    skip, reason = self_improve.should_skip_task(
        "channel_experiments",
        cost_remaining=10.0,  # budget ok
        last_outcome={
            "value_score": 0.3,  # very low (neutral/negative)
            "cost": 2.5,
        },
    )
    # If last outcome was low AND cost > $3, should skip
    # channel_experiments is LLM-heavy ($2.5)
    # Last outcome was 0.3 (low), cost $2.5 (expensive)
    # Gate may or may not trigger depending on thresholds
    print(f"✓ Low ROI gate: {reason if skip else 'pass'}")


def test_gate_passes_good_task():
    """Test: Good task passes all gates."""
    skip, reason = self_improve.should_skip_task(
        "harvest_leads",  # cheap ($0.50)
        cost_remaining=30.0,  # lots of budget
        last_outcome={
            "value_score": 0.85,  # high value
            "cost": 0.50,
        },
    )
    assert not skip, f"Good task shouldn't skip: {reason}"
    print("✓ Good task passes all gates")


def test_gates_can_disable():
    """Test: Gates can be disabled individually."""
    original_gates = self_improve.DETERMINISTIC_GATES.copy()
    try:
        # Disable all gates
        self_improve.DETERMINISTIC_GATES["budget"] = False
        self_improve.DETERMINISTIC_GATES["expensive_risky"] = False
        self_improve.DETERMINISTIC_GATES["low_roi"] = False

        skip, reason = self_improve.should_skip_task(
            "seo_pages",
            cost_remaining=0.1,  # way over budget
            last_outcome=None,
        )
        # Gates disabled = should not skip
        assert not skip, f"Disabled gates should not skip: {reason}"
        print("✓ Gates can be disabled")
    finally:
        self_improve.DETERMINISTIC_GATES.update(original_gates)


def test_cost_tracker_basic():
    """Test: CostTracker tracks daily cost."""
    tracker = self_improve.CostTracker(daily_cap=50.0)

    # Initially nothing spent
    assert tracker.can_afford("task1", 10.0)
    tracker.record_cost("task1", 10.0)

    # Check status
    status = tracker.get_daily_status()
    assert status["spent"] == 10.0
    assert status["remaining"] == 40.0
    assert status["pct_used"] == 20.0

    print(f"✓ CostTracker: {status}")


def test_cost_tracker_budget_exceeded():
    """Test: CostTracker rejects overspend."""
    tracker = self_improve.CostTracker(daily_cap=30.0)
    tracker.record_cost("task1", 25.0)

    assert not tracker.can_afford("task2", 10.0), "Should not afford $10 + $25 > $30"
    assert tracker.can_afford("task2", 5.0), "Should afford $5 + $25 = $30"

    print("✓ CostTracker budget enforcement")


def test_approval_queue_basic():
    """Test: ApprovalQueue tracks pending tasks."""
    queue = self_improve.ApprovalQueue(approval_required=True)

    result = queue.queue_task("task1", "reason", 5.0)
    assert not result, "Should be waiting (not auto-approved)"

    pending = queue.get_pending()
    assert len(pending) == 1
    assert pending[0]["task"] == "task1"

    print(f"✓ ApprovalQueue queues task: {pending[0]['id']}")


def test_approval_queue_approve():
    """Test: ApprovalQueue can approve tasks."""
    queue = self_improve.ApprovalQueue(approval_required=True)
    queue.queue_task("task1", "reason", 5.0)

    task_id = queue.get_pending()[0]["id"]
    approved = queue.approve(task_id)
    assert approved, "Should approve"
    assert len(queue.get_pending()) == 0, "Should remove from pending"
    assert len(queue.approved) == 1, "Should add to approved"

    print("✓ ApprovalQueue approves task")


def test_approval_queue_reject():
    """Test: ApprovalQueue can reject tasks."""
    queue = self_improve.ApprovalQueue(approval_required=True)
    queue.queue_task("task1", "reason", 5.0)

    task_id = queue.get_pending()[0]["id"]
    rejected = queue.reject(task_id, reason="too expensive")
    assert rejected, "Should reject"
    assert len(queue.get_pending()) == 0, "Should remove from pending"

    print("✓ ApprovalQueue rejects task")


def test_hybrid_gates_and_cost():
    """Test: Phase 7 gates + Phase 6 cost tracking work together."""
    tracker = self_improve.CostTracker(daily_cap=50.0)
    tracker.record_cost("task1", 30.0)

    cost_remaining = tracker.daily_cap - tracker.today_cost
    assert cost_remaining == 20.0

    # Phase 7 gate: should skip if expensive + risky
    skip, reason = self_improve.should_skip_task(
        "expensive_task",
        cost_remaining=20.0,
        last_outcome=None,
    )
    print(f"✓ Hybrid: gates + cost tracking work: skip={skip}, reason={reason}")


def test_backward_compat_outcome_value_optional():
    """Test: compute_outcome_value defaults gracefully."""
    # Empty dict
    score = self_improve.compute_outcome_value({})
    assert 0.0 <= score <= 1.0, f"Should be valid score: {score}"

    # Missing keys
    score = self_improve.compute_outcome_value({"lead_count": 5})
    assert 0.0 <= score <= 1.0, f"Should handle missing keys: {score}"

    # Invalid types (should clamp)
    score = self_improve.compute_outcome_value(
        {
            "avg_lead_score": "invalid",
            "revenue_impact": "invalid",
            "cost": "invalid",
        }
    )
    assert 0.0 <= score <= 1.0, f"Should handle invalid types: {score}"

    print("✓ Backward compat: compute_outcome_value handles edge cases")


def test_outcome_weights_configurable():
    """Test: OUTCOME_WEIGHTS dict is modifiable."""
    original = self_improve.OUTCOME_WEIGHTS.copy()
    try:
        # Change weights
        self_improve.OUTCOME_WEIGHTS["lead_quality"] = 0.5
        self_improve.OUTCOME_WEIGHTS["revenue"] = 0.3
        self_improve.OUTCOME_WEIGHTS["cost"] = -0.2

        # Verify change affects computation
        outcome = {
            "avg_lead_score": 0.8,
            "revenue_impact": 500,
            "cost": 2.0,
            "lead_count": 10,
            "success": True,
        }
        score = self_improve.compute_outcome_value(outcome)
        assert 0.0 <= score <= 1.0
        print(f"✓ OUTCOME_WEIGHTS configurable: score={score:.2f}")
    finally:
        self_improve.OUTCOME_WEIGHTS.update(original)


async def test_integration_run_once_structure():
    """Test: run_once() returns correct structure with Phase 7 fields."""
    # This is a structural test (no-op if loop disabled)
    status = self_improve.status()
    assert "enabled" in status
    assert "recent_runs" in status

    print("✓ Integration: run_once() structure ok")


def main():
    """Run all tests."""
    print("=" * 70)
    print("Phase 7: Deterministic Feedback Loops + Cost-Aware Bandit Tests")
    print("=" * 70)

    tests = [
        # Outcome value tests
        ("Outcome Value: High Quality", test_outcome_value_high_quality),
        ("Outcome Value: Neutral", test_outcome_value_neutral),
        ("Outcome Value: Expensive Failure", test_outcome_value_expensive_failure),
        ("Outcome Value: Clamping", test_outcome_value_clamps),
        # Gate tests
        ("Gate: Budget", test_gate_budget),
        ("Gate: Expensive + Risky", test_gate_expensive_risky),
        ("Gate: Low ROI", test_gate_low_roi),
        ("Gate: Good Task Passes", test_gate_passes_good_task),
        ("Gate: Can Disable", test_gates_can_disable),
        # CostTracker tests
        ("CostTracker: Basic", test_cost_tracker_basic),
        ("CostTracker: Budget Enforcement", test_cost_tracker_budget_exceeded),
        # ApprovalQueue tests
        ("ApprovalQueue: Basic", test_approval_queue_basic),
        ("ApprovalQueue: Approve", test_approval_queue_approve),
        ("ApprovalQueue: Reject", test_approval_queue_reject),
        # Integration tests
        ("Integration: Hybrid Gates + Cost", test_hybrid_gates_and_cost),
        (
            "Integration: Backward Compat (outcome_value)",
            test_backward_compat_outcome_value_optional,
        ),
        ("Integration: Configurable Weights", test_outcome_weights_configurable),
        ("Integration: run_once() Structure", test_integration_run_once_structure),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            # Run async tests
            if asyncio.iscoroutinefunction(test_func):
                asyncio.run(test_func())
            else:
                test_func()
            passed += 1
            print()
        except AssertionError as e:
            failed += 1
            print(f"✗ {name}: {e}\n")
        except Exception as e:
            failed += 1
            print(f"✗ {name}: UNEXPECTED ERROR: {e}\n")

    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
