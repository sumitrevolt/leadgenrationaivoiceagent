"""
TypeSafe Middleware Integration Test
=====================================
Tests the middleware with TypeSafe API integration.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path("C:/Users/Ratanshila/.buzz/REPOS/leadgenrationaivoiceagent")
sys.path.insert(0, str(project_root))

from app.platform.typesafe_middleware import (
    TypeSafeMiddleware,
    TypeSafeDecision,
    get_middleware,
    decide_lead,
    decide_campaign,
    decide_task,
    decide_telegram,
    clear_decision_cache,
)


def test_lead_qualification():
    """Test lead qualification via TypeSafe middleware."""
    print("=" * 60)
    print("TEST: Lead Qualification via Middleware")
    print("=" * 60)
    
    middleware = get_middleware()
    
    sample_leads = [
        {
            "id": "lead_001",
            "company": "Acme Corp",
            "industry": "SaaS",
            "company_size": 500,
            "budget_signal": 85,
            "engagement_score": 90,
            "fit_score": 88,
            "urgency": "high"
        },
        {
            "id": "lead_002",
            "company": "StartupXYZ",
            "industry": "E-commerce",
            "company_size": 50,
            "budget_signal": 40,
            "engagement_score": 60,
            "fit_score": 55,
            "urgency": "medium"
        }
    ]
    
    for lead in sample_leads:
        decision = middleware.qualify_lead(lead)
        print(f"\nLead: {lead['company']}")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Model: {decision.model}")
        print(f"  Result: {json.dumps(decision.result, indent=2)}")
        print(f"  Confidence: {decision.confidence:.1%}")
        print(f"  Latency: {decision.latency_ms:.0f}ms")
        
        # Validate decision structure
        assert isinstance(decision, TypeSafeDecision)
        assert decision.result is not None
        assert "priority" in decision.result
        assert "score" in decision.result
    
    print("\n✅ Lead qualification test PASSED")
    return True


def test_campaign_optimization():
    """Test campaign optimization via TypeSafe middleware."""
    print("\n" + "=" * 60)
    print("TEST: Campaign Optimization via Middleware")
    print("=" * 60)
    
    middleware = get_middleware()
    
    sample_campaigns = [
        {
            "id": "camp_001",
            "name": "LinkedIn Outreach Q3",
            "status": "active",
            "impressions": 50000,
            "clicks": 2500,
            "conversions": 150,
            "spend": 5000,
            "ctr": 0.05,
            "conversion_rate": 0.06,
            "roi": 4.5,
            "days_running": 30
        },
        {
            "id": "camp_002",
            "name": "Google Ads Retargeting",
            "status": "paused",
            "impressions": 25000,
            "clicks": 500,
            "conversions": 10,
            "spend": 3000,
            "ctr": 0.02,
            "conversion_rate": 0.02,
            "roi": -0.5,
            "days_running": 45
        }
    ]
    
    for campaign in sample_campaigns:
        decision = middleware.optimize_campaign(campaign)
        print(f"\nCampaign: {campaign['name']}")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Model: {decision.model}")
        print(f"  Result: {json.dumps(decision.result, indent=2)}")
        print(f"  Confidence: {decision.confidence:.1%}")
        print(f"  Latency: {decision.latency_ms:.0f}ms")
        
        # Validate decision structure
        assert isinstance(decision, TypeSafeDecision)
        assert decision.result is not None
        assert "action" in decision.result
        assert "expected_impact" in decision.result
    
    print("\n✅ Campaign optimization test PASSED")
    return True


def test_task_routing():
    """Test task routing via TypeSafe middleware."""
    print("\n" + "=" * 60)
    print("TEST: Task Routing via Middleware")
    print("=" * 60)
    
    middleware = get_middleware()
    
    sample_tasks = [
        {"task_id": "task_001", "type": "lead_scraper", "priority": "critical", "domain": "outreach"},
        {"task_id": "task_002", "type": "follow_up", "priority": "high", "domain": "sales"},
        {"task_id": "task_003", "type": "qa_check", "priority": "medium", "domain": "quality"},
    ]
    
    for task in sample_tasks:
        decision = middleware.route_task(task)
        print(f"\nTask: {task['type']} (Priority: {task['priority']})")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Model: {decision.model}")
        print(f"  Result: {json.dumps(decision.result, indent=2)}")
        print(f"  Confidence: {decision.confidence:.1%}")
        
        # Validate decision structure
        assert isinstance(decision, TypeSafeDecision)
        assert decision.result is not None
        assert "assigned_agent" in decision.result
        assert "priority_adjusted" in decision.result
    
    print("\n✅ Task routing test PASSED")
    return True


def test_telegram_classification():
    """Test Telegram message classification via TypeSafe middleware."""
    print("\n" + "=" * 60)
    print("TEST: Telegram Classification via Middleware")
    print("=" * 60)
    
    middleware = get_middleware()
    
    sample_messages = [
        {"message_id": "msg_001", "text": "/status", "sender": "sumitrevolt", "is_owner": True},
        {"message_id": "msg_002", "text": "Show me my tasks", "sender": "sumitrevolt", "is_owner": True},
        {"message_id": "msg_003", "text": "What agents are available?", "sender": "sumitrevolt", "is_owner": True},
        {"message_id": "msg_004", "text": "Generate leads for SaaS companies", "sender": "sumitrevolt", "is_owner": True},
    ]
    
    for message in sample_messages:
        decision = middleware.classify_telegram_message(message)
        print(f"\nMessage: '{message['text']}'")
        print(f"  Decision ID: {decision.decision_id}")
        print(f"  Model: {decision.model}")
        print(f"  Result: {json.dumps(decision.result, indent=2)}")
        print(f"  Confidence: {decision.confidence:.1%}")
        
        # Validate decision structure
        assert isinstance(decision, TypeSafeDecision)
        assert decision.result is not None
        assert "intent" in decision.result
        assert "priority" in decision.result
    
    print("\n✅ Telegram classification test PASSED")
    return True


def test_convenience_functions():
    """Test convenience functions for quick decisions."""
    print("\n" + "=" * 60)
    print("TEST: Convenience Functions")
    print("=" * 60)
    
    # Test decide_lead
    lead = {"id": "lead_test", "fit_score": 80, "budget_signal": 75, "engagement_score": 90}
    decision = decide_lead(lead)
    print(f"decide_lead() -> {decision.result}")
    assert decision is not None
    
    # Test decide_campaign
    campaign = {"id": "camp_test", "roi": 2.5, "ctr": 0.05}
    decision = decide_campaign(campaign)
    print(f"decide_campaign() -> {decision.result}")
    assert decision is not None
    
    # Test decide_task
    task = {"task_id": "task_test", "priority": "high", "type": "outreach"}
    decision = decide_task(task)
    print(f"decide_task() -> {decision.result}")
    assert decision is not None
    
    # Test decide_telegram
    message = {"message_id": "msg_test", "text": "/status"}
    decision = decide_telegram(message)
    print(f"decide_telegram() -> {decision.result}")
    assert decision is not None
    
    print("\n✅ Convenience functions test PASSED")
    return True


def test_decision_cache():
    """Test decision caching."""
    print("\n" + "=" * 60)
    print("TEST: Decision Cache")
    print("=" * 60)
    
    # Clear cache first
    clear_decision_cache()
    
    middleware = get_middleware()
    
    # Make same decision twice
    lead = {"id": "lead_cache_test", "fit_score": 75, "budget_signal": 70, "engagement_score": 80}
    
    decision1 = middleware.qualify_lead(lead)
    decision2 = middleware.qualify_lead(lead)
    
    print(f"First call latency: {decision1.latency_ms:.0f}ms")
    print(f"Second call latency: {decision2.latency_ms:.0f}ms")
    
    # Both should have similar results (cache may or may not be used)
    assert decision1.result == decision2.result
    
    print("\n✅ Decision cache test PASSED")
    return True


def main():
    """Run all middleware tests."""
    print("=" * 70)
    print("TypeSafe Middleware — Integration Test Suite")
    print("=" * 70)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 70)
    
    tests = [
        ("Lead Qualification", test_lead_qualification),
        ("Campaign Optimization", test_campaign_optimization),
        ("Task Routing", test_task_routing),
        ("Telegram Classification", test_telegram_classification),
        ("Convenience Functions", test_convenience_functions),
        ("Decision Cache", test_decision_cache),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} test FAILED: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"  {status}: {name}")
    
    all_passed = all(r[1] for r in results)
    print("\n" + "=" * 70)
    if all_passed:
        print("ALL TESTS PASSED ✅")
    else:
        print("SOME TESTS FAILED ❌")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
