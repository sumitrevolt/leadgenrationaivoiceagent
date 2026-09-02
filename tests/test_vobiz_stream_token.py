"""Tests: HMAC-signed Vobiz media-stream token (app/telephony/stream_token.py).

Security sweep 2026-07-06 [M]: the `/api/telephony/vobiz/stream/{token}` media
WS runs a full free-AI conversation loop for any token. `sign()`/`verify()` let
OUR outbound tokens carry a stable HMAC signature so the WS can (when explicitly
gated) reject anonymous callers WITHOUT breaking the load-bearing unknown-token
fallback. Default = INERT: no secret => sign() returns raw, verify() returns True
=> zero behavior change. These are pure helper tests (no WS integration).
"""

import time

from app.telephony import stream_token

_SECRET = "unit-test-secret"  # nosecret — obviously-fake test-only literal


class TestInert:
    """No VOBIZ_STREAM_SECRET => signing/verification is a no-op."""

    def test_sign_returns_raw_unchanged_when_secret_unset(self, monkeypatch):
        monkeypatch.delenv("VOBIZ_STREAM_SECRET", raising=False)
        assert stream_token.sign("abc123") == "abc123"

    def test_verify_returns_true_for_anything_when_secret_unset(self, monkeypatch):
        monkeypatch.delenv("VOBIZ_STREAM_SECRET", raising=False)
        # Bare uuid, garbage, and empty all pass — current lenient behavior.
        assert stream_token.verify("abc123") is True
        assert stream_token.verify("not-a-real-token") is True
        assert stream_token.verify("") is True

    def test_empty_secret_is_also_inert(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", "   ")  # blank => treated unset
        assert stream_token.sign("abc123") == "abc123"
        assert stream_token.verify("abc123") is True


class TestSignVerifyRoundTrip:
    """With a secret set, a freshly signed token verifies."""

    def test_valid_signed_token_passes(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        tok = stream_token.sign("abc123")
        assert tok != "abc123"  # signing actually happened
        assert tok.startswith("abc123.")
        assert tok.count(".") == 2
        assert stream_token.verify(tok) is True

    def test_signed_token_is_stable_across_calls(self, monkeypatch):
        # Same raw + same exp => same signature (survives a WS reconnect).
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        exp = int(time.time()) + 600
        tok1 = stream_token.sign("abc123", exp=exp)
        tok2 = stream_token.sign("abc123", exp=exp)
        assert tok1 == tok2
        assert stream_token.verify(tok1) is True


class TestRejects:
    """With a secret set, bad tokens fail closed."""

    def test_tampered_signature_fails(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        tok = stream_token.sign("abc123")
        raw, exp, sig = tok.rsplit(".", 2)
        tampered = f"{raw}.{exp}.{'0' * len(sig)}"
        assert stream_token.verify(tampered) is False

    def test_tampered_raw_fails(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        tok = stream_token.sign("abc123")
        _raw, exp, sig = tok.rsplit(".", 2)
        assert stream_token.verify(f"evilraw.{exp}.{sig}") is False

    def test_expired_token_fails(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        past = int(time.time()) - 10  # already expired
        tok = stream_token.sign("abc123", exp=past)
        assert stream_token.verify(tok) is False

    def test_unsigned_bare_token_fails_when_secret_set(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        # A bare uuid (no .exp.sig suffix) is rejected once enforcement is armed.
        assert stream_token.verify("abc123") is False

    def test_wrong_secret_fails(self, monkeypatch):
        # Token signed under one secret must not verify under another.
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        tok = stream_token.sign("abc123")
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", "a-different-secret")
        assert stream_token.verify(tok) is False

    def test_malformed_exp_fails(self, monkeypatch):
        monkeypatch.setenv("VOBIZ_STREAM_SECRET", _SECRET)
        assert stream_token.verify("abc123.notanumber.deadbeefdeadbeef") is False
