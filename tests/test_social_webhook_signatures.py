"""Loop-social-12 (2026-07-11): webhook signature verifiers.

Contract:
- verify_meta_signature returns True on a valid HMAC-SHA256 header, False
  otherwise (missing header, wrong prefix, tampered payload, wrong secret,
  short header, non-hex chars).
- Uses constant-time compare (no timing leaks — implicit via hmac.compare_digest).
- dispatch_status_update flips the store row + emits ledger event only after
  verification passed (test wiring).
"""

from __future__ import annotations

import hashlib
import hmac

import pytest

from app.social_engine import webhooks as wh


def _sign(secret: str, payload: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def test_valid_meta_signature_accepted():
    secret = "app_secret_12345"  # nosecret (test-only fake for HMAC math)
    payload = b'{"object":"page","entry":[]}'
    header = _sign(secret, payload)
    assert wh.verify_meta_signature(payload, header, secret) is True


def test_tampered_payload_rejected():
    secret = "app_secret_12345"  # nosecret (test-only fake for HMAC math)
    payload = b'{"object":"page","entry":[]}'
    header = _sign(secret, payload)
    tampered = b'{"object":"page","entry":[{"evil":1}]}'
    assert wh.verify_meta_signature(tampered, header, secret) is False


def test_wrong_secret_rejected():
    secret = "app_secret_12345"  # nosecret (test-only fake for HMAC math)
    payload = b"{}"
    header = _sign(secret, payload)
    assert wh.verify_meta_signature(payload, header, "different_secret") is False


def test_missing_header_rejected():
    assert wh.verify_meta_signature(b"{}", "", "secret") is False


def test_malformed_prefix_rejected():
    payload = b"{}"
    header = "md5=" + hmac.new(b"secret", payload, hashlib.md5).hexdigest()
    assert wh.verify_meta_signature(payload, header, "secret") is False


def test_non_hex_header_rejected():
    assert wh.verify_meta_signature(b"{}", "sha256=nothexatall", "secret") is False


def test_empty_secret_fails_closed():
    payload = b"{}"
    header = _sign("secret", payload)
    assert wh.verify_meta_signature(payload, header, "") is False


def test_linkedin_uses_same_math():
    secret = "li_secret_xyz"  # nosecret (test-only fake for HMAC math)
    payload = b"linkedin-event"
    header = _sign(secret, payload)
    assert wh.verify_linkedin_signature(payload, header, secret) is True


def test_bare_hex_header_also_accepted():
    """Some providers omit the 'sha256=' prefix. Verifier accepts bare hex."""
    secret = "secret"
    payload = b"{}"
    hex_only = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    assert wh.verify_generic_hmac_sha256(payload, hex_only, secret) is True


def test_dispatch_status_update_no_match_is_ok(monkeypatch, tmp_path):
    """Ledger emit + no store crash when the post_id doesn't match a queued job."""
    from app.social_engine import store as _store
    from app.marketing import delivery_ledger

    monkeypatch.setattr(_store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(_store, "_mirror", lambda job: None)

    captured: list[tuple] = []
    monkeypatch.setattr(
        delivery_ledger, "log_event", lambda cid, ev, detail="", **kw: captured.append((cid, ev))
    )
    out = wh.dispatch_status_update("PID-orphan", "published", detail="ok", client_id="c1")
    assert out["ok"] is True
    assert out["matched_job"] is False
    assert ("c1", "post_published") in captured
