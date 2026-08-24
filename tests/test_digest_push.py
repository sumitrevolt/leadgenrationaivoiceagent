"""W1.15 — daily digest gets a phone push channel (ntfy), gated + additive.

`run_digest` persisted to a file, logged a manager event, and (if NOTIFY_EMAIL set)
emailed — but had NO phone-push channel, so the founder's daily digest could sit unseen
in an inbox. Fix: a best-effort ntfy push, gated by DIGEST_NTFY (default OFF = inert),
so it ships additively and is switched on by the user.
"""

from __future__ import annotations

import asyncio

import app.agents.staff as staff
from app.platform import team


def _run(coro):
    return asyncio.run(coro)


def test_digest_pushes_to_ntfy_when_enabled(monkeypatch):
    pushes = []

    async def _spy_push(title, message, **k):
        pushes.append((title, message))

    monkeypatch.setattr("app.integrations.ntfy.push", _spy_push)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(team, "recent_events", lambda *a, **k: [])
    monkeypatch.setenv("DIGEST_NTFY", "1")

    res = _run(staff.run_digest())
    assert "text" in res
    assert len(pushes) == 1, "digest must push to ntfy when DIGEST_NTFY=1"
    joined = pushes[0][0] + pushes[0][1]
    assert "Daily Digest" in joined


def test_digest_no_push_when_disabled(monkeypatch):
    pushes = []

    async def _spy_push(title, message, **k):
        pushes.append(1)

    monkeypatch.setattr("app.integrations.ntfy.push", _spy_push)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(team, "recent_events", lambda *a, **k: [])
    monkeypatch.delenv("DIGEST_NTFY", raising=False)

    _run(staff.run_digest())
    assert pushes == [], "digest must NOT push when DIGEST_NTFY unset (additive/inert default)"
