"""Unit tests for the telephony / compliance / scaling production upgrades.

Self-contained: uses asyncio.new_event_loop() (no pytest-asyncio dependency) and
forces the call-state store into local mode so no Redis is required.
"""

import asyncio
import os
from datetime import datetime

# --- module imports double as a circular-reference / import-health check --------
from app.api.health import prometheus_metrics  # noqa: F401
from app.tasks.scraping import enrich_lead_data  # noqa: F401
from app.telephony.call_manager import CallManager, CallRequest
from app.telephony.call_state import RedisCallStore
from app.telephony.compliance import IST, CallType, ComplianceGate
from app.utils.dnd_checker import DNDCheckResult
from app.voice_agent.amd import AnsweringMachineDetector


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_app_imports_and_mounts_telephony_webhooks():
    """App imports cleanly (no circular refs) and telephony routes are mounted."""
    from app.main import app

    # FastAPI 0.139 stores included routers as lazy wrappers in app.routes;
    # OpenAPI is the stable effective-route view across FastAPI versions.
    paths = set(app.openapi().get("paths", {}))
    # twilio/exotel webhook routes removed (provider deleted) - Vobiz uses /api/telephony/vobiz/*
    assert "/api/webhooks/vobiz/answer" in paths
    assert "/api/webhooks/health" in paths


def test_call_state_rebinds_redis_client_per_event_loop(monkeypatch):
    """A Redis client created in one loop must never be reused in another."""

    class _FakeRedis:
        def __init__(self):
            self.pings = 0

        async def ping(self):
            self.pings += 1

        async def zadd(self, *_args, **_kwargs):
            return 1

        async def zpopmin(self, *_args, **_kwargs):
            return []

    clients = []

    def _from_url(*_args, **_kwargs):
        client = _FakeRedis()
        clients.append(client)
        return client

    import redis.asyncio as aioredis

    monkeypatch.setattr(aioredis, "from_url", _from_url)
    store = RedisCallStore()

    loop1 = asyncio.new_event_loop()
    loop2 = asyncio.new_event_loop()
    try:
        first = loop1.run_until_complete(store._redis())
        second = loop2.run_until_complete(store._redis())
        assert first is clients[0]
        assert second is clients[1]
        assert first is not second
    finally:
        loop1.close()
        loop2.close()


def test_dnd_result_has_verified_flag():
    r = DNDCheckResult(phone="x", is_dnd=False, checked_at=datetime.now(), source="vobiz")
    assert r.verified is True  # default = verified
    r2 = DNDCheckResult(
        phone="x", is_dnd=False, checked_at=datetime.now(), source="fallback", verified=False
    )
    assert r2.verified is False


def test_compliance_fails_closed_on_unverified_dnd():
    """Promotional call must be BLOCKED when DND lookup is unverified (fail-closed)."""
    os.environ["COMPLIANCE_ENABLED"] = "1"
    os.environ["COMPLIANCE_ALLOWLIST"] = ""

    class _FakeDND:
        async def check_single(self, phone):
            return DNDCheckResult(
                phone=phone,
                is_dnd=False,
                checked_at=datetime.now(),
                source="fallback",
                verified=False,
            )

    gate = ComplianceGate(dnd_checker=_FakeDND())
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=IST)  # inside the promo window
    decision = _run(gate.check("+919876543210", CallType.PROMOTIONAL, now=noon))
    assert decision.allowed is False
    assert "dnd_lookup_failed" in decision.reasons


def test_compliance_transactional_allowed_in_window():
    """Transactional calls skip DND; a valid number in-window is allowed."""
    os.environ["COMPLIANCE_ENABLED"] = "1"
    os.environ["COMPLIANCE_ALLOWLIST"] = ""
    gate = ComplianceGate()
    noon = datetime(2026, 1, 1, 12, 0, tzinfo=IST)
    decision = _run(gate.check("+919876543210", CallType.TRANSACTIONAL, now=noon))
    assert decision.allowed is True


def test_call_state_local_priority_and_registry():
    store = RedisCallStore()
    store._checked = True
    store._is_redis = False  # force deterministic local fallback (no Redis)

    _run(store.enqueue(5, "low", {"n": 1}))
    _run(store.enqueue(1, "high", {"n": 2}))
    first = _run(store.dequeue())
    assert first is not None and first[1] == "high"  # priority 1 dialed first
    second = _run(store.dequeue())
    assert second[1] == "low"
    assert _run(store.dequeue()) is None  # empty -> None (non-blocking)

    _run(store.register("c1", {"phone": "x"}))
    assert _run(store.active_count()) == 1
    _run(store.unregister("c1"))
    assert _run(store.active_count()) == 0


def test_call_request_payload_roundtrip():
    req = CallRequest(
        lead_id="l1",
        phone_number="+919876543210",
        campaign_id="c1",
        niche="solar",
        client_name="Acme",
        client_service="Solar",
        script_name="s",
        lead_data={"a": 1},
        priority=3,
        scheduled_time=datetime(2026, 6, 9, 10, 0),
    )
    payload = CallManager._request_to_payload(req)
    assert isinstance(payload["scheduled_time"], str)  # JSON-safe
    back = CallManager._payload_to_request(payload)
    assert back.lead_id == "l1" and back.priority == 3
    assert back.scheduled_time == datetime(2026, 6, 9, 10, 0)


def test_amd_decision_and_voicemail():
    d = AnsweringMachineDetector()
    msg = d.voicemail_message(client_name="Acme", callback_number="+919876543210")
    assert isinstance(msg, str) and len(msg) > 10
