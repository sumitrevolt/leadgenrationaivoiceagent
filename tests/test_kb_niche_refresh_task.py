"""ADR-104 A4.5/A5 -- unit tests for app/tasks/kb_niche_refresh.py's dedup lease.

Uses a minimal in-memory fake Redis (SET NX EX / GET / DELETE semantics only --
this module's entire Redis surface) so these tests need no live Redis/Celery
broker. `refresh_niche_task` itself (the Celery task body) is exercised via a
direct `.run(...)` call on the real `celery.local.PromiseProxy` (bind=True
tasks are already self-bound -- `.run`/`.__wrapped__` take `(niche,
_lease_token)`, no fake `self` needed; retry-count state is set via the real
`push_request(retries=...)`/`pop_request()` API), monkeypatching its imports
at their real call sites.
"""

from __future__ import annotations

import sys
import types

import pytest

sys.path.insert(0, __file__.rsplit("/tests/", 1)[0] if "/tests/" in __file__ else ".")

from app.tasks import kb_niche_refresh as kbr  # noqa: E402


class _FakeRedis:
    """SET(nx=True, ex=...) / GET / DELETE only -- the entire surface this
    module touches. Mirrors real redis-py semantics closely enough for tests."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def get(self, key):
        v = self.store.get(key)
        return v.encode("utf-8") if v is not None else None

    def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def fake_redis(monkeypatch):
    fr = _FakeRedis()
    monkeypatch.setattr(kbr, "_redis_client", lambda: fr)
    return fr


def _fake_supported(monkeypatch, supported=True):
    fake_mod = types.ModuleType("app.voice_agent.kb_readiness")
    fake_mod.is_supported_niche = lambda n: supported
    monkeypatch.setitem(sys.modules, "app.voice_agent.kb_readiness", fake_mod)


def test_request_niche_refresh_unsupported_niche_never_touches_redis(monkeypatch, fake_redis):
    _fake_supported(monkeypatch, supported=False)
    ok = kbr.request_niche_refresh("not_a_real_niche")
    assert ok is False
    assert fake_redis.store == {}


def test_request_niche_refresh_no_redis_fails_closed(monkeypatch):
    _fake_supported(monkeypatch, supported=True)
    monkeypatch.setattr(kbr, "_redis_client", lambda: None)
    ok = kbr.request_niche_refresh("solar")
    assert ok is False


def test_request_niche_refresh_dedup_second_call_returns_false(monkeypatch, fake_redis):
    _fake_supported(monkeypatch, supported=True)
    dispatched = []
    monkeypatch.setattr(
        kbr.refresh_niche_task,
        "apply_async",
        lambda args=(), kwargs=None: dispatched.append((args, kwargs)),
    )
    first = kbr.request_niche_refresh("solar")
    second = kbr.request_niche_refresh("solar")
    assert first is True
    assert second is False  # lease already held -> dedup
    assert len(dispatched) == 1
    assert dispatched[0][0] == ("solar",)


def test_request_niche_refresh_dispatch_failure_releases_lease(monkeypatch, fake_redis):
    _fake_supported(monkeypatch, supported=True)

    def _boom(args=(), kwargs=None):
        raise RuntimeError("broker down")

    monkeypatch.setattr(kbr.refresh_niche_task, "apply_async", _boom)
    ok = kbr.request_niche_refresh("solar")
    assert ok is False
    # lease must be released so a later real dispatch can succeed
    assert f"{kbr._LEASE_PREFIX}:solar" not in fake_redis.store
    assert fake_redis.store.get(f"{kbr._STATE_PREFIX}:solar") == "failed"


def test_release_lease_only_deletes_if_token_matches(fake_redis, monkeypatch):
    fake_redis.store["kb:niche_refresh:lease:solar"] = "token-a"
    kbr._release_lease("solar", "token-b")  # wrong token -- must NOT delete
    assert fake_redis.store.get("kb:niche_refresh:lease:solar") == "token-a"
    kbr._release_lease("solar", "token-a")  # correct token -- deletes
    assert "kb:niche_refresh:lease:solar" not in fake_redis.store


def test_refresh_niche_task_unsupported_niche_defensive_path(monkeypatch, fake_redis):
    """Real Celery bound-task check: `refresh_niche_task` is a `celery.local.
    PromiseProxy` whose `.run`/`.__wrapped__` are ALREADY BOUND to the real Task
    instance (self applied) -- calling with an extra fake `self` positional
    causes a duplicate-argument TypeError (caught by running this against the
    real Windows files instead of a hand-rolled Celery stub, which had modeled
    `__wrapped__` as a plain unbound function). Use `.run(niche, ...)` directly
    and control retry state via the real `push_request`/`pop_request` API."""
    fake_readiness_mod = types.ModuleType("app.voice_agent.kb_readiness")
    fake_readiness_mod.is_supported_niche = lambda n: False
    fake_readiness_mod.STATE_READY = "ready"
    fake_readiness_mod.count_niche_catalog_points = lambda n: None
    fake_readiness_mod.reset_client_cache = lambda: None
    monkeypatch.setitem(sys.modules, "app.voice_agent.kb_readiness", fake_readiness_mod)

    result = kbr.refresh_niche_task.run("bogus_niche", _lease_token="tok")
    assert result["ok"] is False
    assert result["error_class"] == "UnsupportedNiche"


def test_refresh_niche_task_verifies_via_readiness_not_just_seed_ok(monkeypatch, fake_redis):
    """A seed_niche() that reports ok=True but the verification count still
    shows not-ready must raise (retry), not silently report success -- this is
    the "successful embed call that didn't actually persist" guard."""
    fake_readiness_mod = types.ModuleType("app.voice_agent.kb_readiness")
    fake_readiness_mod.is_supported_niche = lambda n: True
    fake_readiness_mod.STATE_READY = "ready"

    class _NotReady:
        state = "not_ready"
        count = 0

    fake_readiness_mod.count_niche_catalog_points = lambda n: _NotReady()
    fake_readiness_mod.reset_client_cache = lambda: None
    monkeypatch.setitem(sys.modules, "app.voice_agent.kb_readiness", fake_readiness_mod)

    fake_loader_mod = types.ModuleType("app.voice_agent.kb_loader")
    fake_loader_mod.seed_niche = lambda kb, niche: {"ok": True, "chunks": 5}
    monkeypatch.setitem(sys.modules, "app.voice_agent.kb_loader", fake_loader_mod)

    fake_kb_mod = types.ModuleType("app.voice_agent.knowledge_base")
    fake_kb_mod.get_knowledge_base = lambda: object()
    monkeypatch.setitem(sys.modules, "app.voice_agent.knowledge_base", fake_kb_mod)

    # real Celery bound-task pattern: push a request context with retries ==
    # max_retries (final attempt) onto the actual task instance, run, then pop.
    kbr.refresh_niche_task.push_request(retries=kbr.refresh_niche_task.max_retries)
    try:
        with pytest.raises(RuntimeError, match="post_seed_not_ready"):
            kbr.refresh_niche_task.run("solar", _lease_token="tok")
    finally:
        kbr.refresh_niche_task.pop_request()
    # final attempt -> lease released + state failed
    assert "kb:niche_refresh:lease:solar" not in fake_redis.store
    assert fake_redis.store.get("kb:niche_refresh:state:solar") == "failed"


def test_refresh_niche_task_time_limits_have_margin_above_measured_worst_case():
    """ADR-104 A10 (2026-07-15) pin: worker_heavy's first-use-per-process
    Qdrant/fastembed init measured at ~97-99s (bare, non-Celery script; 3
    separate ForkPoolWorker instances, all consistent). A task racing a
    fresh pool-respawn's still-in-flight worker_process_init warm-up blocks
    on the same lock, then does its own ~26s of real work -> ~123s observed
    worst case. 90/120 (the pre-A10 values) left ZERO margin for that path.
    This pins the values so a future edit can't silently regress the margin
    back to zero without a test failure forcing a conscious decision."""
    limits = kbr.refresh_niche_task
    assert limits.soft_time_limit == 180
    assert limits.time_limit == 240
    # keep real margin above the measured ~123s worst case, not just "bigger"
    assert limits.soft_time_limit >= 150
    assert limits.time_limit - limits.soft_time_limit >= 30


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
