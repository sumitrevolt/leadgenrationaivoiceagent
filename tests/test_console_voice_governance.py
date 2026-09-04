"""Governance tests for the console's single test call.

Why this exists: ``start_stream_call`` (app/api/telephony_vobiz.py) is the
canonical dial helper and it applies NO governance of its own — no daily cap,
no per-tenant cap, no kill switch, no circuit breaker, no lead eligibility.
Its existing callers enforce those gates themselves. The console route is a
tenant-facing button, so if the gates are not enforced (and proven enforced)
in that route, the console is simply a path around every one of them.

What is under test is therefore the GOVERNANCE, not the plumbing:
  * the per-tenant counter blocks at N+1 and is isolated per tenant
  * kill switch / circuit breaker block before anything is dialled
  * a tenant-facing failure is reported, never raised and never a 500
  * dry_run is reported as "nothing was dialled", not as a success

No real call, no real Redis, no LLM. Redis and every governance predicate are
monkeypatched; ``start_stream_call`` is always a spy.
"""

import asyncio
from urllib.parse import parse_qs

import pytest
from fastapi import HTTPException

from app.api import product_consoles as pc
from app.telephony import voice_launch as vl

CID_A = "tenant_a"
CID_B = "tenant_b"
PHONE = "+919812345678"


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class FakeRedis:
    """Minimal async Redis with the surface voice_launch actually uses.

    `fail=True` simulates an unavailable counter — the state in which every
    reservation must FAIL CLOSED rather than fall through to the dialer.
    """

    def __init__(self, fail: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.fail = fail

    async def incr(self, key):
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.store[key] = str(int(self.store.get(key) or 0) + 1)
        return int(self.store[key])

    async def get(self, key):
        if self.fail:
            raise RuntimeError("redis unavailable")
        return self.store.get(key)

    async def set(self, key, val, ex=None):
        if self.fail:
            raise RuntimeError("redis unavailable")
        self.store[key] = str(val)

    async def expire(self, key, ttl):
        return None

    async def delete(self, key):
        self.store.pop(key, None)


@pytest.fixture
def redis(monkeypatch):
    """Install a fake counter backend. Yields the instance so tests can inspect
    (or break) it."""

    def _install(fail: bool = False):
        fake = FakeRedis(fail=fail)

        async def _get():
            return fake

        monkeypatch.setattr(vl, "_redis", _get)
        return fake

    return _install


@pytest.fixture(autouse=True)
def _isolated_console_store(monkeypatch):
    """Keep the console's own store in memory so tests never touch data/."""
    mem: dict[str, dict] = {}

    def _read(cid):
        return dict(mem.get(cid) or {})

    def _write(cid, patch):
        rec = dict(mem.get(cid) or {})
        rec.update(patch or {})
        mem[cid] = rec
        return rec

    monkeypatch.setattr(pc, "_read_config", _read)
    monkeypatch.setattr(pc, "_write_config", _write)
    return mem


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch):
    """Keep every test off the filesystem.

    `_resolve_niche` falls through to `clients_store.get_client` and
    `_kb_evidence` to the real knowledge base whenever the tenant config has no
    business.niche / no indexed content. Both take file locks (data/*.lock),
    which is exactly the safe-delete guard that hangs this repo's test runs —
    so they are stubbed. The real `_resolve_niche` precedence logic is covered
    on its own in test_resolve_niche_prefers_configured_niche.
    """
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client", lambda cid: {}, raising=False
    )
    monkeypatch.setattr(
        pc, "_kb_evidence",
        lambda cid, cfg: {"namespace": f"client:{cid}", "chunks": 0,
                          "backend": "fake", "sources": []},
    )


def test_resolve_niche_prefers_configured_niche(monkeypatch):
    """The real `_resolve_niche` precedence: console config, then the client
    record, then "general"."""
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: {"niche": "from_client_record"},
        raising=False,
    )
    assert pc._resolve_niche("c", {"business": {"niche": "from_config"}}) == "from_config"
    assert pc._resolve_niche("c", {}) == "from_client_record"
    monkeypatch.setattr(
        "app.marketing.clients_store.get_client",
        lambda cid: (_ for _ in ()).throw(RuntimeError("store down")),
        raising=False,
    )
    assert pc._resolve_niche("c", {}) == "general", "must degrade, never raise"


@pytest.fixture
def no_gates(monkeypatch):
    """All governance predicates green, so a test can target exactly one gate."""

    async def _false(*a, **k):
        return False

    async def _eligible(*a, **k):
        return vl.EligibilityResult(True, vl.SkipReason.NONE, {})

    monkeypatch.setattr(vl, "admin_kill_engaged", lambda: False)
    monkeypatch.setattr(vl, "circuit_open", _false)
    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", _eligible)


@pytest.fixture
def dial_spy(monkeypatch):
    """Replace the dialer with a spy. Nothing can be dialled during a test."""
    calls: list[dict] = []

    async def _fake(**kw):
        calls.append(kw)
        return {"placed": True, "dry_run": bool(kw.get("dry_run")), "stream_token": "tok"}

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _fake, raising=False)
    return calls


def _call(**kw):
    return asyncio.run(pc.automation_test_call(body=pc.TestCallIn(**kw), client_id=CID_A))


# --------------------------------------------------------------------------- #
# 1-2. Per-tenant cap
# --------------------------------------------------------------------------- #
def test_tenant_cap_blocks_the_n_plus_first_reservation(redis):
    redis()
    for i in range(3):
        res = asyncio.run(vl.reserve_tenant_slot(CID_A, 3))
        assert res.ok is True, f"reservation {i + 1} of 3 must succeed"

    blocked = asyncio.run(vl.reserve_tenant_slot(CID_A, 3))
    assert blocked.ok is False
    assert blocked.reason == "tenant_daily_limit_reached"
    assert blocked.count == blocked.cap == 3


def test_rejected_reservation_does_not_permanently_inflate_the_counter(redis):
    """The over-cap increment rolls itself back, so the next day's siblings and
    any concurrent reader see `cap`, not cap+N."""
    fake = redis()
    asyncio.run(vl.reserve_tenant_slot(CID_A, 1))
    assert asyncio.run(vl.reserve_tenant_slot(CID_A, 1)).ok is False
    key = vl._tenant_counter_key(CID_A)
    assert int(fake.store[key]) == 1, "counter must be rolled back to the cap, not left above it"


def test_tenant_counters_do_not_collide_across_tenants(redis):
    redis()
    for _ in range(2):
        assert asyncio.run(vl.reserve_tenant_slot(CID_A, 2)).ok is True
    # Tenant A is now at its cap of 2...
    assert asyncio.run(vl.reserve_tenant_slot(CID_A, 2)).ok is False
    # ...and tenant B, same IST day, must be completely unaffected.
    res_b = asyncio.run(vl.reserve_tenant_slot(CID_B, 2))
    assert res_b.ok is True
    assert res_b.count == 1


def test_tenant_cap_is_clamped_to_the_platform_ceiling():
    """The console accepts max_calls_per_day up to 5000. A tenant-supplied
    number must never raise a platform spend/compliance limit."""
    assert vl.tenant_cap(5000) == vl._DAILY_CAP_CEILING
    assert vl.tenant_cap(0) == 1
    assert vl.tenant_cap(-5) == 1
    assert vl.tenant_cap("not-a-number") == vl.tenant_cap(None)  # falls back, never raises
    assert 1 <= vl.tenant_cap(50) <= vl._DAILY_CAP_CEILING


def test_reservation_fails_closed_when_redis_is_unavailable(redis):
    """An unavailable counter must BLOCK, not allow."""
    redis(fail=True)
    res = asyncio.run(vl.reserve_tenant_slot(CID_A, 10))
    assert res.ok is False
    assert res.reason == "counter_unavailable"
    assert res.count == -1


def test_release_tenant_slot_returns_the_slot(redis):
    fake = redis()
    asyncio.run(vl.reserve_tenant_slot(CID_A, 5))
    assert asyncio.run(vl.release_tenant_slot(CID_A)) == 0
    assert int(fake.store[vl._tenant_counter_key(CID_A)]) == 0


# --------------------------------------------------------------------------- #
# 3-4. Kill switch / circuit breaker block before the dial
# --------------------------------------------------------------------------- #
def test_kill_switch_blocks_and_places_no_call(redis, no_gates, dial_spy, monkeypatch):
    redis()
    monkeypatch.setattr(vl, "admin_kill_engaged", lambda: True)

    out = _call(to=PHONE)

    assert out["placed"] is False
    assert out["dialed"] is False
    assert dial_spy == [], "a kill-switched call must never reach the dialer"
    assert out["reason"] == "admin_kill"
    assert "Blocked at 'admin_kill'" in out["note"]


def test_circuit_open_blocks_and_places_no_call(redis, no_gates, dial_spy, monkeypatch):
    redis()

    async def _open(*a, **k):
        return True

    monkeypatch.setattr(vl, "circuit_open", _open)

    out = _call(to=PHONE)

    assert out["dialed"] is False
    assert dial_spy == [], "an open circuit must never reach the dialer"
    assert out["reason"] == "circuit_open"


def test_eligibility_gate_blocks_and_places_no_call(redis, no_gates, dial_spy, monkeypatch):
    redis()

    async def _ineligible(*a, **k):
        return vl.EligibilityResult(False, vl.SkipReason.OPTED_OUT, {"call_type": "transactional"})

    monkeypatch.setattr(vl, "is_lead_eligible_for_voice_call", _ineligible)

    out = _call(to=PHONE)

    assert out["dialed"] is False
    assert dial_spy == []
    assert out["reason"] == vl.SkipReason.OPTED_OUT


def test_tenant_daily_limit_blocks_and_places_no_call(redis, no_gates, dial_spy, _isolated_console_store):
    redis()
    _isolated_console_store[CID_A] = {"automation": {"max_calls_per_day": 1}}
    _call(to=PHONE, dry_run=False)  # consumes the single slot

    out = _call(to=PHONE, dry_run=False)

    assert out["dialed"] is False
    assert out["reason"] == "tenant_daily_limit_reached"
    assert len(dial_spy) == 1, "the second call must not reach the dialer"


# --------------------------------------------------------------------------- #
# 5. template_id / voice_role threading + backwards compatibility
# --------------------------------------------------------------------------- #
def test_answer_stream_qs_carries_template_and_role_when_supplied():
    from app.api.telephony_vobiz import _answer_stream_qs

    qs = parse_qs(_answer_stream_qs(
        "salon", "c1", lead_phone=PHONE,
        template_id="lead_qualify", voice_role="booking_agent",
    ))

    assert qs["template_id"] == ["lead_qualify"]
    assert qs["voice_role"] == ["booking_agent"]
    assert qs["niche"] == ["salon"]
    assert qs["lead_phone"] == [PHONE]


def test_answer_stream_qs_omits_template_and_role_when_absent():
    """Backwards compatibility: the four pre-existing start_stream_call callers
    pass neither kwarg, and their URLs must be byte-for-byte unchanged."""
    from app.api.telephony_vobiz import _answer_stream_qs

    qs = parse_qs(_answer_stream_qs("salon", "c1", lead_phone=PHONE, lead_id="lead-xyz"))

    assert "template_id" not in qs
    assert "voice_role" not in qs
    # The existing wire keys must still be intact.
    assert qs["niche"] == ["salon"]
    assert qs["client_id"] == ["c1"]
    assert qs["lead_phone"] == [PHONE]
    assert qs["crm_lead_id"] == ["lead-xyz"], "crm_lead_id convention must not regress"


def test_start_stream_call_forwards_template_and_role(redis, no_gates, dial_spy):
    redis()
    _call(to=PHONE, template_id="appointment_reminder")

    assert dial_spy, "the call must have reached the dialer"
    kw = dial_spy[0]
    assert kw["template_id"] == "appointment_reminder"
    # appointment_reminder is spoken by the booking persona, not the default.
    assert kw["voice_role"] == "booking_agent"
    # client_id must reach the dialer: it is what namespaces the tenant's knowledge.
    assert kw["client_id"] == CID_A


# --------------------------------------------------------------------------- #
# 6. The endpoint never raises and never 500s
# --------------------------------------------------------------------------- #
def test_redis_unavailable_blocks_instead_of_dialling(redis, no_gates, dial_spy):
    """Fail-CLOSED: if we cannot count the call, we must not place it."""
    redis(fail=True)

    out = _call(to=PHONE)

    assert out["ok"] is True
    assert out["dialed"] is False
    assert dial_spy == []
    assert out["reason"] == "counter_unavailable"


@pytest.mark.parametrize(
    "gate,expected",
    [
        ("admin_kill_engaged", "admin_kill_unavailable"),
        ("circuit_open", "circuit_unavailable"),
        ("is_lead_eligible_for_voice_call", "eligibility_error"),
    ],
)
def test_every_gate_error_is_reported_not_raised(
    redis, no_gates, dial_spy, monkeypatch, gate, expected
):
    """A predicate that EXPLODES must still yield a structured result naming the
    gate that failed — never an exception, never a 500, and never a dial."""
    redis()

    def _boom(*a, **k):
        raise RuntimeError("boom")

    async def _aboom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(vl, gate, _boom if gate == "admin_kill_engaged" else _aboom)

    out = _call(to=PHONE)

    assert out["ok"] is True, f"{gate} blowing up must not surface as an error status"
    assert out["dialed"] is False, f"{gate} failing must not dial"
    assert out["reason"] == expected
    assert dial_spy == [], f"{gate} failing must not reach the dialer"


def test_dialer_exception_is_reported_not_raised(redis, no_gates, monkeypatch):
    redis()

    async def _explode(**kw):
        raise RuntimeError("vobiz down")

    monkeypatch.setattr("app.api.telephony_vobiz.start_stream_call", _explode, raising=False)

    out = _call(to=PHONE)

    assert out["ok"] is True
    assert out["dialed"] is False
    assert out["reason"] == "internal_error"


def test_invalid_phone_is_a_400_not_a_500(redis, no_gates, dial_spy):
    redis()
    with pytest.raises(HTTPException) as exc:
        _call(to="123")
    assert exc.value.status_code == 400
    assert dial_spy == []


# --------------------------------------------------------------------------- #
# 7. dry_run honesty
# --------------------------------------------------------------------------- #
def test_dry_run_places_no_call_and_says_so(redis, no_gates, dial_spy):
    redis()

    out = _call(to=PHONE)  # dry_run defaults to True

    assert dial_spy[0]["dry_run"] is True, "the dialer must be told not to dial"
    assert out["dialed"] is False, "a dry run must not claim a dialled call"
    assert out["dry_run"] is True
    assert "NO CALL WAS PLACED" in out["note"], "the response must say plainly that nothing was dialled"


def test_dry_run_does_not_consume_the_tenant_quota(redis, no_gates, dial_spy, _isolated_console_store):
    """Otherwise a tenant pressing the dry-run button a few times would exhaust
    their daily limit without a single call ever ringing."""
    fake = redis()
    _isolated_console_store[CID_A] = {"automation": {"max_calls_per_day": 2}}
    for _ in range(5):
        out = _call(to=PHONE)
        assert out["ok"] is True
        assert out["reason"] != "tenant_daily_limit_reached"

    key = vl._tenant_counter_key(CID_A)
    assert int(fake.store.get(key) or 0) == 0


def test_live_call_reports_dialled(redis, no_gates, dial_spy):
    redis()

    out = _call(to=PHONE, dry_run=False)

    assert dial_spy[0]["dry_run"] is False
    assert out["dialed"] is True
    assert out["placed"] is True
    assert out["reason"] == ""


# --------------------------------------------------------------------------- #
# 8. A blocked launch writes nothing and explains why
# --------------------------------------------------------------------------- #
def test_blocked_launch_writes_nothing_and_explains_why(redis, no_gates, dial_spy, monkeypatch):
    redis()
    writes: list[tuple] = []
    monkeypatch.setattr(pc, "_write_config", lambda cid, patch: writes.append((cid, patch)))
    monkeypatch.setattr(vl, "admin_kill_engaged", lambda: True)

    out = _call(to=PHONE)

    assert writes == [], "a blocked test call must not mutate tenant config"
    assert out["dialed"] is False
    assert "Blocked at 'admin_kill'" in out["note"]
    assert out["steps"], "the caller must get a trace of what was checked"
    assert out["steps"][-1]["ok"] is False


def test_missing_knowledge_and_template_are_allowed_but_reported(
    redis, no_gates, dial_spy, _isolated_console_store
):
    """A test call is how you discover the config is incomplete — blocking it
    would make the product untestable. But the response must never imply a
    quality the config does not support."""
    redis()
    _isolated_console_store[CID_A] = {"automation": {"max_calls_per_day": 5}}

    out = _call(to=PHONE)

    assert out["ok"] is True
    assert out["placed"] is True, "an incomplete config must not block the test call"
    assert out["dialed"] is False, "but it is still a dry run"
    joined = " ".join(out["warnings"]).lower()
    assert "knowledge base is empty" in joined
    assert "no call template is bound" in joined
    assert out["template_id"] == ""
    assert out["knowledge_chunks"] == 0


def test_configured_tenant_reports_no_missing_pieces(
    redis, no_gates, dial_spy, monkeypatch, _isolated_console_store
):
    """The other half of the honesty contract: a fully configured tenant gets
    no warnings, so `warnings` never cries wolf."""
    redis()
    monkeypatch.setattr(
        pc, "_kb_evidence",
        lambda cid, cfg: {"namespace": f"client:{cid}", "chunks": 12,
                          "backend": "fake", "sources": []},
    )
    _isolated_console_store[CID_A] = {
        "automation": {"max_calls_per_day": 5, "template_id": "lead_qualify"}
    }

    out = _call(to=PHONE)

    assert out["knowledge_chunks"] == 12
    assert out["template_id"] == "lead_qualify"
    assert out["warnings"] == []


def test_unknown_template_is_refused(redis, no_gates, dial_spy):
    redis()

    out = _call(to=PHONE, template_id="not_a_real_template")

    assert out["placed"] is False
    assert out["reason"] == "unknown_template"
    assert dial_spy == []
