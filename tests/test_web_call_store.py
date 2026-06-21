"""Web-call session store — lead_key gate + chronological list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.voice_agent import web_call_store as store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    path = tmp_path / "web_call_sessions.jsonl"
    monkeypatch.setattr(store, "_STORE", path)
    return path


def test_append_requires_valid_lead_key(isolated_store):
    sid = "sess-abc12345"
    assert store.append_session({"session_id": sid, "lead_key": "short", "turns": [{"role": "user", "text": "hi"}]}) is False
    assert store.append_session({"session_id": sid, "lead_key": "wc_testuser01", "turns": [{"role": "user", "text": "hi"}]}) is True
    assert isolated_store.is_file()


def test_list_newest_first_and_optional_turns(isolated_store):
    lead = "wc_histtest01"
    for i in range(3):
        store.append_session(
            {
                "session_id": f"sess-{i:02d}-abcd",
                "lead_key": lead,
                "started_at": f"2026-06-2{i}T10:00:00+00:00",
                "turns": [{"role": "user", "text": f"turn{i}"}],
            }
        )
    summary = store.list_sessions(lead, limit=10, include_turns=False)
    assert len(summary) == 3
    assert "turns" not in summary[0]
    assert summary[0]["started_at"].startswith("2026-06-22")

    full = store.list_sessions(lead, limit=1, include_turns=True)
    assert full[0]["turns"][0]["text"] == "turn2"


def test_get_session_scoped_to_lead(isolated_store):
    lead = "wc_ownerkey01"
    sid = "sess-owner-01"
    store.append_session({"session_id": sid, "lead_key": lead, "turns": [{"role": "bot", "text": "namaste"}]})
    row = store.get_session(sid, lead)
    assert row and row["session_id"] == sid
    assert store.get_session(sid, "wc_otherkey9") is None
