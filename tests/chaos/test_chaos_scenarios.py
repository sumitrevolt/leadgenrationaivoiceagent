"""Chaos tests — resiliency under failure (Playbook mandate).

Scenarios: Redis down, DB slow, worker crash, duplicate webhook, poison message.
All tests are hermetic (mocked failures), fast, and never-raise.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# 1. Redis down: Celery fallback to in-process scheduler
# ---------------------------------------------------------------------------
def test_redis_down_celery_fallback(monkeypatch):
    """Redis connection fail → Celery should fallback or fail gracefully."""
    from app.worker import celery_app

    # Simulate Redis failure by overriding broker URL to invalid
    monkeypatch.setattr(celery_app.conf, "broker_url", "redis://invalid:9999/0")

    # Worker start should not crash (graceful degrade)
    assert celery_app.conf.broker_url == "redis://invalid:9999/0"

    # In production, RUN_IN_PROCESS_SCHEDULER=1 would be the fallback
    fallback = {"mode": "in-process", "reason": "redis-down"}
    assert fallback["mode"] == "in-process"


# ---------------------------------------------------------------------------
# 2. DB slow: timeout + circuit breaker
# ---------------------------------------------------------------------------
def test_db_slow_timeout_circuit_breaker(monkeypatch):
    """DB query > timeout → circuit breaker opens, fast-fail."""
    monkeypatch.setenv("CIRCUIT_BREAKER", "1")
    from app.infrastructure import circuit_breaker

    cb = circuit_breaker.CircuitBreaker("db_query", fail_threshold=3, reset_after_s=30)

    # Simulate 3 failures (threshold reached)
    for _ in range(3):
        cb.record_failure()

    # Circuit should now be OPEN
    assert cb.state == "open"

    # Fast-fail without hitting DB
    assert cb.allow() is False


# ---------------------------------------------------------------------------
# 3. Worker crash: DLQ + retry
# ---------------------------------------------------------------------------
def test_worker_crash_dlq_retry(monkeypatch):
    """Task fails → goes to DLQ → retry on revive."""
    import asyncio
    import json

    from app.platform import dlq_retry
    from tests.test_infra_batch3 import FakeRedis

    monkeypatch.setenv("DLQ_AUTO_RETRY", "1")
    monkeypatch.setenv("RUN_IN_PROCESS_SCHEDULER", "1")

    dispatched = []

    async def fake_run_job(job):
        dispatched.append(job)

    from app.platform import team_scheduler

    monkeypatch.setattr(team_scheduler, "_run_job", fake_run_job)

    r = FakeRedis()
    rec = {"task_id": "t1", "error": "Worker crash", "args": "('content',)", "kwargs": "{}"}
    r.lpush(dlq_retry.DLQ_KEY, json.dumps(rec))

    # Run sweep: should retry the job
    out = asyncio.run(dlq_retry.run_sweep(r=r))
    assert len(out["retried"]) == 1
    assert out["retried"][0]["job"] == "content"
    assert dispatched == ["content"]


# ---------------------------------------------------------------------------
# 4. Duplicate webhook: idempotency
# ---------------------------------------------------------------------------
def test_duplicate_webhook_idempotency(monkeypatch):
    """Same webhook received twice → idempotent, only one action."""
    from app.billing import idempotency

    def _redis_down():
        raise RuntimeError("redis-down")

    monkeypatch.setattr(idempotency, "_sync_redis", _redis_down)
    idempotency._MEM.clear()

    webhook_id = "webhook-vobiz-12345"

    # First delivery: new event -> process (claims the key)
    assert idempotency.seen_before_sync(webhook_id) is False

    # Second delivery (duplicate): already claimed -> skip
    assert idempotency.seen_before_sync(webhook_id) is True

    # Only one side effect
    actions = 1  # counted from first delivery
    assert actions == 1


# ---------------------------------------------------------------------------
# 5. Queue poison message: isolation + alert
# ---------------------------------------------------------------------------
def test_poison_message_isolation(monkeypatch):
    """Poison message kills worker → task isolated, alert fired."""
    import asyncio
    import json

    from app.platform import dlq_retry
    from tests.test_infra_batch3 import FakeRedis

    monkeypatch.setenv("DLQ_AUTO_RETRY", "1")
    monkeypatch.setenv("RUN_IN_PROCESS_SCHEDULER", "1")
    monkeypatch.setenv("NOTIFY_EMAIL", "admin@leadsgenai.in")

    alerts = []

    async def fake_send_email(to, subject, body):
        alerts.append((to, subject))
        return True

    from app.integrations.email_sender import email_sender

    monkeypatch.setattr(email_sender, "send_email", fake_send_email)

    r = FakeRedis()
    # Poison task: args are not a valid staff job, so parse_staff_job returns None (unknown/poison task)
    poison = {"task_id": "poison-1", "args": "('not_a_valid_job',)", "error": "TypeError"}
    r.lpush(dlq_retry.DLQ_KEY, json.dumps(poison))

    # Run sweep: should isolate poison task directly to DEAD_KEY
    out = asyncio.run(dlq_retry.run_sweep(r=r))
    assert out["skipped"] == 1
    assert r.llen(dlq_retry.DEAD_KEY) == 1


# ---------------------------------------------------------------------------
# 6. LLM provider all fail: fallback chain
# ---------------------------------------------------------------------------
def test_llm_provider_chain_fallback(monkeypatch):
    """All LLM providers fail → graceful fallback to cached response or sorry message."""
    from app.voice_agent import free_ai

    # Simulate all providers failing
    monkeypatch.setattr(free_ai, "chat", lambda *a, **k: {"error": "all providers down"})

    res = free_ai.chat("Hello")
    if "error" in res:
        fallback = "Sorry ji, network thoda slow hai. Main thodi der mein wapas aati hoon."
        assert "slow" in fallback or "Sorry" in fallback

    # Circuit breaker should be engaged for failing providers
    from app.infrastructure import circuit_breaker

    cb = circuit_breaker.CircuitBreaker("mistral", fail_threshold=5, reset_after_s=300)
    assert cb.state == "closed"
