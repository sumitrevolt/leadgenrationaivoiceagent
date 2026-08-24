"""Hermetic tests for seen_before_sync / forget_sync sync primitives.

No real Redis, no network, no DB — monkeypatch _sync_redis to force the two code paths:
  - raise  → memory fallback (_mem_seen)
  - return mock → real SET NX EX path
"""

from __future__ import annotations

import importlib
import time
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_mem(idem_module):
    """Clear the module-level _MEM dict between tests so state never bleeds."""
    idem_module._MEM.clear()


# ---------------------------------------------------------------------------
# Tests — memory-fallback path (_sync_redis raises → fail-open)
# ---------------------------------------------------------------------------


def test_seen_before_sync_first_call_false(monkeypatch):
    """First call with an unseen key must return False (not a duplicate)."""
    import app.billing.idempotency as idem

    _reset_mem(idem)

    monkeypatch.setattr(
        idem, "_sync_redis", lambda: (_ for _ in ()).throw(ConnectionError("redis down"))
    )

    result = idem.seen_before_sync("test-key-first-call")
    assert result is False, "First-time key should return False (not seen before)"


def test_seen_before_sync_second_call_true(monkeypatch):
    """Second call with the same key must return True (duplicate detected in memory)."""
    import app.billing.idempotency as idem

    _reset_mem(idem)

    def _raise():
        raise ConnectionError("redis down")

    monkeypatch.setattr(idem, "_sync_redis", _raise)

    key = "test-key-second-call"
    first = idem.seen_before_sync(key)
    second = idem.seen_before_sync(key)

    assert first is False, "First call should return False"
    assert second is True, "Second call with same key should return True (seen before)"


def test_forget_sync_clears_key(monkeypatch):
    """After forget_sync, the key must be treated as unseen again."""
    import app.billing.idempotency as idem

    _reset_mem(idem)

    def _raise():
        raise ConnectionError("redis down")

    monkeypatch.setattr(idem, "_sync_redis", _raise)

    key = "test-key-forget"

    # Mark as seen
    idem.seen_before_sync(key)
    assert idem.seen_before_sync(key) is True, "Should be True before forget"

    # Forget — _sync_redis raises here too (forget_sync catches silently); _MEM.pop still runs
    idem.forget_sync(key)

    # Now it must look new again
    result = idem.seen_before_sync(key)
    assert result is False, "After forget_sync, key should be False (not seen)"


# ---------------------------------------------------------------------------
# Test — real mock-Redis path (SET NX EX wiring)
# ---------------------------------------------------------------------------


def test_seen_before_sync_with_real_mock_redis(monkeypatch):
    """Mock _sync_redis returning a MagicMock; verify SET is called with correct args."""
    import app.billing.idempotency as idem

    _reset_mem(idem)

    mock_redis = MagicMock()

    # SET NX=True: first call returns True (key created), second returns None (already exists)
    mock_redis.set.side_effect = [True, None]

    monkeypatch.setattr(idem, "_sync_redis", lambda: mock_redis)

    key = "test-key-mock-redis"
    ttl = 42

    first = idem.seen_before_sync(key, ttl_s=ttl)
    second = idem.seen_before_sync(key, ttl_s=ttl)

    assert first is False, "SET returned True (created) → should be False (not seen before)"
    assert second is True, "SET returned None (already exists) → should be True (seen before)"

    # Verify both calls used correct Redis args
    rk = idem._PREFIX + key
    assert mock_redis.set.call_count == 2

    for call in mock_redis.set.call_args_list:
        args, kwargs = call
        assert args[0] == rk, f"Expected key '{rk}', got '{args[0]}'"
        assert kwargs.get("nx") is True, "nx=True must be passed for atomic check-and-set"
        assert kwargs.get("ex") == ttl, f"Expected ex={ttl}, got {kwargs.get('ex')}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_seen_before_sync_empty_key(monkeypatch):
    """Empty / whitespace-only key must always return False (fail-open, no dedup possible)."""
    import app.billing.idempotency as idem

    _reset_mem(idem)

    # _sync_redis should never even be called for an empty key
    call_count = 0

    def _raise():
        nonlocal call_count
        call_count += 1
        raise ConnectionError("should not be called")

    monkeypatch.setattr(idem, "_sync_redis", _raise)

    assert idem.seen_before_sync("") is False
    assert idem.seen_before_sync("   ") is False
    assert call_count == 0, "_sync_redis must not be called for empty keys"


def test_forget_sync_empty_key_no_error(monkeypatch):
    """forget_sync with empty key must silently no-op without raising."""
    import app.billing.idempotency as idem

    _reset_mem(idem)
    monkeypatch.setattr(
        idem, "_sync_redis", lambda: (_ for _ in ()).throw(ConnectionError("should not be called"))
    )

    # Must not raise
    idem.forget_sync("")
    idem.forget_sync("   ")
