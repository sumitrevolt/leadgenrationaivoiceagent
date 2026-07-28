"""Consent + Opt-out Ledger (TCCCPR/DPDP) tests — module + compliance-gate wiring."""

import os
import time

import pytest

from app.marketing import wa_campaign_runner
from app.telephony import consent_ledger as cl


@pytest.fixture(autouse=True)
def _tmp_stores(tmp_path, monkeypatch):
    """Har test apne tmp jsonl stores pe chale (real data/ untouched).

    The resolver FUNCTIONS are patched, not module constants. The constants are
    gone precisely because a path frozen at import cannot be redirected by a
    fixture that runs later — patching a leftover constant here would leave the
    production code writing into the repository's own `data/` during CI.
    """
    monkeypatch.setattr(cl, "ledger_path", lambda: tmp_path / "consent_ledger.jsonl")
    monkeypatch.setattr(cl, "suppression_path", lambda: tmp_path / "voice_suppression.jsonl")
    # `record_opt_out` cross-channel-propagates into wa_campaign_runner.suppress()
    # (TCCCPR: a revocation applies to every commercial channel). Without this
    # third patch that write lands in the working copy's data/wa_suppression.jsonl
    # — which is not hypothetical: four of this file's test numbers are sitting in
    # that file right now. It is gitignored, so the damage never reached a commit,
    # but "gitignored" is not "isolated": on the VPS that same path IS the
    # authoritative suppression list. Isolating two of three stores is not
    # isolation.
    monkeypatch.setattr(
        wa_campaign_runner, "_suppression_path", lambda: str(tmp_path / "wa_suppression.jsonl")
    )
    monkeypatch.setattr(cl, "recordings_dir", lambda: tmp_path / "recordings")
    yield


def test_opt_out_suppresses_and_is_idempotent():
    assert cl.is_suppressed("+91 98765 43210") is False
    r1 = cl.record_opt_out("+91 98765 43210", reason="test", channel="voice", call_id="c1")
    assert r1["suppressed"] is True
    # +91 prefix variations same number resolve hote hain (last-10 match)
    assert cl.is_suppressed("9876543210") is True
    assert cl.is_suppressed("919876543210") is True
    # idempotent — duplicate suppression entry nahi
    cl.record_opt_out("9876543210")
    assert len([i for i in cl.suppression_list() if i["phone"] == "9876543210"]) == 1


def test_consent_record_and_history():
    cl.record_consent("9876500001", scope="voice_promo", source="inquiry_form", proof="inq-42")
    assert cl.has_consent("9876500001") is True
    assert cl.has_consent("9876500001", scope="other_scope") is False
    hist = cl.ledger_for("9876500001")
    assert hist and hist[0]["type"] == "consent" and hist[0]["source"] == "inquiry_form"


def test_opt_out_revokes_consent_and_opt_in_restores():
    cl.record_consent("9876500002", source="signup")
    assert cl.has_consent("9876500002") is True
    cl.record_opt_out("9876500002")
    assert cl.has_consent("9876500002") is False  # suppression > consent
    # 90-day re-consent cool-off now blocks an immediate opt-back-in (TRAI floor);
    # admin force-override exercises the restore path.
    res = cl.opt_back_in("9876500002", source="admin", proof="ticket-1", force=True)
    assert res["suppressed"] is False
    assert cl.is_suppressed("9876500002") is False
    assert cl.has_consent("9876500002") is True


def test_consent_max_age_expiry():
    cl.record_consent("9876500003", source="web")
    assert cl.has_consent("9876500003", max_age_days=7) is True
    # 0-day validity → har consent expired
    assert cl.has_consent("9876500003", max_age_days=0) is False


def test_bad_phone_never_raises():
    assert cl.record_opt_out("")["error"] == "bad_phone"
    assert cl.is_suppressed("") is False
    assert cl.has_consent("abc") is False
    assert cl.ledger_for("") == []


def test_retention_sweep_dry_run_then_gated_delete(monkeypatch):
    d = cl.recordings_dir()
    d.mkdir(parents=True, exist_ok=True)
    old_f = d / "old_call.wav"
    new_f = d / "new_call.wav"
    old_f.write_bytes(b"x")
    new_f.write_bytes(b"x")
    past = time.time() - 100 * 86400
    os.utime(old_f, (past, past))

    # Flag OFF (default) = dry-run: report only, koi delete nahi
    monkeypatch.delenv("RECORDING_RETENTION", raising=False)
    rep = cl.retention_sweep(days=90)
    assert rep["expired"] == 1 and rep["deleted"] == 0
    assert old_f.exists()

    # Flag ON = sirf expired delete hoti hai
    monkeypatch.setenv("RECORDING_RETENTION", "1")
    rep2 = cl.retention_sweep(days=90)
    assert rep2["deleted"] == 1
    assert not old_f.exists() and new_f.exists()


def test_retention_sweep_missing_dir_noop():
    rep = cl.retention_sweep(days=90)
    assert rep["expired"] == 0 and rep.get("error") is None


@pytest.mark.asyncio
async def test_compliance_gate_blocks_suppressed_promotional(monkeypatch):
    """ComplianceGate wiring: opt-out number par promotional = BLOCK ('opted_out')."""
    from app.telephony.compliance import CallType, ComplianceGate

    monkeypatch.delenv("COMPLIANCE_ALLOWLIST", raising=False)
    cl.record_opt_out("9876511111")
    gate = ComplianceGate(dnd_checker=None)
    dec = await gate.check("+919876511111", CallType.PROMOTIONAL)
    assert dec.allowed is False
    assert "opted_out" in dec.reasons
    assert dec.checks.get("suppressed") is True


@pytest.mark.asyncio
async def test_compliance_gate_transactional_not_blocked_by_suppression(monkeypatch):
    """Transactional (user-requested callback) suppression se block nahi hota."""
    from datetime import datetime

    from app.telephony.compliance import IST, CallType, ComplianceGate

    monkeypatch.delenv("COMPLIANCE_ALLOWLIST", raising=False)
    cl.record_opt_out("9876522222")
    gate = ComplianceGate(dnd_checker=None)
    noon = datetime.now(IST).replace(hour=12, minute=0)
    dec = await gate.check("+919876522222", CallType.TRANSACTIONAL, now=noon)
    assert dec.allowed is True
    assert dec.checks.get("suppressed") is True  # note hota hai, block nahi
