"""W1.5 — self_improve tick-slot must FAIL-CLOSED when Redis is unavailable/errors.

Bug: `acquire_tick_slot()` returned a *live* token when Redis was unavailable
(`_redis_client()` is None) or when the get/set raised — i.e. it fail-OPENED. Without
the distributed guard, every duplicate self-requeue chain believed it owned the slot
and ran, so a Redis outage multiplied the self-improve chains (free-tier LLM burn).

Fix: on Redis-unavailable or error, return "" (no slot). The caller
(`staff_jobs.self_improve_tick`) already treats "" as a clean skip (no run, no
requeue); the watchdog revives the chain when Redis returns. No per-tick stack trace.
"""
from __future__ import annotations

import app.agents.self_improve as si


def test_tick_slot_fail_closed_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(si, "_redis_client", lambda: None)
    assert si.acquire_tick_slot() == "", "Redis unavailable must yield NO slot (fail-closed)"


def test_tick_slot_fail_closed_on_redis_error(monkeypatch):
    class _BrokenRedis:
        def get(self, *a, **k):
            raise RuntimeError("redis down")

        def set(self, *a, **k):
            raise RuntimeError("redis down")

    monkeypatch.setattr(si, "_redis_client", lambda: _BrokenRedis())
    assert si.acquire_tick_slot() == "", "Redis error must yield NO slot (fail-closed)"
