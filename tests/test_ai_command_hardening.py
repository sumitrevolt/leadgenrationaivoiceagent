"""Tests for the admin AI command hardening."""

from __future__ import annotations

import asyncio
import json

import pytest


def _admin_user():
    from app.models.user import User, UserRole, UserStatus

    return User(
        id="u-admin",
        email="admin@example.com",
        first_name="Admin",
        last_name="User",
        role=UserRole.SUPER_ADMIN,
        status=UserStatus.ACTIVE,
        password_hash="$2b$12$mockhash",
        password_salt="",
    )


def test_command_query_model_max_length():
    from app.api.ai import CommandIn

    with pytest.raises(Exception):
        CommandIn(query="x" * 501)


def test_normalize_command_query():
    from app.api.ai import _normalize_command_query

    raw = "  hello\nthere\t" + ("x" * 600)
    out = _normalize_command_query(raw)
    assert "\n" not in out
    assert "\t" not in out
    assert out.startswith("hello there")
    assert len(out) <= 500


def test_nl_command_sanitizes_prompt(monkeypatch):
    from app.api import ai
    from app.voice_agent import free_ai

    captured = {}

    async def _fake_chat(system, messages, **kw):
        captured["system"] = system
        captured["messages"] = messages
        return json.dumps({"action": "help", "reply": "ok"}), "mock"

    monkeypatch.setattr(free_ai, "chat", _fake_chat)

    out = asyncio.run(
        ai.nl_command(
            ai.CommandIn(query="  stats\n dikhao \t" + ("x" * 50)),
            _admin_user(),
        )
    )
    assert out["ok"] is True
    assert out["action"] == "help"
    assert captured["messages"][0]["content"] == "stats dikhao " + ("x" * 50)
