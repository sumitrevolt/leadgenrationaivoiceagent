"""Contract for Product-2 self-serve voice calling (council decision 2026-07-06).

The flat-fee "AI calls your leads" was admin-only. These routes let the customer
trigger + see it — but SAFELY: gated default-OFF (inert), every call routed through
`queue_call` (the sole compliance chokepoint — cannot be bypassed here), client_id
forced from the JWT (IDOR — a customer can only queue its OWN leads), anti-joined
against CallLog so no lead is re-dialled. No real call is placed in these tests
(the call manager is faked).
"""

from __future__ import annotations

from datetime import datetime

import pytest


def _iso_db(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.models.base as base_mod

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    base_mod.Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(base_mod, "_engine", engine)
    monkeypatch.setattr(base_mod, "_SessionLocal", Session)
    return Session


def _seed(Session):
    from app.models.call_log import CallLog
    from app.models.lead import Lead, LeadStatus

    s = Session()
    try:
        s.add_all(
            [
                Lead(
                    id="lead_a1",
                    company_name="A Alpha",
                    phone="9990000001",
                    assigned_to="client_a",
                    status=LeadStatus.NEW,
                    lead_score=80,
                ),
                Lead(
                    id="lead_a2",
                    company_name="A Gamma",
                    phone="9990000002",
                    assigned_to="client_a",
                    status=LeadStatus.NEW,
                    lead_score=40,
                ),
                Lead(
                    id="lead_b1",
                    company_name="B Beta",
                    phone="9990000003",
                    assigned_to="client_b",
                    status=LeadStatus.NEW,
                    lead_score=90,
                ),
            ]
        )
        # lead_a1 already called -> must be anti-joined out of the call-queue
        s.add(
            CallLog(
                id="cl1",
                client_id="client_a",
                lead_id="lead_a1",
                to_number="9990000001",
                initiated_at=datetime.utcnow(),
            )
        )
        s.commit()
    finally:
        s.close()


class _FakeMgr:
    def __init__(self):
        self.seen = []

    async def queue_call(self, req):
        self.seen.append(req)
        return "callid-" + req.lead_id  # plain id => "queued"


async def test_call_queue_503_when_flag_off(monkeypatch):
    monkeypatch.delenv("CUSTOMER_VOICE_SELFSERVE", raising=False)
    from fastapi import HTTPException

    from app.api.customer_dashboard import customer_voice_call_queue

    with pytest.raises(HTTPException) as ei:
        await customer_voice_call_queue(limit=20, client_id="client_a")
    assert ei.value.status_code == 503  # inert by default — no calls, no side effects


async def test_call_queue_403_for_marketing_only_plan(monkeypatch):
    """Regression guard (2026-07-07 audit finding): a Marketing-only ("starter")
    customer must NOT get free AI voice calls just because CUSTOMER_VOICE_SELFSERVE
    happens to be on — AI Voice is a separate standalone product. queue_call()'s
    own minute/lead-quota checks fail-OPEN for non-metered plans, so this
    route-level product check is the only real gate for entitlement."""
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    from fastapi import HTTPException

    from app.api.customer_dashboard import customer_voice_call_queue

    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record",
        lambda cid: {"business_name": "A", "niche": "salon", "product": "marketing"},
    )
    with pytest.raises(HTTPException) as ei:
        await customer_voice_call_queue(limit=20, client_id="client_a")
    assert ei.value.status_code == 403


async def test_call_queue_allowed_for_combo_plan(monkeypatch):
    """Combo-plan customers (both products) must still be allowed through the gate."""
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    Session = _iso_db(monkeypatch)
    _seed(Session)
    fake = _FakeMgr()
    monkeypatch.setattr("app.api.customer_dashboard._voice_call_manager", lambda: fake)
    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record",
        lambda cid: {"business_name": "A", "niche": "salon", "product": "combo"},
    )
    from app.api.customer_dashboard import customer_voice_call_queue

    res = await customer_voice_call_queue(limit=20, client_id="client_a")
    assert res["ok"]


async def test_call_queue_scopes_to_own_client_and_skips_called(monkeypatch):
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    Session = _iso_db(monkeypatch)
    _seed(Session)
    fake = _FakeMgr()
    monkeypatch.setattr("app.api.customer_dashboard._voice_call_manager", lambda: fake)
    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record",
        lambda cid: {"business_name": "A", "niche": "salon", "product": "voice"},
    )
    from app.api.customer_dashboard import customer_voice_call_queue

    res = await customer_voice_call_queue(limit=20, client_id="client_a")
    assert (
        res["ok"] and res["queued"] == 1
    )  # only lead_a2 (a1 already called, b1 is another tenant)
    phones = {r.phone_number for r in fake.seen}
    assert phones == {"9990000002"}
    assert all(r.client_id == "client_a" for r in fake.seen)  # IDOR: never another client's lead
    assert "9990000003" not in phones  # client_b's lead NEVER queued


async def test_call_queue_honors_compliance_block(monkeypatch):
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    Session = _iso_db(monkeypatch)
    _seed(Session)

    class _Blocker:
        async def queue_call(self, req):
            return "compliance_blocked_" + req.lead_id  # gate refused

    monkeypatch.setattr("app.api.customer_dashboard._voice_call_manager", lambda: _Blocker())
    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record", lambda cid: {"product": "voice"}
    )
    from app.api.customer_dashboard import customer_voice_call_queue

    res = await customer_voice_call_queue(limit=20, client_id="client_a")
    assert res["queued"] == 0 and res["blocked"] >= 1
    assert "compliance_blocked" in res["reasons"]  # the route respects the gate's refusal


def test_queue_status_counts_scoped(monkeypatch):
    Session = _iso_db(monkeypatch)
    _seed(Session)
    from app.api.customer_dashboard import customer_voice_queue_status

    res = customer_voice_queue_status(client_id="client_a")
    assert res["leads_with_phone"] == 2  # a1 + a2 (NOT b1 — other tenant)
    assert res["already_called"] == 1  # lead_a1
    assert res["remaining_to_call"] == 1
    assert res["self_serve_enabled"] in (True, False)


class _FakeRedis:
    """Minimal async Redis for the in-flight-dedup + daily-cap path."""

    def __init__(self, inflight=None, dcount=0):
        self._inflight = set(inflight or [])
        self._d = int(dcount)

    async def smembers(self, k):
        return set(self._inflight)

    async def get(self, k):
        return str(self._d).encode() if self._d else None

    async def sadd(self, k, *v):
        self._inflight.update(v)

    async def expire(self, k, t):
        return True

    async def incr(self, k):
        self._d += 1
        return self._d


async def test_call_queue_skips_inflight_leads(monkeypatch):
    # TOCTOU fix (sec-audit): a lead queued-but-not-yet-CallLog'd (in-flight) must NOT
    # be re-queued — else the same person gets re-dialled in the queue->log window.
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    Session = _iso_db(monkeypatch)
    _seed(Session)
    fake = _FakeMgr()
    monkeypatch.setattr("app.api.customer_dashboard._voice_call_manager", lambda: fake)
    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record",
        lambda cid: {"business_name": "A", "niche": "salon", "product": "voice"},
    )
    fr = _FakeRedis(inflight={"lead_a2"})  # a2 already in-flight

    async def _getr():
        return fr

    monkeypatch.setattr("app.cache.get_redis_client", _getr, raising=False)
    from app.api.customer_dashboard import customer_voice_call_queue

    res = await customer_voice_call_queue(limit=20, client_id="client_a")
    assert res["queued"] == 0  # a1 already-called, a2 in-flight -> nothing re-dialled
    assert len(fake.seen) == 0


async def test_call_queue_daily_cap(monkeypatch):
    monkeypatch.setenv("CUSTOMER_VOICE_SELFSERVE", "1")
    monkeypatch.setenv("VOICE_SELFSERVE_DAILY_CAP", "1")
    Session = _iso_db(monkeypatch)
    _seed(Session)
    fake = _FakeMgr()
    monkeypatch.setattr("app.api.customer_dashboard._voice_call_manager", lambda: fake)
    monkeypatch.setattr(
        "app.api.customer_dashboard._client_record", lambda cid: {"product": "voice"}
    )
    fr = _FakeRedis(dcount=1)  # already used 1 today, cap=1 -> reached immediately

    async def _getr():
        return fr

    monkeypatch.setattr("app.cache.get_redis_client", _getr, raising=False)
    from app.api.customer_dashboard import customer_voice_call_queue

    res = await customer_voice_call_queue(limit=20, client_id="client_a")
    assert res["daily_cap_reached"] is True
    assert res["queued"] == 0
