"""Numeric owner allowlist (TELEGRAM_OWNER_USER_IDS) — spoof-proof policy.

When the numeric list is set, username matches are IGNORED by design
(usernames are changeable). When unset, legacy username/chat behaviour is
preserved (backward compatible with live VPS config).
"""

from __future__ import annotations

import pytest

from app.integrations import telegram_bot as tb


@pytest.fixture()
def bot():
    return tb.TelegramBot(token="x" * 24)


def test_numeric_list_set_denies_username_match(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_IDS", "1621120182")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", "")
    # numeric id match => owner
    assert bot.is_owner(user_id="1621120182", username="sumitrevolt") is True
    # same username, wrong numeric id => DENIED (username not proof)
    assert bot.is_owner(user_id="999", username="sumitrevolt") is False
    # chat id in the numeric list => owner
    assert bot.is_owner(user_id="1", username="nobody", chat_id="1621120182") is True


def test_numeric_list_empty_falls_back_to_legacy_username(bot, monkeypatch):
    monkeypatch.delenv("TELEGRAM_OWNER_USER_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "sumitrevolt")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", "")
    assert bot.is_owner(user_id="1", username="SumitsRevolt") is True
    assert bot.is_owner(user_id="1", username="stranger") is False


def test_chat_ids_still_honoured_in_legacy_mode(bot, monkeypatch):
    monkeypatch.delenv("TELEGRAM_OWNER_USER_IDS", raising=False)
    monkeypatch.setenv("TELEGRAM_OWNER_USERNAMES", "")
    monkeypatch.setenv("TELEGRAM_OWNER_CHAT_IDS", "123,-456")
    assert bot.is_owner(user_id="1", username="x", chat_id="123") is True
    assert bot.is_owner(user_id="1", username="x", chat_id="-456") is True
    assert bot.is_owner(user_id="1", username="x", chat_id="789") is False


def test_numeric_parser_ignores_garbage(monkeypatch):
    monkeypatch.setenv("TELEGRAM_OWNER_USER_IDS", "abc, 123, -45, @678")
    assert tb._get_owner_user_ids() == {123, -45, 678}
    monkeypatch.delenv("TELEGRAM_OWNER_USER_IDS", raising=False)
    assert tb._get_owner_user_ids() == set()
