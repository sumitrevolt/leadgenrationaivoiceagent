#!/usr/bin/env python3
"""Quick inline test of Phase 7 functionality."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents import self_improve

print("=" * 70)
print("Phase 7 Inline Tests")
print("=" * 70)

# Test 1: compute_outcome_value - high quality
print("\n[Test 1] Outcome Value: High Quality")
outcome_high = {
    "lead_count": 20,
    "avg_lead_score": 0.9,
    "revenue_impact": 1000,
    "cost": 1.0,
    "success": True,
}
score = self_improve.compute_outcome_value(outcome_high)
print("  Input: high quality leads + revenue, cheap cost")
print(f"  Score: {score:.2f}")
assert 0.8 < score < 1.0, f"Expected high score (0.8-1.0), got {score:.2f}"
print("  ✓ PASS")

# Test 2: compute_outcome_value - neutral
print("\n[Test 2] Outcome Value: Neutral")
outcome_neutral = {
    "lead_count": 5,
    "avg_lead_score": 0.3,
    "revenue_impact": 0,
    "cost": 2.0,
    "success": True,
}
score = self_improve.compute_outcome_value(outcome_neutral)
print("  Input: info-only leads, no revenue, normal cost")
print(f"  Score: {score:.2f}")
assert 0.0 < score < 0.3, f"Expected low score (0.0-0.3), got {score:.2f}"
print("  ✓ PASS")

# Test 3: compute_outcome_value - failure
print("\n[Test 3] Outcome Value: Expensive Failure")
outcome_fail = {
    "lead_count": 0,
    "avg_lead_score": 0.0,
    "revenue_impact": 0,
    "cost": 10.0,
    "success": False,
}
score = self_improve.compute_outcome_value(outcome_fail)
print("  Input: no leads, no revenue, expensive")
print(f"  Score: {score:.2f}")
assert score == 0.0, f"Expected 0.0 (clamped), got {score:.2f}"
print("  ✓ PASS")

# Test 4: should_skip_task - budget gate
print("\n[Test 4] Deterministic Gate: Budget")
skip, reason = self_improve.should_skip_task(
    "seo_pages",
    cost_remaining=2.0,  # only $2 left, seo_pages costs $5
    last_outcome=None,
)
print("  Task: seo_pages (cost=$5)")
print("  Budget remaining: $2")
print(f"  Skip: {skip}, Reason: {reason}")
assert skip and "budget" in reason, f"Expected budget skip, got skip={skip}, reason={reason}"
print("  ✓ PASS")

# Test 5: CostTracker
print("\n[Test 5] CostTracker: Daily Budget")
tracker = self_improve.CostTracker(daily_cap=50.0)
assert tracker.can_afford("task1", 30.0), "Should afford $30 < $50"
tracker.record_cost("task1", 30.0)
status = tracker.get_daily_status()
print(f"  Daily cap: ${status['cap']}")
print(f"  Spent: ${status['spent']}")
print(f"  Remaining: ${status['remaining']}")
print(f"  Pct used: {status['pct_used']}%")
assert status["spent"] == 30.0, f"Expected $30, got ${status['spent']}"
assert status["remaining"] == 20.0, f"Expected $20 remaining, got ${status['remaining']}"
assert not tracker.can_afford("task2", 25.0), "Should not afford $30+$25 > $50"
print("  ✓ PASS")

# Test 6: ApprovalQueue
print("\n[Test 6] ApprovalQueue: Task Workflow")
queue = self_improve.ApprovalQueue(approval_required=True)
queue_result = queue.queue_task("expensive_task", "LLM-heavy action", 5.0)
pending = queue.get_pending()
print("  Queued task, waiting approval")
print(f"  Pending count: {len(pending)}")
assert len(pending) == 1, f"Expected 1 pending, got {len(pending)}"
task_id = pending[0]["id"]
queue.approve(task_id)
print(f"  Approved task #{task_id}")
assert len(queue.get_pending()) == 0, "Pending should be empty"
assert len(queue.approved) == 1, "Should have 1 approved"
print("  ✓ PASS")

# Test 7: OUTCOME_WEIGHTS and DETERMINISTIC_GATES are configurable
print("\n[Test 7] Configuration: Modifiable Weights and Gates")
print(f"  OUTCOME_WEIGHTS: {self_improve.OUTCOME_WEIGHTS}")
print(f"  DETERMINISTIC_GATES: {self_improve.DETERMINISTIC_GATES}")
assert "lead_quality" in self_improve.OUTCOME_WEIGHTS, "Missing lead_quality weight"
assert "budget" in self_improve.DETERMINISTIC_GATES, "Missing budget gate"
print("  ✓ PASS")

# Test 8: Backward compatibility - compute_outcome_value handles edge cases
print("\n[Test 8] Backward Compat: Edge Cases")
score_empty = self_improve.compute_outcome_value({})
print(f"  Empty dict score: {score_empty:.2f}")
assert 0.0 <= score_empty <= 1.0, "Should clamp to [0,1]"

score_partial = self_improve.compute_outcome_value({"lead_count": 5})
print(f"  Partial dict score: {score_partial:.2f}")
assert 0.0 <= score_partial <= 1.0, "Should clamp to [0,1]"
print("  ✓ PASS")

print("\n" + "=" * 70)
print("All tests PASSED ✓")
print("=" * 70)
print("\nPhase 7 Implementation Summary:")
print("  ✓ Outcome value computation (weighted multi-metric)")
print("  ✓ Deterministic gates (budget, expensive_risky, low_roi)")
print("  ✓ Cost tracking (daily budget enforcement)")
print("  ✓ Approval queue (task approval workflow)")
print("  ✓ Backward compatibility (no breaking changes)")
print("  ✓ Configurable (weights and gates modifiable)")
