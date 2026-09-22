"""Egress token resolution — the unified chain through the real call surface.

One owner: ``key_manager.resolve_service_secret`` resolves the Notify slot
(env NOTIFY -> encrypted-vault NOTIFY). ``telegram_egress._token_candidates``
appends env-only last resorts (legacy BOT_TOKEN -> JARVIS) so P0 alerts never
silently die. These tests pin the full documented order:

    NOTIFY env -> NOTIFY vault -> legacy BOT_TOKEN -> JARVIS
"""

from __future__ import annotations

import app.platform.key_manager as key_manager
import app.utils.telegram_egress as telegram_egress

_NOTIFY_ENV = "TELEGRAM_NOTIFY_BOT_TOKEN"
_LEGACY_ENV = "TELEGRAM_BOT_TOKEN"
_JARVIS_ENV = "TELEGRAM_JARVIS_BOT_TOKEN"


def _clear_env(monkeypatch):
    for name in (_NOTIFY_ENV, _LEGACY_ENV, _JARVIS_ENV):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(telegram_egress, "_dead_tokens", set())


def test_env_notify_token_wins_over_vault(monkeypatch):
    """Env is the emergency rollback path and beats the encrypted vault."""
    env_token = "E" * 30

    class VaultOnly:
        def get_key_value(self, service):
            return "V" * 30

    _clear_env(monkeypatch)
    monkeypatch.setenv(_NOTIFY_ENV, env_token)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: VaultOnly())

    assert telegram_egress._token_candidates() == [env_token]


def test_vault_notify_token_used_when_env_absent(monkeypatch):
    """Rotated Notify credential survives restart without plaintext env mutation."""
    vault_token = "V" * 30

    class VaultOnly:
        def get_key_value(self, service):
            return vault_token if service == "telegram_notify_bot_token" else None

    _clear_env(monkeypatch)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: VaultOnly())

    assert telegram_egress._token_candidates() == [vault_token]


def test_notify_fallback_order_vault_then_legacy_then_jarvis(monkeypatch):
    """With env absent: vault NOTIFY -> legacy BOT_TOKEN -> JARVIS, in order."""
    vault_token = "V" * 30
    legacy_token = "L" * 30
    jarvis_token = "J" * 30

    class VaultThenEnvFallbacks:
        def get_key_value(self, service):
            return vault_token if service == "telegram_notify_bot_token" else None

    _clear_env(monkeypatch)
    monkeypatch.setenv(_LEGACY_ENV, legacy_token)
    monkeypatch.setenv(_JARVIS_ENV, jarvis_token)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: VaultThenEnvFallbacks())

    assert telegram_egress._token_candidates() == [vault_token, legacy_token, jarvis_token]
    assert telegram_egress._bot_token() == vault_token


def test_send_utility_fails_closed_when_env_and_vault_are_empty(monkeypatch):
    class EmptyKeyManager:
        def get_key_value(self, service):
            return None

    _clear_env(monkeypatch)
    monkeypatch.setattr(key_manager, "get_key_manager", lambda: EmptyKeyManager())

    assert telegram_egress._token_candidates() == []
    assert telegram_egress._bot_token() is None


def test_vault_unavailable_degrades_to_env_and_legacy_chain(monkeypatch):
    """A broken vault fails open to the remaining env candidates, never raises."""
    env_token = "E" * 30

    def broken_key_manager():
        raise RuntimeError("vault unavailable")

    _clear_env(monkeypatch)
    monkeypatch.setenv(_NOTIFY_ENV, env_token)
    monkeypatch.setattr(key_manager, "get_key_manager", broken_key_manager)

    assert telegram_egress._token_candidates() == [env_token]
