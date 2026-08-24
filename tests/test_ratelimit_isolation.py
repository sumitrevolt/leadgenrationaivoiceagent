"""Regression: rate-limit state must not leak across tests (2026-07-18).

Guards the autouse `_reset_rate_limit_state` fixture in conftest.py. Before it,
the shared in-memory limiter singleton (`app.cache._redis_client`, an
InMemoryCache under the tests' refused-Redis fallback) accumulated
rl:<scope>:<ip> counters, so later tests received HTTP 429 instead of their real
status (test_signup_password_hygiene). See docs/CI_HEALTH_2026-07-18.md cluster 1.
"""

from __future__ import annotations

import asyncio

import app.cache as _cache


def _mem() -> dict:
    """In-memory limiter store used under the tests' Redis-refused fallback."""
    client = getattr(_cache, "_redis_client", None)
    if client is None or not hasattr(client, "_cache"):
        _cache._redis_client = _cache.InMemoryCache()
        client = _cache._redis_client
    return client._cache


def _rl_keys():
    return [k for k in _mem() if str(k).startswith("rl:")]


def test_rate_limit_state_clean_then_pollute():
    # the autouse fixture cleared limiter state before this test
    assert _rl_keys() == [], f"expected clean rl state at start, found {_rl_keys()}"
    # pollute so the next test proves cross-test isolation
    _mem()["rl:signup:203.0.113.7:999"] = "999"
    _mem()["rl:inquiry:203.0.113.7:999"] = "50"


def test_rate_limit_state_isolated_from_previous_test():
    # if isolation works, the previous test's rl: pollution has been cleared
    assert _rl_keys() == [], (
        f"rate-limit state leaked across tests (isolation fixture failed): {_rl_keys()}"
    )


def test_limiter_still_counts_within_a_test():
    """The fixture resets BETWEEN tests but must NOT disable limiting: a real
    RateLimiter still blocks once the per-window cap is exceeded within one test."""
    from app.cache import RateLimiter

    async def _run():
        rl = RateLimiter(prefix="rl:_isolation_probe", max_requests=3, window_seconds=60)
        out = []
        for _ in range(5):
            allowed, _rem = await rl.is_allowed("probe-ip")
            out.append(allowed)
        return out

    allowed = asyncio.run(_run())
    assert allowed[0] is True, f"first request must be allowed, got {allowed}"
    assert allowed[-1] is False, f"limiter must block after cap within a test, got {allowed}"
