"""customer_totp — enrol, verify, recovery codes, challenge, disable.

Two-factor is security-critical: tests assert correctness AND non-bypass.
- Recovery codes MUST be single-use.
- Challenges MUST expire.
- Wrong codes MUST NOT succeed.
- Disabled state MUST actually remove the row (login gate re-opens).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.platform import customer_totp as ct
from app.utils.totp import totp_now


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ct, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(ct, "_PATH", tmp_path / "customer_totp.jsonl")
    monkeypatch.setenv("TOTP_CHALLENGE_KEY", "test-challenge-key-fixed")


# --------------------------------------------------------------------------- #
# Enrol → confirm
# --------------------------------------------------------------------------- #
def test_begin_enroll_shape() -> None:
    out = ct.begin_enroll("client_a", "user@example.com")
    assert out["ok"] is True
    assert out["secret"]
    assert out["otpauth_uri"].startswith("otpauth://totp/")
    assert "secret=" in out["otpauth_uri"]
    assert len(out["recovery_codes"]) == 8
    # No state persisted yet
    assert ct.is_enabled("client_a") is False


def test_confirm_enroll_requires_correct_code() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    out = ct.confirm_enroll("client_a", enrol["secret"], "000000", enrol["recovery_codes"])
    assert out["ok"] is False
    # And not enabled
    assert ct.is_enabled("client_a") is False


def test_confirm_enroll_persists_row() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    code = totp_now(enrol["secret"])
    out = ct.confirm_enroll("client_a", enrol["secret"], code, enrol["recovery_codes"])
    assert out["ok"] is True
    assert ct.is_enabled("client_a") is True


def test_enroll_blocked_if_already_enabled() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    out = ct.begin_enroll("client_a", "x")
    assert out["ok"] is False
    assert "already" in out["error"]


# --------------------------------------------------------------------------- #
# Verify
# --------------------------------------------------------------------------- #
def test_verify_accepts_current_totp() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    assert ct.verify("client_a", totp_now(enrol["secret"])) is True


def test_verify_rejects_wrong_totp() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    assert ct.verify("client_a", "000000") is False


def test_recovery_code_works_once_then_consumed() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    rc = enrol["recovery_codes"][0]
    # First use succeeds
    assert ct.verify("client_a", rc) is True
    # Second use of the SAME code MUST fail (single-use is critical)
    assert ct.verify("client_a", rc) is False
    # Other recovery codes still work
    assert ct.verify("client_a", enrol["recovery_codes"][1]) is True


def test_verify_returns_false_for_unenrolled_client() -> None:
    assert ct.verify("nobody", "123456") is False


# --------------------------------------------------------------------------- #
# Disable
# --------------------------------------------------------------------------- #
def test_disable_with_totp_code() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    out = ct.disable("client_a", totp_now(enrol["secret"]))
    assert out["ok"] is True
    assert ct.is_enabled("client_a") is False


def test_disable_with_recovery_code() -> None:
    """Customer who lost authenticator MUST be able to recover."""
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    out = ct.disable("client_a", enrol["recovery_codes"][3])
    assert out["ok"] is True


def test_disable_rejects_wrong_code() -> None:
    enrol = ct.begin_enroll("client_a", "x")
    ct.confirm_enroll(
        "client_a", enrol["secret"], totp_now(enrol["secret"]), enrol["recovery_codes"]
    )
    out = ct.disable("client_a", "000000")
    assert out["ok"] is False
    assert ct.is_enabled("client_a") is True


# --------------------------------------------------------------------------- #
# Login challenge
# --------------------------------------------------------------------------- #
def test_challenge_roundtrip() -> None:
    tok = ct.create_challenge("client_a")
    assert ct.consume_challenge(tok) == "client_a"


def test_challenge_tampered_signature_rejected() -> None:
    tok = ct.create_challenge("client_a")
    # Flip the last byte of the signature
    body, sig = tok.split(".", 1)
    bad = body + "." + sig[:-1] + ("0" if sig[-1] != "0" else "1")
    assert ct.consume_challenge(bad) is None


def test_challenge_expired_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A challenge older than TTL must not verify (replay-window bound).

    Sleep 2.5s vs TTL=1s — int() truncation in create_challenge means a 1.2s
    sleep is borderline (works most runs, fails when t0 is just past an
    integer boundary). 2.5s gives a clean margin without slowing the suite."""
    monkeypatch.setattr(ct, "_CHALLENGE_TTL_S", 1)
    tok = ct.create_challenge("client_a")
    time.sleep(2.5)
    assert ct.consume_challenge(tok) is None
