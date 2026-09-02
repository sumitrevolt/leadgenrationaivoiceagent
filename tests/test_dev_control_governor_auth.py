from __future__ import annotations

from app.dev_control.governor_auth import (
    ATTESTATION_VERSION,
    build_configured_governor_headers,
    build_governor_signature,
    governor_auth_status,
    verify_governor_attestation,
)


TASK_ID = "task-auth-1"
ARTIFACT_HASH = "a" * 64
CLAUDE_SECRET = "c" * 40
CHATGPT_SECRET = "g" * 40
NOW = 1_750_000_000
NONCE = "nonce_for_review_123456"


def _signature(*, secret=CLAUDE_SECRET, governor="claude", summary="safe") -> str:
    return build_governor_signature(
        secret=secret,
        task_id=TASK_ID,
        governor=governor,
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary=summary,
        issued_at=NOW,
        nonce=NONCE,
    )


def test_valid_scoped_hmac_attestation(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    result = verify_governor_attestation(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_signature(),
        now=NOW,
    )
    assert result == {"ok": True, "reason": "verified", "version": ATTESTATION_VERSION}


def test_missing_or_short_secret_fails_closed(monkeypatch):
    monkeypatch.delenv("DEV_CLAUDE_REVIEW_SECRET", raising=False)
    missing = verify_governor_attestation(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_signature(),
        now=NOW,
    )
    assert missing["ok"] is False and missing["reason"] == "secret_unconfigured"
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", "too-short")
    short = verify_governor_attestation(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_signature(),
        now=NOW,
    )
    assert short["ok"] is False and short["reason"] == "secret_unconfigured"


def test_governor_secrets_are_not_interchangeable(monkeypatch):
    monkeypatch.setenv("DEV_CHATGPT_REVIEW_SECRET", CHATGPT_SECRET)
    result = verify_governor_attestation(
        task_id=TASK_ID,
        governor="chatgpt",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_signature(secret=CLAUDE_SECRET, governor="chatgpt"),
        now=NOW,
    )
    assert result["ok"] is False and result["reason"] == "signature_invalid"


def test_stale_future_and_malformed_attestations_fail(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    common = dict(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        nonce=NONCE,
        signature=_signature(),
        now=NOW,
    )
    assert (
        verify_governor_attestation(issued_at=str(NOW - 301), **common)["reason"]
        == "timestamp_outside_window"
    )
    assert (
        verify_governor_attestation(issued_at=str(NOW + 31), **common)["reason"]
        == "timestamp_outside_window"
    )
    assert (
        verify_governor_attestation(issued_at="not-a-time", **common)["reason"]
        == "attestation_malformed"
    )
    assert (
        verify_governor_attestation(issued_at=str(NOW), **{**common, "nonce": "short"})["reason"]
        == "attestation_malformed"
    )


def test_signed_body_tampering_is_rejected(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    result = verify_governor_attestation(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="changed after signing",
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_signature(summary="safe"),
        now=NOW,
    )
    assert result["ok"] is False and result["reason"] == "signature_invalid"


def test_status_exposes_only_configuration_boolean(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    monkeypatch.setenv("DEV_CHATGPT_REVIEW_SECRET", "short")
    assert governor_auth_status() == {
        "attestation_version": ATTESTATION_VERSION,
        "claude_configured": True,
        "chatgpt_configured": False,
        "required_secret_min_chars": 32,
    }


def test_configured_header_builder_never_returns_secret(monkeypatch):
    monkeypatch.setenv("DEV_CLAUDE_REVIEW_SECRET", CLAUDE_SECRET)
    headers = build_configured_governor_headers(
        task_id=TASK_ID,
        governor="claude",
        decision="approve",
        artifact_hash=ARTIFACT_HASH,
        summary="safe",
        issued_at=NOW,
        nonce=NONCE,
    )
    assert set(headers) == {
        "X-Governor-Timestamp",
        "X-Governor-Nonce",
        "X-Governor-Signature",
    }
    assert CLAUDE_SECRET not in repr(headers)
    assert (
        verify_governor_attestation(
            task_id=TASK_ID,
            governor="claude",
            decision="approve",
            artifact_hash=ARTIFACT_HASH,
            summary="safe",
            issued_at=headers["X-Governor-Timestamp"],
            nonce=headers["X-Governor-Nonce"],
            signature=headers["X-Governor-Signature"],
            now=NOW,
        )["ok"]
        is True
    )
