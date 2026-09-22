from __future__ import annotations

import app.platform.key_manager as key_manager
import app.utils.telegram_egress as telegram_egress


def test_send_utility_uses_notify_token_from_encrypted_vault(monkeypatch):
    """Every egress helper must share the restart-safe Notify credential source."""
    vault_token = "V" * 30

    class FakeKeyManager:
        def get_key_value(self, service):
            return vault_token if service == "telegram_notify_bot_token" else None

    for name in (
        "TELEGRAM_NOTIFY_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_JARVIS_BOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: FakeKeyManager())
    monkeypatch.setattr(telegram_egress, "_dead_tokens", set())

    assert telegram_egress._token_candidates() == [vault_token]


def test_send_utility_fails_closed_when_env_and_vault_are_empty(monkeypatch):
    class EmptyKeyManager:
        def get_key_value(self, service):
            return None

    for name in (
        "TELEGRAM_NOTIFY_BOT_TOKEN",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_JARVIS_BOT_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: EmptyKeyManager())
    monkeypatch.setattr(telegram_egress, "_dead_tokens", set())

    assert telegram_egress._token_candidates() == []
    assert telegram_egress._bot_token() is None
