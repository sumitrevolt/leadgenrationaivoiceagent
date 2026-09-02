"""W1.5 — self_improve tick-slot must FAIL-CLOSED when Redis is unavailable/errors.

Bug: `acquire_tick_slot()` returned a *live* token when Redis was unavailable
(`_redis_client()` is None) or when the get/set raised — i.e. it fail-OPENED. Without
the distributed guard, every duplicate self-requeue chain believed it owned the slot
and ran, so a Redis outage multiplied the self-improve chains (free-tier LLM burn).

Fix: on Redis-unavailable or error, return "" (no slot). The caller
(`staff_jobs.self_improve_tick`) treats "" as a clean skip (no run, no requeue),
so denied duplicate ticks cannot multiply the queue; the watchdog revives one
chain only after its own Redis NX lock succeeds. No per-tick stack trace.
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


def test_revive_lock_fail_closed_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(si, "_redis_client", lambda: None)
    assert si._acquire_revive_lock() is False, "Revive must not seed a chain without Redis lock"


def test_revive_lock_fail_closed_on_redis_error(monkeypatch):
    class _BrokenRedis:
        def set(self, *a, **k):
            raise RuntimeError("redis down")

    monkeypatch.setattr(si, "_redis_client", lambda: _BrokenRedis())
    assert si._acquire_revive_lock() is False, "Revive must not seed a chain on Redis errors"


def test_watchdog_does_not_enqueue_without_revive_lock(tmp_path, monkeypatch):
    import json
    import time

    monkeypatch.setenv("SELF_IMPROVE_LOOP", "1")
    monkeypatch.setattr(si, "_STATE", str(tmp_path / "state.json"))
    with open(si._STATE, "w", encoding="utf-8") as f:
        json.dump({"last_tick": time.time() - 3600}, f)
    monkeypatch.setattr(si, "_acquire_revive_lock", lambda: False)

    from app.tasks import staff_jobs

    queued: list[bool] = []
    monkeypatch.setattr(staff_jobs.self_improve_tick, "delay", lambda: queued.append(True))

    out = si.ensure_alive()

    assert out == {"enabled": True, "alive": False, "revive_skipped": "lock"}
    assert queued == [], "Watchdog must not seed a chain without a distributed lock"
