"""TRAI 90-din re-consent cool-off tests (consent_ledger + compliance gate wiring).

Pure-python: tmp jsonl stores (monkeypatched), seeded timestamps — no network/DB/LLM.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.marketing import wa_campaign_runner
from app.telephony import consent_ledger as cl


@pytest.fixture(autouse=True)
def _tmp_stores(tmp_path, monkeypatch):
    # Resolver functions, not constants — see test_consent_ledger.py for why.
    # The WhatsApp store is patched too because record_opt_out cross-propagates
    # there; leaving it out writes into the repository's own data/ directory.
    monkeypatch.setattr(cl, "ledger_path", lambda: tmp_path / "consent_ledger.jsonl")
    monkeypatch.setattr(cl, "suppression_path", lambda: tmp_path / "voice_suppression.jsonl")
    monkeypatch.setattr(
        wa_campaign_runner, "_suppression_path", lambda: str(tmp_path / "wa_suppression.jsonl")
    )
    monkeypatch.setattr(cl, "recordings_dir", lambda: tmp_path / "recordings")
    monkeypatch.delenv("RECONSENT_COOLOFF_DAYS", raising=False)
    yield


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _seed_opt_out(phone: str, days_ago: float):
    """Write a suppression + ledger opt_out entry with a backdated timestamp."""
    k = cl._key(phone)
    at = _iso(days_ago)
    cl._append(cl.suppression_path(), {"phone": k, "reason": "test", "channel": "voice", "at": at})
    cl._append(cl.ledger_path(), {"type": "opt_out", "phone": k, "reason": "test", "at": at})


# ----------------------------- helpers ----------------------------- #
def test_days_since_and_blocked_until_none_when_never_opted_out():
    assert cl.days_since_opt_out("9876500010") is None
    assert cl.blocked_until("9876500010") is None
    assert cl.last_opt_out_at("9876500010") is None
    assert cl.reconsent_blocked("9876500010") is False


def test_days_since_opt_out_recent_and_old():
    _seed_opt_out("9876500011", days_ago=10)
    since = cl.days_since_opt_out("9876500011")
    assert since is not None and 9.5 < since < 10.5
    assert cl.reconsent_blocked("9876500011") is True  # within 90d

    _seed_opt_out("9876500012", days_ago=120)
    assert cl.reconsent_blocked("9876500012") is False  # past 90d


def test_blocked_until_is_opt_out_plus_cooloff():
    _seed_opt_out("9876500013", days_ago=30)
    bu = cl.blocked_until("9876500013")
    assert bu is not None
    bu_dt = datetime.fromisoformat(bu)
    expected = datetime.now(timezone.utc) + timedelta(days=60)  # 90 - 30
    assert abs((bu_dt - expected).total_seconds()) < 3600


def test_last_opt_out_at_matches_across_prefixes():
    _seed_opt_out("9876500014", days_ago=5)
    assert cl.last_opt_out_at("+91 98765 00014") is not None
    assert cl.reconsent_blocked("919876500014") is True


# ----------------------------- opt_back_in cool-off ----------------------------- #
def test_opt_back_in_rejected_within_cooloff():
    _seed_opt_out("9876500015", days_ago=10)
    res = cl.opt_back_in("9876500015", source="admin", proof="t1")
    assert res.get("error") == "reconsent_cooloff"
    assert res["reconsent_blocked"] is True
    assert res["suppressed"] is True  # still suppressed — number NOT callable
    assert cl.is_suppressed("9876500015") is True
    assert cl.has_consent("9876500015") is False


def test_opt_back_in_allowed_after_cooloff():
    _seed_opt_out("9876500016", days_ago=100)
    res = cl.opt_back_in("9876500016", source="admin", proof="t2")
    assert res["suppressed"] is False
    assert res["reconsent_blocked"] is False
    assert cl.is_suppressed("9876500016") is False
    assert cl.has_consent("9876500016") is True


def test_opt_back_in_force_override_within_cooloff():
    _seed_opt_out("9876500017", days_ago=5)
    res = cl.opt_back_in("9876500017", source="admin", proof="legal-ok", force=True)
    assert res["suppressed"] is False
    assert cl.is_suppressed("9876500017") is False
    assert cl.has_consent("9876500017") is True
    # audit breadcrumb written
    hist = cl.ledger_for("9876500017")
    assert any(h.get("type") == "reconsent_override" for h in hist)


def test_cooloff_env_override():
    _seed_opt_out("9876500018", days_ago=10)
    # tighten cool-off to 5 days → 10d-old opt-out now allowed
    import os

    os.environ["RECONSENT_COOLOFF_DAYS"] = "5"
    try:
        assert cl.reconsent_blocked("9876500018") is False
        res = cl.opt_back_in("9876500018", source="admin")
        assert res["suppressed"] is False
    finally:
        del os.environ["RECONSENT_COOLOFF_DAYS"]


def test_cooloff_zero_disables_floor():
    _seed_opt_out("9876500019", days_ago=1)
    import os

    os.environ["RECONSENT_COOLOFF_DAYS"] = "0"
    try:
        assert cl.reconsent_blocked("9876500019") is False
        res = cl.opt_back_in("9876500019", source="admin")
        assert res["suppressed"] is False
    finally:
        del os.environ["RECONSENT_COOLOFF_DAYS"]


def test_bad_phone_never_raises():
    assert cl.opt_back_in("")["error"] == "bad_phone"
    assert cl.days_since_opt_out("") is None
    assert cl.blocked_until("") is None
    assert cl.reconsent_blocked("") is False


def test_real_record_opt_out_then_blocked():
    """End-to-end via the real API (not seeded): opt-out then immediate opt-in blocked."""
    cl.record_opt_out("9876500020", reason="test")
    res = cl.opt_back_in("9876500020", source="admin")
    assert res.get("error") == "reconsent_cooloff"
    assert cl.is_suppressed("9876500020") is True


# ----------------------------- compliance gate visibility ----------------------------- #
@pytest.mark.asyncio
async def test_gate_records_cooloff_on_suppressed_promotional(monkeypatch):
    from app.telephony.compliance import CallType, ComplianceGate

    monkeypatch.delenv("COMPLIANCE_ALLOWLIST", raising=False)
    _seed_opt_out("9876500021", days_ago=3)
    gate = ComplianceGate(dnd_checker=None)
    dec = await gate.check("+919876500021", CallType.PROMOTIONAL)
    assert dec.allowed is False
    assert "opted_out" in dec.reasons
    assert dec.checks.get("suppressed") is True
    assert dec.checks.get("reconsent_blocked") is True
    assert dec.checks.get("days_since_opt_out") is not None
    assert dec.checks.get("reconsent_blocked_until")
