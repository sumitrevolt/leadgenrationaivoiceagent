"""The suppression authority may fail to RESOLVE — and that must not read as consent.

Before the runtime-data migration these paths were module constants, so
"resolve the path" could not fail; the only errors were I/O on a file that
legitimately might not exist. `resolve_store_path` adds real resolution failures:
a runtime root that is not absolute, does not exist, is not writable, a segment
that escapes the root, or (after cutover) an override pointing somewhere other
than the canonical target.

The pre-existing `except Exception: return False` around those reads was written
when the only failures were "file missing" — a legitimate not-suppressed answer.
Carried over unchanged it would answer "this person did not opt out" whenever the
opt-out list is unreachable, which is the TCCCPR fail-OPEN this module's own
comments call illegal.

So the contract asserted here is:

    cannot READ the list          -> not suppressed   (a missing file is an answer)
    cannot RESOLVE the authority  -> suppressed       (an outage is not an answer)

and the write side must never claim a suppression it could not persist.
"""

from __future__ import annotations

import pytest

from app.marketing import wa_campaign_runner as runner
from app.platform import runtime_data as rd
from app.telephony import consent_ledger as cl

PHONE = "+91 90000 11122"


def _explode(*_a, **_k):
    raise rd.RuntimeDataError("runtime root is configured but unusable")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(cl, "ledger_path", lambda: tmp_path / "consent_ledger.jsonl")
    monkeypatch.setattr(cl, "suppression_path", lambda: tmp_path / "voice_suppression.jsonl")
    monkeypatch.setattr(runner, "_suppression_path", lambda: str(tmp_path / "wa_suppression.jsonl"))
    # The DB path is a separate authority; these tests are about the file one.
    monkeypatch.setattr(cl, "_db_is_suppressed", lambda _k: False)
    monkeypatch.setattr(cl, "_db_add_suppression", lambda *_a, **_k: False)
    monkeypatch.setattr(cl, "_db_remove_suppression", lambda _k: False)
    yield


# ------------------------------------------------------------------ voice
def test_voice_missing_file_reads_as_not_suppressed():
    """The baseline the fail-closed case must be distinguished from."""
    assert cl.is_suppressed(PHONE) is False


def test_voice_unresolvable_authority_reads_as_SUPPRESSED(monkeypatch, caplog):
    monkeypatch.setattr(cl, "suppression_path", _explode)
    with caplog.at_level("ERROR"):
        assert cl.is_suppressed(PHONE) is True
    assert any(
        "UNRESOLVABLE" in r.message or "UNRESOLVABLE" in r.getMessage() for r in caplog.records
    )


def test_voice_opt_out_does_not_claim_a_suppression_it_could_not_store(monkeypatch):
    """`suppressed: True` is a promise. Without a store there is nothing to promise."""
    monkeypatch.setattr(cl, "suppression_path", _explode)
    out = cl.record_opt_out(PHONE, reason="test", channel="voice")
    assert out["suppressed"] is False


def test_voice_opt_back_in_refuses_when_the_authority_is_unresolvable(monkeypatch):
    """Re-consent is the one direction that makes a number contactable again."""
    monkeypatch.setattr(cl, "suppression_path", _explode)
    out = cl.opt_back_in(PHONE, source="admin", force=True)
    assert out["suppressed"] is True
    assert out["error"] == "suppression_authority_unavailable"


def test_voice_opt_out_still_works_normally():
    """Anti-vacuity: the fail-closed paths must not be the only paths that work."""
    out = cl.record_opt_out(PHONE, reason="test", channel="voice")
    assert out["suppressed"] is True
    assert cl.is_suppressed(PHONE) is True


# --------------------------------------------------------------- whatsapp
def test_whatsapp_missing_file_reads_as_not_suppressed():
    assert runner.is_suppressed("9000011122") is False


def test_whatsapp_unresolvable_authority_reads_as_SUPPRESSED(monkeypatch):
    monkeypatch.setattr(runner, "_suppression_path", _explode)
    assert runner.is_suppressed("9000011122") is True


def test_whatsapp_suppress_reports_failure_instead_of_claiming_success(monkeypatch):
    monkeypatch.setattr(runner, "_suppression_path", _explode)
    out = runner.suppress("9000011122", "opt_out")
    assert out["suppressed"] is False
    assert out["error"] == "suppression_authority_unavailable"


def test_whatsapp_suppress_still_works_normally():
    assert runner.suppress("9000011122", "opt_out")["suppressed"] is True
    assert runner.is_suppressed("9000011122") is True
