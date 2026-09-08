"""Feature-flag system tests (Phase 1 SaaS infra upgrade).

Free-stack, NO real Redis — InMemoryCache inject + pure-eval. asyncio_mode=auto
(pyproject [tool.pytest.ini_options]) → async def test_* seedhe chalte (no decorator).
"""

from app.infrastructure.feature_flags import (
    FeatureFlag,
    FeatureFlagService,
    FeatureState,
    evaluate_flag,
)


# --------------------------------------------------------------------------- #
# PURE eval (no storage, no env) — deterministic logic
# --------------------------------------------------------------------------- #
def test_evaluate_disabled_and_unknown():
    assert evaluate_flag(None) is False
    assert evaluate_flag({}) is False
    assert evaluate_flag({"state": "disabled"}) is False
    assert evaluate_flag({"state": "garbage-state"}) is False  # coerce -> disabled


def test_evaluate_enabled_all():
    assert evaluate_flag({"state": "enabled_all"}) is True
    assert evaluate_flag({"state": "enabled_all"}, tenant_id="t1") is True


def test_evaluate_enabled_tenants():
    f = {"state": "enabled_tenants", "enabled_tenants": ["t1", "t2"]}
    assert evaluate_flag(f, tenant_id="t1") is True
    assert evaluate_flag(f, tenant_id="t3") is False
    assert evaluate_flag(f, tenant_id=None) is False  # no tenant -> not targeted


def test_evaluate_percentage_bounds():
    base = {"key": "k", "state": "enabled_percentage"}
    assert evaluate_flag({**base, "percentage": 0}, tenant_id="t1") is False
    assert evaluate_flag({**base, "percentage": 100}, tenant_id="t1") is True


def test_evaluate_percentage_deterministic():
    f = {"key": "promo", "state": "enabled_percentage", "percentage": 50}
    # same input -> same bucket, har call (cross-process bhi sha256 se stable)
    assert evaluate_flag(f, tenant_id="tenant-xyz") == evaluate_flag(f, tenant_id="tenant-xyz")


def test_evaluate_percentage_distribution():
    f = {"key": "roll", "state": "enabled_percentage", "percentage": 30}
    hits = sum(1 for i in range(2000) if evaluate_flag(f, tenant_id=f"t{i}"))
    # ~30% of 2000 = 600; sha256 uniform -> well within this wide band (no flake)
    assert 500 <= hits <= 700


def test_evaluate_percentage_key_isolates_buckets():
    # same tenant, different flag-key -> independent buckets (ek flag dusre ko leak na kare)
    a = [
        evaluate_flag(
            {"key": "A", "state": "enabled_percentage", "percentage": 50}, tenant_id=f"t{i}"
        )
        for i in range(200)
    ]
    b = [
        evaluate_flag(
            {"key": "B", "state": "enabled_percentage", "percentage": 50}, tenant_id=f"t{i}"
        )
        for i in range(200)
    ]
    assert a != b  # extremely unlikely to be identical if buckets are key-salted


# --------------------------------------------------------------------------- #
# Service with injected InMemoryCache (no Redis required)
# --------------------------------------------------------------------------- #
def _mem_service() -> FeatureFlagService:
    from app.cache import InMemoryCache

    mem = InMemoryCache()

    async def _getter():
        return mem

    return FeatureFlagService(redis_getter=_getter)


async def test_set_get_delete_roundtrip(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAGS", "1")
    svc = _mem_service()
    assert await svc.get_flag("x") is None
    assert (
        await svc.set_flag(FeatureFlag(key="x", state=FeatureState.ENABLED_ALL, description="d"))
        is True
    )
    got = await svc.get_flag("x")
    assert got is not None and got.state == FeatureState.ENABLED_ALL and got.description == "d"
    assert any(f.key == "x" for f in await svc.get_all_flags())
    assert await svc.delete_flag("x") is True
    assert await svc.get_flag("x") is None
    assert await svc.delete_flag("x") is False  # already gone


async def test_is_enabled_respects_master_gate(monkeypatch):
    svc = _mem_service()
    await svc.set_flag(FeatureFlag(key="feat", state=FeatureState.ENABLED_ALL))
    monkeypatch.setenv("FEATURE_FLAGS", "0")
    assert await svc.is_enabled("feat", tenant_id="t1") is False  # master OFF -> dormant
    monkeypatch.setenv("FEATURE_FLAGS", "1")
    assert await svc.is_enabled("feat", tenant_id="t1") is True  # master ON -> live


async def test_is_enabled_tenant_targeting(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAGS", "1")
    svc = _mem_service()
    await svc.set_flag(
        FeatureFlag(key="beta", state=FeatureState.ENABLED_TENANTS, enabled_tenants=["good"])
    )
    assert await svc.is_enabled("beta", tenant_id="good") is True
    assert await svc.is_enabled("beta", tenant_id="bad") is False
    assert await svc.is_enabled("no-such-flag", tenant_id="good") is False  # unknown -> default-off
    assert await svc.is_enabled("", tenant_id="good") is False  # empty key -> False


async def test_is_enabled_never_raises_on_broken_storage(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAGS", "1")

    async def _broken():
        raise RuntimeError("redis down")

    svc = FeatureFlagService(redis_getter=_broken)
    # storage broken -> fail-safe False, koi exception nahi
    assert await svc.is_enabled("anything", tenant_id="t1") is False
    assert await svc.get_all_flags() == []


async def test_created_at_preserved_on_update(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAGS", "1")
    svc = _mem_service()
    await svc.set_flag(FeatureFlag(key="p", state=FeatureState.DISABLED))
    first = await svc.get_flag("p")
    await svc.set_flag(FeatureFlag(key="p", state=FeatureState.ENABLED_ALL))
    second = await svc.get_flag("p")
    assert second.created_at == first.created_at  # created_at preserve
    assert second.state == FeatureState.ENABLED_ALL  # state updated


async def test_percentage_rollout_via_service(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAGS", "1")
    svc = _mem_service()
    await svc.set_flag(
        FeatureFlag(key="grad", state=FeatureState.ENABLED_PERCENTAGE, percentage=100)
    )
    assert await svc.is_enabled("grad", tenant_id="anyone") is True
    await svc.set_flag(FeatureFlag(key="grad", state=FeatureState.ENABLED_PERCENTAGE, percentage=0))
    assert await svc.is_enabled("grad", tenant_id="anyone") is False
