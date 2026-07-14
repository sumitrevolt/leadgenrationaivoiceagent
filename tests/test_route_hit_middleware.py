"""Route-hit telemetry must not reuse an asyncio Redis pool across event loops."""

import asyncio

from app import middleware


class _SyncRedis:
    def __init__(self):
        self.calls = []

    def hincrby(self, key, path, amount):
        self.calls.append((key, path, amount))


def test_route_hit_record_uses_loop_safe_sync_client(monkeypatch):
    fake = _SyncRedis()
    monkeypatch.setattr(middleware, "_route_hit_sync_client", fake)
    monkeypatch.setattr(middleware.time, "strftime", lambda *_a, **_k: "20260714")

    asyncio.run(middleware.RouteHitMiddleware._record("/health"))

    assert fake.calls == [("route_hits:20260714", "/health", 1)]


def test_route_hit_record_remains_fail_silent(monkeypatch):
    class _BrokenRedis:
        def hincrby(self, *_a, **_k):
            raise RuntimeError("redis unavailable")

    monkeypatch.setattr(middleware, "_route_hit_sync_client", _BrokenRedis())
    asyncio.run(middleware.RouteHitMiddleware._record("/health"))
