"""
Tests for Telegram Dual-Bot Coordination Architecture
======================================================
Verifies:
1. Token resolution & fail-closed behavior
2. Role separation (Jarvis Ingress vs Notify Egress)
3. Zero 409 conflict guarantee
4. Owner authentication & deduplication
5. Cross-bot coordination dispatch
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

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


def test_update_deduplication():
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
