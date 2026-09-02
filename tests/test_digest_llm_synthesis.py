"""W2.4 — daily digest gets an optional cheap-LLM "why + next action" synthesis.

The digest was a rule-based line concat — accurate but flat (numbers, no interpretation).
W2.4 adds an optional free-LLM (bulk profile, W1.10-cached) synthesis appended to the
digest, gated by DIGEST_LLM (default OFF → pure rule-based), fail-open (LLM error/empty
→ digest unchanged).
"""

from __future__ import annotations

import asyncio

import app.agents.staff as staff
from app.platform import team


def _quiet(monkeypatch):
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(team, "recent_events", lambda *a, **k: [])
    monkeypatch.delenv("DIGEST_NTFY", raising=False)


def test_llm_synthesis_appended_when_enabled(monkeypatch):
    calls = []

    async def _fake_chat(system, messages, **k):
        calls.append(k.get("profile"))
        return ("Dhyan: inquiries kam aa rahi. Action: landing page CTA push karo.", "stub")

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    _quiet(monkeypatch)
    monkeypatch.setenv("DIGEST_LLM", "1")

    res = asyncio.run(staff.run_digest())
    assert len(calls) == 1, "digest must call the LLM once when DIGEST_LLM=1"
    assert calls[0] == "bulk", "synthesis must use the cached bulk profile"
    assert "🧠" in res["text"] and "landing page CTA push" in res["text"]


def test_no_llm_when_disabled(monkeypatch):
    calls = []

    async def _fake_chat(system, messages, **k):
        calls.append(1)
        return ("x", "stub")

    monkeypatch.setattr("app.voice_agent.free_ai.chat", _fake_chat)
    _quiet(monkeypatch)
    monkeypatch.delenv("DIGEST_LLM", raising=False)

    res = asyncio.run(staff.run_digest())
    assert calls == [], "digest must NOT call the LLM when DIGEST_LLM unset"
    assert "🧠" not in res["text"]
