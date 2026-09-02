"""Voice close-signal -> consent record -> autopilot enrolment (the A bridge).

Before this, a customer saying "haan, WhatsApp bhej do" produced exactly one
durable write: a sales_pipeline deal. The consent itself was never recorded, so
sales-autopilot eligibility - which fails CLOSED on a missing consent_basis -
refused that number forever. Harvested leads therefore had no lawful route into
follow-up, and the whole automated chain stopped at the call.

These tests pin the two writes the close signal must now make, and pin the safety
property that matters more than either: no consent record => no enrolment.
"""

from __future__ import annotations

import pytest

from app.platform.sales_autopilot import store as ap_store
from app.telephony import consent_ledger
from app.voice_agent import telecaller_brain as TB

PHONE = "+919812345678"


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Every store redirected; no network, no real ledger.

    TelecallerBrain refuses to construct without an LLM provider, and that check
    reads state captured at IMPORT time - so setting an env var here would be too
    late and the test would depend on the developer's .env (R4). Declare the
    provider directly instead; nothing in this file exercises the LLM.
    """
    from app.voice_agent import free_ai as _free_ai

    monkeypatch.setattr(_free_ai, "PROVIDERS_AVAILABLE", {"groq": True}, raising=False)
    monkeypatch.setattr(ap_store, "_DIR", str(tmp_path))
    monkeypatch.setattr(ap_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(ap_store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))
    monkeypatch.setattr(consent_ledger, "ledger_path", lambda: tmp_path / "consent.jsonl")
    monkeypatch.setattr(consent_ledger, "suppression_path", lambda: tmp_path / "suppression.jsonl")
    # The close signal also writes a deal and may spawn a WhatsApp task; neither
    # is under test here and both must stay inert.
    from app.marketing import sales_pipeline

    monkeypatch.setattr(sales_pipeline, "upsert_deal", lambda *a, **k: {})
    monkeypatch.delenv("VOICE_CLOSE_WHATSAPP", raising=False)
    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)


def _brain(phone=PHONE):
    b = TB.TelecallerBrain(niche="beauty_salon", client_name="Test Salon")
    if phone:
        b.caller_phone = phone
    return b


def test_close_signal_records_consent_with_source_and_proof():
    b = _brain()
    b._on_close_signal()

    assert consent_ledger.has_consent(PHONE, scope="all") is True
    entries = consent_ledger.ledger_for(PHONE)
    assert entries, "consent must be written to the ledger, not just implied"
    sources = [str(e.get("source") or "") for e in entries]
    assert "verbal_call_close" in sources, sources


def test_close_signal_enrols_prospect_with_a_consent_basis():
    b = _brain()
    b._on_close_signal()

    rows = ap_store.list_prospects(limit=100)
    assert len(rows) == 1, rows
    rec = rows[0]
    assert rec.get("consent_basis") == "verbal_call_close"
    assert rec.get("status") == ap_store.STATUS_NEW
    assert "9812345678" in str(rec.get("phone"))


def test_enrolled_prospect_actually_passes_the_consent_gate():
    """The point of the bridge: the number becomes contactable."""
    from app.platform.sales_autopilot import eligibility as elig
    from app.platform.sales_autopilot import policy as policy_mod

    b = _brain()
    b._on_close_signal()
    rec = ap_store.list_prospects(limit=10)[0]

    permissive = policy_mod.Policy(
        {"enabled": True, "channels": ["whatsapp"], "whatsapp_enabled": True, "kill_switches": {}}
    )
    out = elig.evaluate(dict(rec), channel="whatsapp", step="initial", pol=permissive)
    assert "consent_missing" not in out.get("reason_codes", []), out


def test_no_phone_is_a_clean_no_op():
    """Web-test calls have no dialed number yet — must not write anything."""
    b = _brain(phone="")
    b._on_close_signal()
    assert ap_store.list_prospects(limit=10) == []


def test_repeat_close_signal_is_idempotent():
    b = _brain()
    b._on_close_signal()
    b._on_close_signal()
    rows = ap_store.list_prospects(limit=100)
    assert len(rows) == 1, "same caller must not create a second prospect"


def test_enrolment_is_skipped_when_consent_cannot_be_recorded(monkeypatch):
    """SAFETY: never hand the autopilot a number whose consent we failed to persist."""

    def _boom(*a, **k):
        raise RuntimeError("ledger down")

    monkeypatch.setattr(consent_ledger, "record_consent", _boom)
    b = _brain()
    b._on_close_signal()  # must not raise
    assert ap_store.list_prospects(limit=10) == [], "no consent write => no enrolment"


def test_close_signal_never_raises_even_if_autopilot_store_fails(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("store down")

    monkeypatch.setattr(ap_store, "upsert_prospect", _boom)
    b = _brain()
    b._on_close_signal()  # must not raise — the call must never break
    assert b.close_signal_fired is True
