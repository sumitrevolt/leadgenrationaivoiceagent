"""Idempotency fallback-key stability tests.

BUG (fixed): the fallback idempotency key (used when Celery `self.request.id`
is missing) was built with the Python builtin ``hash(str(args))``. ``hash()``
is randomized per-process by ``PYTHONHASHSEED``, so the same args produced a
DIFFERENT key in each worker process -> Redis setnx dedup silently bypassed.

FIX: fallback key now uses ``hashlib.sha1(str(args).encode()).hexdigest()[:16]``
which is stable/deterministic across processes.

These tests assert the fallback key is deterministic for the same args and is
derived from a stable sha1 (NOT the randomized builtin ``hash``).
"""

from __future__ import annotations

import hashlib

from app.tasks import idempotency
from app.tasks.idempotency import idempotent_task


class _FakeRequest:
    """Mimic celery ``self.request`` with no task id -> forces fallback path."""

    id = None


class _FakeTask:
    """Mimic the bound ``self`` a celery task receives."""

    request = _FakeRequest()


def _capture_fallback_key(args, monkeypatch):
    """Invoke the idempotent wrapper and return the Redis key it generated.

    A fake redis client records the key passed to ``.set(...)``; ``nx=True``
    returns truthy so the wrapped function still runs (no skip).
    """
    captured: dict[str, str] = {}

    class _FakeRedis:
        def set(self, key, *a, **k):  # noqa: ANN001
            captured["key"] = key
            return True  # nx success -> not a duplicate

    monkeypatch.setattr(idempotency, "_redis_client", lambda: _FakeRedis())

    @idempotent_task("demo_task", ttl=60)
    def _job(self, *a, **k):  # noqa: ANN001
        return "ran"

    result = _job(_FakeTask(), *args)
    assert result == "ran"  # wrapped fn executed (not skipped)
    # key format: celery:idem:{task_name}:{task_name}:{fallback_hash}:{retries}
    return captured["key"]


def test_fallback_key_is_deterministic_same_args(monkeypatch):
    """Same args -> same fallback key on repeated calls (within a process)."""
    args = ("lead-42", 7)
    key1 = _capture_fallback_key(args, monkeypatch)
    key2 = _capture_fallback_key(args, monkeypatch)
    assert key1 == key2


def test_fallback_key_differs_for_different_args(monkeypatch):
    """Different args -> different fallback key."""
    key_a = _capture_fallback_key(("lead-42", 7), monkeypatch)
    key_b = _capture_fallback_key(("lead-99", 7), monkeypatch)
    assert key_a != key_b


def test_fallback_key_uses_stable_sha1_not_builtin_hash(monkeypatch):
    """Fallback key must embed the sha1 digest, NOT the process-randomized
    builtin ``hash`` value.

    This is the core regression guard: ``hashlib.sha1`` is stable across
    processes/PYTHONHASHSEED, while ``hash()`` is not. We assert the key
    contains the expected sha1 prefix and does NOT equal what a ``hash()``
    based implementation would have produced.
    """
    args = ("lead-42", 7)
    expected_sha1 = hashlib.sha1(str(args).encode()).hexdigest()[:16]

    key = _capture_fallback_key(args, monkeypatch)

    # stable sha1 fragment present (key now carries a trailing :{retries} segment
    # so a genuine self.retry() is not deduped away — fresh task => retries 0).
    assert expected_sha1 in key
    assert key.endswith(f"demo_task:{expected_sha1}:0")

    # regression guard: a builtin-hash implementation would have used this
    legacy_key_fragment = f"demo_task:{hash(str(args))}"
    assert legacy_key_fragment not in key


def test_retry_attempt_not_deduped_away(monkeypatch):
    """A genuine self.retry() (same task_id, incremented retries) must produce a
    DISTINCT key so a real Redis setnx lets it run — while a redelivery of the
    SAME attempt (same retries) is still skipped as a duplicate.

    Regression: previously the key omitted retries, so the retry collided with the
    original attempt's live key and was silently skipped (failure never re-ran,
    never reached the DLQ).
    """
    store: set[str] = set()

    class _DedupRedis:
        def set(self, key, *a, **k):  # noqa: ANN001
            if key in store:
                return False  # nx fails -> treated as duplicate
            store.add(key)
            return True

    monkeypatch.setattr(idempotency, "_redis_client", lambda: _DedupRedis())

    @idempotent_task("demo_task", ttl=60)
    def _job(self, *a, **k):  # noqa: ANN001
        return "ran"

    class _Req:
        id = "task-abc"
        retries = 0

    class _Task:
        request = _Req()

    t = _Task()
    # attempt 0 runs
    assert _job(t, "x") == "ran"
    # redelivery of the SAME attempt (retries still 0) -> deduped
    assert _job(t, "x") == {"ok": True, "skipped": "duplicate", "task": "demo_task"}
    # genuine retry (retries incremented) -> NOT deduped, runs again
    t.request.retries = 1
    assert _job(t, "x") == "ran"
