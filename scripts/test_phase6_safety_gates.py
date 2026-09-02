#!/usr/bin/env python3
"""
Test Phase 6: Safety gates for self-improve loop.
Verification script for cost tracking + approval UI.
"""

import asyncio
import json
import sys
from datetime import datetime, timezone

# Test 1: Cost Tracker
print("\n✅ TEST 1: CostTracker class")
try:
    from app.agents.self_improve import CostTracker

    ct = CostTracker(daily_cap=50.0)

    # Test can_afford
    assert ct.can_afford("test_action", 10.0), "Should afford $10 from $50 cap"
    print("  ✓ can_afford(task, 10.0) = True")

    # Test record_cost
    ct.record_cost("test_action", 10.0)
    status = ct.get_daily_status()
    assert status["spent"] == 10.0, f"Expected spent=$10, got {status['spent']}"
    assert status["remaining"] == 40.0, f"Expected remaining=$40, got {status['remaining']}"
    print("  ✓ record_cost(task, 10.0) updated spent=$10, remaining=$40")

    # Test can't exceed budget
    assert not ct.can_afford("expensive_action", 50.0), "Should NOT afford $50 when $40 remains"
    print("  ✓ can_afford(expensive_action, 50.0) = False (budget protection)")

    # Test pct_used
    ct.record_cost("another_action", 20.0)
    status = ct.get_daily_status()
    assert status["spent"] == 30.0, f"Expected spent=$30, got {status['spent']}"
    assert status["pct_used"] == 60.0, f"Expected pct_used=60%, got {status['pct_used']}"
    print(f"  ✓ pct_used = {status['pct_used']}% (30/50 spent)")

    print("✅ CostTracker class PASS")
except Exception as e:
    print(f"❌ CostTracker test FAIL: {e}")
    sys.exit(1)

# Test 2: Approval Queue
print("\n✅ TEST 2: ApprovalQueue class")
try:
    from app.agents.self_improve import ApprovalQueue

    aq = ApprovalQueue(approval_required=True)

    # Test queue_task
    result = aq.queue_task("test_task", reason="Testing approval gate", cost_estimate=2.5)
    assert not result, "Should return False (waiting approval)"
    print("  ✓ queue_task() returns False when approval_required=True")

    # Test get_pending
    pending = aq.get_pending()
    assert len(pending) == 1, f"Expected 1 pending task, got {len(pending)}"
    task_id = pending[0]["id"]
    assert pending[0]["status"] == "waiting", "Status should be 'waiting'"
    print(f"  ✓ get_pending() returns 1 task with id={task_id[:8]}")

    # Test approve
    success = aq.approve(task_id)
    assert success, "Approve should return True"
    assert len(aq.get_pending()) == 0, "Task should be removed from pending after approval"
    assert len(aq.approved) == 1, "Task should be in approved list"
    print("  ✓ approve(task_id) moved task to approved list")

    # Test is_approved
    assert aq.is_approved(task_id), "Task should be in approved list"
    print("  ✓ is_approved(task_id) = True")

    # Test reject
    aq.queue_task("reject_task", reason="To be rejected", cost_estimate=1.0)
    reject_task_id = aq.get_pending()[0]["id"]
    success = aq.reject(reject_task_id, reason="Not needed")
    assert success, "Reject should return True"
    assert len(aq.get_pending()) == 0, "Rejected task should be removed from pending"
    print("  ✓ reject(task_id, reason) removes from pending")

    # Test auto-approve when approval_required=False
    aq_auto = ApprovalQueue(approval_required=False)
    result = aq_auto.queue_task("auto_task", reason="Auto-approve", cost_estimate=1.0)
    assert result, "Should return True when approval_required=False"
    print("  ✓ queue_task() returns True when approval_required=False (auto-approve)")

    print("✅ ApprovalQueue class PASS")
except Exception as e:
    print(f"❌ ApprovalQueue test FAIL: {e}")
    sys.exit(1)

# Test 3: Global instances
print("\n✅ TEST 3: Global instances (_get_cost_tracker, _get_approval_queue)")
try:
    from app.agents.self_improve import _get_approval_queue, _get_cost_tracker

    ct = _get_cost_tracker()
    assert ct is not None, "Cost tracker should not be None"
    assert isinstance(ct, CostTracker), "Should return CostTracker instance"
    print("  ✓ _get_cost_tracker() returns CostTracker instance")

    aq = _get_approval_queue()
    assert aq is not None, "Approval queue should not be None"
    assert isinstance(aq, ApprovalQueue), "Should return ApprovalQueue instance"
    print("  ✓ _get_approval_queue() returns ApprovalQueue instance")

    print("✅ Global instances PASS")
except Exception as e:
    print(f"❌ Global instances test FAIL: {e}")
    sys.exit(1)

# Test 4: Helper functions
print("\n✅ TEST 4: Helper functions (cost_status, approval_status)")
try:
    from app.agents.self_improve import approval_status, cost_status

    cs = cost_status()
    assert "date" in cs, "cost_status should have 'date'"
    assert "spent" in cs, "cost_status should have 'spent'"
    assert "cap" in cs, "cost_status should have 'cap'"
    assert "pct_used" in cs, "cost_status should have 'pct_used'"
    print(f"  ✓ cost_status() returns keys: {list(cs.keys())}")

    astatus = approval_status()
    assert "approval_required" in astatus, "approval_status should have 'approval_required'"
    assert "pending_count" in astatus, "approval_status should have 'pending_count'"
    assert "pending" in astatus, "approval_status should have 'pending'"
    print(f"  ✓ approval_status() returns keys: {list(astatus.keys())}")

    print("✅ Helper functions PASS")
except Exception as e:
    print(f"❌ Helper functions test FAIL: {e}")
    sys.exit(1)

# Test 5: Environment variables
print("\n✅ TEST 5: Environment variables")
try:
    import os

    # Check if env vars are readable
    self_improve_approval = os.environ.get("SELF_IMPROVE_APPROVAL", "0")
    selfimprove_cost_cap = os.environ.get("SELFIMPROVE_COST_CAP", "50")

    print(f"  ✓ SELF_IMPROVE_APPROVAL = {self_improve_approval}")
    print(f"  ✓ SELFIMPROVE_COST_CAP = {selfimprove_cost_cap}")

    # Validate cost cap is numeric
    try:
        cap = float(selfimprove_cost_cap)
        assert cap > 0, "Cost cap must be positive"
        print(f"  ✓ Cost cap parsed as ${cap}")
    except ValueError:
        print("  ⚠️  Cost cap not numeric, will use default 50.0")

    print("✅ Environment variables PASS")
except Exception as e:
    print(f"❌ Environment variables test FAIL: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL PHASE 6 TESTS PASSED")
print("=" * 60)
print("\nPhase 6 Implementation Summary:")
print("  • CostTracker: daily budget cap + per-task cost logging")
print("  • ApprovalQueue: human approval gates for LLM-heavy actions")
print("  • Global instances: _get_cost_tracker(), _get_approval_queue()")
print("  • Helper functions: cost_status(), approval_status()")
print(
    "  • API endpoints: /api/growth/selfimprove/cost-status, /approvals-pending, /approval/{id}/approve, /approval/{id}/reject"
)
print("  • Frontend UI: Cost tracking chart + approval request cards with approve/reject buttons")
print("  • Environment: SELF_IMPROVE_APPROVAL (0/1), SELFIMPROVE_COST_CAP ($)")
print("\nNext: Run full pytest to verify integration with run_once() loop")
