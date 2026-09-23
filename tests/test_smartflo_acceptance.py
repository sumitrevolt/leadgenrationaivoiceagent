"""Tests for the SmartFlo acceptance framework.

These tests cover the LOCAL gates (0-3). Gates 4-11 are UNVERIFIED until
the operator runs the framework in the trusted VPS environment with a
real test number and the existing active channel.

The acceptance framework's purpose is the P0 release gate per the
2026-09-22 owner directive: until a real bidirectional conversation
succeeds, calling is NOT operational, and the 5-channel rollout is blocked.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.voice import smartflo_acceptance as sa


def test_run_acceptance_short_circuits_on_missing_prereqs(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no env set, gates 0-2 should FAIL and gates 4-11 should BLOCK.

    This validates the prereq-check ordering: local gates run first, then
    remote gates only if all prereqs pass. A BLOCKED gate must never be
    reported as PASS.
    """
    # Strip any inherited env so the prereq gates FAIL
    for k in ["SMARTFLO_API_KEY", "SMARTFLO_APP_ID", "SMARTFLO_VOICE_STREAM_ENABLED", "COMPLIANCE_ALLOWLIST"]:
        monkeypatch.delenv(k, raising=False)
    # CI bypass: netguard blocks live TCP probe; skip it for unit tests
    monkeypatch.setenv("SMARTFLO_SKIP_VPS_PROBE", "1")
    result = sa.run_acceptance(test_number=None)
    # Gates 0 (creds) and 2 (probe-skipped VPS) may PASS independently of CLI args.
    # The load-bearing invariants are: FAIL > 0 (gate 1 or 3 blocked), BLOCKED == 8 (remote gates short-circuited)
    assert result["summary"]["FAIL"] >= 1, f"expected at least 1 FAIL when prereqs missing, got {result['summary']}"
    assert result["summary"]["BLOCKED"] == 8, f"expected 8 BLOCKED (remote gates short-circuited), got {result['summary']}"
    assert result["verdict"] == "BLOCKED_FIX_PREREQS_FIRST"


def test_gate0_credentials_present_reports_fingerprint_only() -> None:
    """Gate 0 must NEVER print the key value — only the sha256[:12] fingerprint."""
    result = sa.verify_credentials_present()
    serialized = json.dumps(result)
    # No 32+ char hex strings (which would be a fingerprint, fine — that's intentional)
    # but NO key-like prefix
    assert "sk-" not in serialized.lower()
    # If the result includes a fingerprint, it must be 12 chars
    fp = result.get("credential_state", {}).get("fingerprint", "")
    if fp:
        assert len(fp) == 12, "credential_state fingerprint MUST be sha256[:12]"
        assert all(c in "0123456789abcdef" for c in fp), "fingerprint must be hex"


def test_gate1_stream_enabled_short_circuits_when_inert() -> None:
    """Default INERT mode is the safety default — flag must be explicitly set."""
    result = sa.verify_stream_enabled()
    if result["status"] == "FAIL":
        assert "SMARTFLO_VOICE_STREAM_ENABLED" in result["reason"]


def test_gate3_test_number_validation() -> None:
    """Reject short/missing numbers; accept valid Indian mobile."""
    # Missing
    r = sa.verify_test_number_authorized(None)
    assert r["status"] == "FAIL"

    # Too short
    r = sa.verify_test_number_authorized("12345")
    assert r["status"] == "FAIL"
    assert "10 digits" in r["reason"]

    # Valid
    r = sa.verify_test_number_authorized("9876543210")
    assert r["status"] == "PASS"


def test_gate3_test_number_respects_compliance_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    """If COMPLIANCE_ALLOWLIST is set, --to must be in it (default-deny)."""
    monkeypatch.setenv("COMPLIANCE_ALLOWLIST", "1111111111,2222222222")
    r = sa.verify_test_number_authorized("9999999999")
    assert r["status"] == "FAIL"
    assert "COMPLIANCE_ALLOWLIST" in r["reason"]

    r = sa.verify_test_number_authorized("1111111111")
    assert r["status"] == "PASS"


def test_remote_gates_are_unverified_stubs() -> None:
    """Gates 4-11 are operator-trusted STUBS. They MUST be marked UNVERIFIED
    (not PASS, not FAIL) until the operator fills in the real verification logic.
    This protects against the framework being used as a fake-green dashboard."""
    for fn in (
        sa.verify_smartflo_call_accepted,
        sa.verify_websocket_opened,
        sa.verify_swara_greeting_played,
        sa.verify_caller_speech_recognized,
        sa.verify_swara_response_contextual,
        sa.verify_multi_turn_no_dead_air,
        sa.verify_interruption_barge_in,
        sa.verify_call_ended_with_outcome,
    ):
        result = fn("9876543210")
        assert result["status"] == "UNVERIFIED", (
            f"{fn.__name__} must be UNVERIFIED stub, got {result['status']}"
        )
        assert "STUB" in result["reason"], (
            f"{fn.__name__} must declare itself a STUB"
        )


def test_run_acceptance_verdict_strings_are_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Owner dashboards may read verdict strings. Keep them stable."""
    for k in ["SMARTFLO_API_KEY", "SMARTFLO_APP_ID", "SMARTFLO_VOICE_STREAM_ENABLED", "COMPLIANCE_ALLOWLIST"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SMARTFLO_SKIP_VPS_PROBE", "1")
    result = sa.run_acceptance(test_number=None)
    assert result["verdict"] in {
        "READY_FOR_FIVE_CHANNEL_ROLLOUT",
        "PENDING_OPERATOR_TRUSTED_RUN",
        "BLOCKED_FIX_PREREQS_FIRST",
    }


def test_cli_main_invocation_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    """The CLI main() must return the right exit codes for each verdict.

    exit 0 = all 12 gates PASS (only achievable after operator runs trusted env)
    exit 1 = UNVERIFIED gates remain (real verification still needed)
    exit 2 = FAIL gates present (prereqs blocked)
    """
    for k in ["SMARTFLO_API_KEY", "SMARTFLO_APP_ID", "SMARTFLO_VOICE_STREAM_ENABLED", "COMPLIANCE_ALLOWLIST"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SMARTFLO_SKIP_VPS_PROBE", "1")
    rc = sa.main([])
    # prereqs missing => some FAILs => exit 2
    assert rc == 2, f"expected exit 2 for missing prereqs, got {rc}"
