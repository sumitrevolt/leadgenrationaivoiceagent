"""
Tests for Telegram Dual-Bot Coordination Architecture
======================================================
Verifies:
1. Token resolution & fail-closed behavior
2. Role separation (Jarvis Ingress vs Notify Egress)
3. Zero 409 conflict guarantee
4. Owner authentication & deduplication
5. Cross-bot coordination dispatch
6. Local <-> VPS <-> Hermes polling coordination (lease, owner gate, 409 standby)
7. Live token validity + egress fallback when a slot is 401-dead
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

import app.platform.telegram_coordinator as tc
from app.platform.telegram_coordinator import (
    dispatch_egress_alert,
    dispatch_jarvis_response,
    get_dual_bot_status,
    get_egress_token,
    get_polling_token,
    is_duplicate_update,
    is_owner_chat,
    is_owner_username,
    is_telegram_configured,
)


@pytest.fixture
def isolated_lease(monkeypatch, tmp_path):
    """Isolate the polling lease: file backend only, temp path, clean globals.

    Without this, a developer machine with a local Redis would get real keys
    written during tests and the suite would depend on Redis availability.
    """
    monkeypatch.setattr(tc, "_redis_client", lambda: None)
    monkeypatch.setattr(tc, "_LEASE_PATH", tmp_path / "telegram_poll_lease.json")
    monkeypatch.setattr(tc, "_dead_egress_tokens", set())
    monkeypatch.setattr(tc, "_external_conflict_until", 0.0)
    monkeypatch.setattr(tc, "_conflict_count", 0)
    monkeypatch.setattr(tc, "_last_standby_reason", None)
    monkeypatch.setenv("TELEGRAM_INSTANCE_ROLE", "local")
    monkeypatch.setenv("TELEGRAM_INGRESS_OWNER", "auto")
    return tc


def test_token_resolution_fail_closed(monkeypatch):
    monkeypatch.delenv("TELEGRAM_JARVIS_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_NOTIFY_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    assert get_polling_token() is None
    assert get_egress_token() is None
    assert is_telegram_configured() is False


def test_token_resolution_valid(monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    monkeypatch.setenv("TELEGRAM_NOTIFY_BOT_TOKEN", "0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321")

    assert get_polling_token() == "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345"
    assert get_egress_token() == "0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321"
    assert is_telegram_configured() is True


def test_owner_authentication(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", "1621120182, 999888777")
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "sumitrevolt, owner_test")

    assert is_owner_chat(1621120182) is True
    assert is_owner_chat("999888777") is True
    assert is_owner_chat(111222333) is False

    assert is_owner_username("sumitrevolt") is True
    assert is_owner_username("@sumitrevolt") is True
    assert is_owner_username("owner_test") is True
    assert is_owner_username("stranger") is False


def test_update_deduplication(isolated_lease):
    test_id = 9999901
    assert is_duplicate_update(test_id) is False
    assert is_duplicate_update(test_id) is True
    assert is_duplicate_update(None) is False


def test_dual_bot_roles_and_separation(monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    monkeypatch.setenv("TELEGRAM_NOTIFY_BOT_TOKEN", "0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321")

    status = get_dual_bot_status()
    assert status["configured"] is True
    assert status["jarvis"]["role"] == "ingress_interactive_commands"
    assert status["jarvis"]["polling_enabled"] is True

    assert status["notify"]["role"] == "egress_broadcast_alerts"
    assert status["notify"]["polling_enabled"] is False  # Zero 409 conflict guarantee


def test_dispatch_egress_alert(monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFY_BOT_TOKEN", "0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321")

    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        mock_api.return_value = {"ok": True, "result": {"message_id": 101}}

        res = dispatch_egress_alert("P0 Service Degradation", "Redis queue threshold exceeded", severity="CRITICAL")
        assert res.get("ok") is True

        mock_api.assert_called_once()
        args, kwargs = mock_api.call_args
        token, method, params = args
        assert token == "0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321"
        assert method == "sendMessage"
        assert "CRITICAL" in params["text"]
        assert "@Sumits_jarvis_bot" in params["text"]


def test_dispatch_jarvis_response(monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")

    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        mock_api.return_value = {"ok": True, "result": {"message_id": 102}}

        res = dispatch_jarvis_response(1621120182, "All 9 Hermes supervisory bots active.")
        assert res.get("ok") is True

        mock_api.assert_called_once()
        args, kwargs = mock_api.call_args
        token, method, params = args
        assert token == "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345"
        assert method == "sendMessage"
        assert "All 9 Hermes supervisory bots active." in params["text"]


# ---------------------------------------------------------------------------
# Polling coordination: one token, one poller (local <-> VPS <-> Hermes)
# ---------------------------------------------------------------------------


def test_lease_grants_only_one_owner(isolated_lease):
    first = isolated_lease.acquire_polling_lease("laptop:111")
    assert first["acquired"] is True
    assert first["backend"] == "file"

    second = isolated_lease.acquire_polling_lease("vps:222")
    assert second["acquired"] is False
    assert second["reason"] == "held_by_other"
    assert second["holder"] == "laptop:111"

    # The holder may renew its own lease (heartbeat) without losing it.
    renew = isolated_lease.acquire_polling_lease("laptop:111")
    assert renew["acquired"] is True


def test_stale_lease_is_taken_over(isolated_lease):
    isolated_lease._write_lease_file({"holder": "dead:999", "expires_at": time.time() - 5})

    takeover = isolated_lease.acquire_polling_lease("vps:222")
    assert takeover["acquired"] is True
    assert takeover["reason"] == "stale_takeover"
    assert isolated_lease.get_polling_lease("vps:222")["held_by_me"] is True


def test_release_only_by_holder(isolated_lease):
    isolated_lease.acquire_polling_lease("laptop:111")

    assert isolated_lease.release_polling_lease("vps:222") is False
    assert isolated_lease.get_polling_lease("vps:222")["holder"] == "laptop:111"

    assert isolated_lease.release_polling_lease("laptop:111") is True
    assert isolated_lease.get_polling_lease("laptop:111")["holder"] is None


def test_should_poll_strict_owner_gate(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_OWNER", "vps")

    decision = isolated_lease.should_poll("laptop:111", "local")
    assert decision["poll"] is False
    assert decision["reason"] == "ingress_owner_is_vps"
    # A non-owner must not even claim the lease.
    assert isolated_lease.get_polling_lease("laptop:111")["holder"] is None

    allowed = isolated_lease.should_poll("vps:222", "vps")
    assert allowed["poll"] is True


def test_should_poll_off_switch(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_INGRESS_OWNER", "off")
    decision = isolated_lease.should_poll("laptop:111", "local")
    assert decision["poll"] is False
    assert decision["reason"] == "ingress_owner_off"


def test_should_poll_lease_blocks_second_instance(isolated_lease):
    assert isolated_lease.should_poll("laptop:111", "local")["poll"] is True

    blocked = isolated_lease.should_poll("vps:222", "local")
    assert blocked["poll"] is False
    assert blocked["reason"] == "lease_held_by_other"
    assert blocked["holder"] == "laptop:111"


def test_should_poll_dry_run_never_takes_the_lease(isolated_lease):
    """A status read must report coordination state, not mutate it."""
    decision = isolated_lease.should_poll("laptop:1", "local", dry_run=True)
    assert decision["poll"] is True
    assert decision["reason"] == "lease_free"
    assert decision["dry_run"] is True
    assert isolated_lease._read_lease_file() == {}

    isolated_lease.acquire_polling_lease("vps:2")
    blocked = isolated_lease.should_poll("laptop:1", "local", dry_run=True)
    assert blocked["poll"] is False
    assert blocked["reason"] == "lease_held_by_other"
    assert isolated_lease.get_polling_lease("vps:2")["holder"] == "vps:2"


def test_should_poll_respects_external_conflict_cooldown(isolated_lease, monkeypatch):
    monkeypatch.setattr(isolated_lease, "_external_conflict_until", time.time() + 30)

    decision = isolated_lease.should_poll("laptop:111", "local")
    assert decision["poll"] is False
    assert decision["reason"] == "external_consumer_conflict"
    assert decision["retry_in_s"] > 0


# ---------------------------------------------------------------------------
# Live token validity + egress fallback
# ---------------------------------------------------------------------------


def test_validate_bot_token_live(isolated_lease, monkeypatch):
    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        mock_api.return_value = {"ok": True, "result": {"username": "Sumits_jarvis_bot", "id": 8363810880}}
        good = isolated_lease.validate_bot_token("1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345", force=True)
        assert good["valid"] is True
        assert good["username"] == "@Sumits_jarvis_bot"
        assert "1234567890" not in str(good)  # never echo the token

        mock_api.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}
        dead = isolated_lease.validate_bot_token("0987654321:ZYXwvuTSRqpoNMLkjihGFEdcba54321", force=True)
        assert dead["valid"] is False
        assert dead["reason"] == "unauthorized"


def test_token_health_reports_presence(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    monkeypatch.delenv("TELEGRAM_NOTIFY_BOT_TOKEN", raising=False)

    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        mock_api.return_value = {"ok": True, "result": {"username": "Sumits_jarvis_bot", "id": 1}}
        health = isolated_lease.token_health(live=True)

    assert health["jarvis"]["present"] is True and health["jarvis"]["valid"] is True
    assert health["notify"]["present"] is False and health["notify"]["reason"] == "absent"


def test_egress_falls_back_when_notify_token_is_401(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFY_BOT_TOKEN", "N" * 30)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "B" * 30)
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "J" * 30)

    assert [slot for slot, _ in isolated_lease.egress_token_candidates()] == ["notify", "fallback", "jarvis"]

    def fake_api(token, method, params):
        if token.startswith("NNNN"):
            return {"ok": False, "error_code": 401, "description": "Unauthorized"}
        return {"ok": True, "result": {"message_id": 7}}

    with patch("app.platform.telegram_coordinator._send_tg_api", side_effect=fake_api):
        res = isolated_lease.dispatch_egress_alert("P0 outage", "prod down", severity="CRITICAL")

    assert res["sent"] is True
    assert res["via"] == "fallback"
    # The dead slot is blacklisted for this process, so P0 alerts keep flowing.
    assert "notify" not in [slot for slot, _ in isolated_lease.egress_token_candidates()]


def test_egress_reports_failure_when_every_slot_is_dead(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_NOTIFY_BOT_TOKEN", "N" * 30)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "B" * 30)
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "J" * 30)

    with patch(
        "app.platform.telegram_coordinator._send_tg_api",
        return_value={"ok": False, "error_code": 401, "description": "Unauthorized"},
    ):
        res = isolated_lease.dispatch_egress_alert("P0 outage", "prod down")

    assert res["sent"] is False
    assert res["reason"] == "unauthorized"
    assert isolated_lease.egress_token_candidates() == []


# ---------------------------------------------------------------------------
# Runner behavior: never fake ingestion, never fight for the token
# ---------------------------------------------------------------------------


def _patch_runner(monkeypatch, *, valid_token: bool = True):
    """Neutralise network + bot construction for run_jarvis_polling tests."""
    monkeypatch.setattr(tc.time, "sleep", lambda *_: None)
    monkeypatch.setattr(
        tc,
        "validate_bot_token",
        lambda *a, **k: {"valid": valid_token, "username": "@Sumits_jarvis_bot", "reason": "ok" if valid_token else "unauthorized"},
    )
    monkeypatch.setattr("app.integrations.telegram_bot.get_telegram_bot", lambda: MagicMock())


def test_runner_refuses_invalid_token_without_calling_api(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    _patch_runner(monkeypatch, valid_token=False)

    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        isolated_lease.run_jarvis_polling(poll_timeout=0, max_iterations=1, instance_id="laptop:1", role="local")
        mock_api.assert_not_called()

    assert isolated_lease.get_polling_lease("laptop:1")["holder"] is None


def test_runner_stands_by_when_owner_is_another_role(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    monkeypatch.setenv("TELEGRAM_INGRESS_OWNER", "vps")
    _patch_runner(monkeypatch)

    with patch("app.platform.telegram_coordinator._send_tg_api") as mock_api:
        isolated_lease.run_jarvis_polling(
            poll_timeout=0,
            max_iterations=5,
            max_standby_rounds=1,
            instance_id="laptop:1",
            role="local",
        )
        mock_api.assert_not_called()

    assert isolated_lease.ingress_conflict_state()["last_standby_reason"] == "ingress_owner_is_vps"


def test_runner_409_releases_lease_and_enters_standby(isolated_lease, monkeypatch):
    monkeypatch.setenv("TELEGRAM_JARVIS_BOT_TOKEN", "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz12345")
    _patch_runner(monkeypatch)

    conflict = {
        "ok": False,
        "error_code": 409,
        "description": "Conflict: terminated by other getUpdates request",
    }
    with patch("app.platform.telegram_coordinator._send_tg_api", return_value=conflict) as mock_api:
        isolated_lease.run_jarvis_polling(
            poll_timeout=0,
            max_iterations=3,
            max_standby_rounds=1,
            instance_id="laptop:1",
            role="local",
        )

    assert mock_api.call_count == 1  # one getUpdates attempt, then honest standby
    state = isolated_lease.ingress_conflict_state()
    assert state["conflict_count"] == 1
    assert state["external_conflict_until"] is not None
    assert state["last_standby_reason"] == "external_consumer_conflict"
    # The external owner of the token must not be shadowed by our stale lease.
    assert isolated_lease.get_polling_lease("laptop:1")["holder"] is None
