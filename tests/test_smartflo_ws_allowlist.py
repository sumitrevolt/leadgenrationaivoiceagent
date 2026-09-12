"""Contract tests — Smartflo voice-stream IP allowlist (2026-09-11).

The stream endpoint is unauthenticated in production (``SMARTFLO_WS_SECRET`` and
``SMARTFLO_WS_REQUIRE_SECRET`` are unset) and a single ``start`` frame drives real
EdgeTTS/LLM spend plus a metered record. ``SMARTFLO_WS_ALLOW_IPS`` is the INERT
(default-off) mitigation, wired here.

The security-critical properties locked by these tests:
  * default/unset behaviour is unchanged (route only consults this when armed)
  * fail-CLOSED on a malformed spec, a malformed peer address, or no peer at all
  * a client-forged ``X-Forwarded-For`` CANNOT grant access — only the last hop
    (the one Caddy appends) is trusted
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.telephony_smartflo import _client_ip_allowed


class _FakeWS:
    """Minimal stand-in for the Starlette WebSocket surface we read."""

    def __init__(self, peer: str | None = None, xff: str | None = None) -> None:
        self.client = SimpleNamespace(host=peer) if peer is not None else None
        self.headers: dict[str, str] = {}
        if xff is not None:
            self.headers["x-forwarded-for"] = xff


def test_peer_inside_cidr_is_allowed():
    assert _client_ip_allowed(_FakeWS(peer="203.0.113.10"), "203.0.113.0/24") is True


def test_peer_outside_cidr_is_rejected():
    assert _client_ip_allowed(_FakeWS(peer="198.51.100.5"), "203.0.113.0/24") is False


def test_exact_ip_match_is_allowed():
    assert _client_ip_allowed(_FakeWS(peer="203.0.113.10"), "203.0.113.10") is True


def test_multiple_entries_are_honoured():
    spec = "203.0.113.0/24, 198.51.100.7"
    assert _client_ip_allowed(_FakeWS(peer="198.51.100.7"), spec) is True


def test_last_forwarded_hop_is_trusted():
    """Behind Caddy the real client is the hop Caddy appended."""
    ws = _FakeWS(peer="127.0.0.1", xff="203.0.113.10")
    assert _client_ip_allowed(ws, "203.0.113.0/24") is True


def test_client_forged_forwarded_header_cannot_grant_access():
    """SECURITY: only the LAST hop counts, so a spoofed left-most entry fails."""
    ws = _FakeWS(peer="127.0.0.1", xff="203.0.113.10, 198.51.100.5")
    assert _client_ip_allowed(ws, "203.0.113.0/24") is False


def test_malformed_allowlist_entry_fails_closed():
    assert _client_ip_allowed(_FakeWS(peer="203.0.113.10"), "not-an-ip") is False


def test_unparseable_peer_fails_closed():
    assert _client_ip_allowed(_FakeWS(peer="garbage"), "203.0.113.0/24") is False


def test_missing_peer_fails_closed():
    assert _client_ip_allowed(_FakeWS(), "203.0.113.0/24") is False


def test_empty_spec_fails_closed():
    """The route only calls this when armed, but an empty spec must never open up."""
    assert _client_ip_allowed(_FakeWS(peer="203.0.113.10"), "") is False


def test_ipv6_is_supported():
    assert _client_ip_allowed(_FakeWS(peer="2001:db8::1"), "2001:db8::/32") is True


def test_helper_never_raises_on_hostile_input():
    for spec in ("", " ", ",,,", "0.0.0.0/0" * 200, "::/0"):
        _client_ip_allowed(_FakeWS(peer="203.0.113.10", xff="evil"), spec)


@pytest.mark.parametrize("spec", ["203.0.113.0/24"])
def test_allowlist_is_inert_by_default_shape(spec):
    """Guard against a change that makes an unarmed route reject everyone."""
    import inspect

    from app.api import telephony_smartflo as mod

    source = inspect.getsource(mod.smartflo_stream_ws)
    assert 'SMARTFLO_WS_ALLOW_IPS' in source
    # The reject branch must sit behind a truthiness check on the env value.
    assert "if _allow_ips and not _client_ip_allowed" in source
