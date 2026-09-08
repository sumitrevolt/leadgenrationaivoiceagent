"""Security contract: per-tool HMAC, skew, replay — never admin bearer as auth."""

from __future__ import annotations

import json

from app.platform import coordination_hub_auth as auth_mod
from app.platform.coordination_hub_auth import (
    ATTESTATION_VERSION,
    body_sha256,
    build_configured_tool_headers,
    build_tool_signature,
    tool_auth_status,
    verify_tool_attestation,
)


def _nonce_tmp(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_mod, "_HUB_ROOT", str(tmp_path))
    monkeypatch.setattr(auth_mod, "_NONCE_FILE", str(tmp_path / "nonce_fps.jsonl"))


CURSOR_SECRET = "c" * 40
BUZZ_SECRET = "b" * 40
NOW = 1_750_000_100
BODY = b'{"status":"online"}'
NONCE = "nonce_coord_hub_test_01"


def _sig(*, secret=CURSOR_SECRET, tool_id="cursor", event_type="heartbeat", body=BODY, nonce=NONCE):
    return build_tool_signature(
        secret=secret,
        tool_id=tool_id,
        event_type=event_type,
        body_sha256=body_sha256(body),
        issued_at=NOW,
        nonce=nonce,
    )


def test_valid_tool_hmac(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    _nonce_tmp(monkeypatch, tmp_path)
    result = verify_tool_attestation(
        tool_id="cursor",
        event_type="heartbeat",
        body=BODY,
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_sig(),
        now=NOW,
    )
    assert result["ok"] is True
    assert result["reason"] == "verified"
    assert result["version"] == ATTESTATION_VERSION


def test_missing_secret_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("COORD_HUB_TOOL_CURSOR_SECRET", raising=False)
    _nonce_tmp(monkeypatch, tmp_path)
    missing = verify_tool_attestation(
        tool_id="cursor",
        event_type="heartbeat",
        body=BODY,
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_sig(),
        now=NOW,
    )
    assert missing["ok"] is False and missing["reason"] == "secret_unconfigured"


def test_wrong_tool_secret_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_TOOL_CLAUDE_SECRET", "d" * 40)
    _nonce_tmp(monkeypatch, tmp_path)
    # Sign with cursor secret but verify as claude
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    result = verify_tool_attestation(
        tool_id="claude",
        event_type="heartbeat",
        body=BODY,
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_sig(secret=CURSOR_SECRET, tool_id="claude"),
        now=NOW,
    )
    assert result["ok"] is False and result["reason"] == "signature_invalid"


def test_timestamp_and_malformed_fail(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    _nonce_tmp(monkeypatch, tmp_path)
    common = {
        "tool_id": "cursor",
        "event_type": "heartbeat",
        "body": BODY,
        "nonce": NONCE,
        "signature": _sig(),
        "now": NOW,
    }
    assert (
        verify_tool_attestation(issued_at=str(NOW - 301), **common)["reason"]
        == "timestamp_outside_window"
    )
    assert (
        verify_tool_attestation(issued_at=str(NOW + 31), **common)["reason"]
        == "timestamp_outside_window"
    )
    assert verify_tool_attestation(issued_at="nope", **common)["reason"] == "attestation_malformed"


def test_nonce_replay_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    _nonce_tmp(monkeypatch, tmp_path)
    first = verify_tool_attestation(
        tool_id="cursor",
        event_type="heartbeat",
        body=BODY,
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_sig(),
        now=NOW,
    )
    assert first["ok"] is True
    second = verify_tool_attestation(
        tool_id="cursor",
        event_type="heartbeat",
        body=BODY,
        issued_at=str(NOW),
        nonce=NONCE,
        signature=_sig(),
        now=NOW,
    )
    assert second["ok"] is False and second["reason"] == "nonce_replay"


def test_buzz_uses_dedicated_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_BUZZ_SECRET", BUZZ_SECRET)
    _nonce_tmp(monkeypatch, tmp_path)
    body = b'{"event_type":"note","channel":"#admin"}'
    nonce = "buzz_nonce_abcdef12"
    sig = _sig(
        secret=BUZZ_SECRET,
        tool_id="buzz",
        event_type="buzz_event",
        body=body,
        nonce=nonce,
    )
    ok = verify_tool_attestation(
        tool_id="buzz",
        event_type="buzz_event",
        body=body,
        issued_at=str(NOW),
        nonce=nonce,
        signature=sig,
        now=NOW,
    )
    assert ok["ok"] is True, ok


def test_status_booleans_only(monkeypatch):
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    monkeypatch.delenv("COORD_HUB_BUZZ_SECRET", raising=False)
    st = tool_auth_status()
    assert st["tools_configured"]["cursor"] is True
    assert st["tools_configured"]["buzz"] is False
    assert CURSOR_SECRET not in json.dumps(st)


def test_header_builder_never_returns_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("COORD_HUB_TOOL_CURSOR_SECRET", CURSOR_SECRET)
    _nonce_tmp(monkeypatch, tmp_path)
    headers = build_configured_tool_headers(
        tool_id="cursor",
        event_type="heartbeat",
        body=BODY,
        issued_at=NOW,
        nonce=NONCE,
    )
    assert set(headers) >= {
        "X-CoordHub-Timestamp",
        "X-CoordHub-Nonce",
        "X-CoordHub-Signature",
    }
    assert CURSOR_SECRET not in repr(headers)


def test_frontend_known_tools_verify_with_own_secret(monkeypatch, tmp_path):
    """Frontend TOOLMETA (monkeycode/opencode/bolt) backend me bhi verify hone
    chahiye — warna un tools ke heartbeats tool_unknown se reject hote hain."""
    for tool_id, secret in (
        ("opencode", "o" * 40),
        ("bolt", "t" * 40),
        ("monkeycode", "m" * 40),
    ):
        monkeypatch.setenv(f"COORD_HUB_TOOL_{tool_id.upper()}_SECRET", secret)
        _nonce_tmp(monkeypatch, tmp_path)
        nonce = f"nonce_{tool_id}_abcdef12"
        sig = _sig(secret=secret, tool_id=tool_id, nonce=nonce)
        result = verify_tool_attestation(
            tool_id=tool_id,
            event_type="heartbeat",
            body=BODY,
            issued_at=str(NOW),
            nonce=nonce,
            signature=sig,
            now=NOW,
        )
        assert result["ok"] is True, f"{tool_id}: {result}"
        monkeypatch.delenv(f"COORD_HUB_TOOL_{tool_id.upper()}_SECRET", raising=False)


def test_frontend_known_tools_listed_in_status(monkeypatch):
    for tool_id in ("opencode", "bolt", "monkeycode"):
        monkeypatch.setenv(f"COORD_HUB_TOOL_{tool_id.upper()}_SECRET", "z" * 40)
    st = tool_auth_status()
    for tool_id in ("opencode", "bolt", "monkeycode"):
        assert tool_id in st["known_tools"], f"{tool_id} missing from known_tools"
        assert st["tools_configured"][tool_id] is True
    monkeypatch.delenv("COORD_HUB_TOOL_OPENCODE_SECRET", raising=False)
    monkeypatch.delenv("COORD_HUB_TOOL_BOLT_SECRET", raising=False)
    monkeypatch.delenv("COORD_HUB_TOOL_MONKEYCODE_SECRET", raising=False)
