"""Web-call session store — lead_key gate + chronological list."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.voice_agent import web_call_store as store


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    path = tmp_path / "web_call_sessions.jsonl"
    tdir = tmp_path / "call_transcripts"
    monkeypatch.setattr(store, "_STORE", path)
    monkeypatch.setattr(store, "_TRANSCRIPTS_DIR", lambda: tdir)
    return path


def test_append_requires_valid_lead_key(isolated_store):
    sid = "sess-abc12345"
    assert (
        store.append_session(
            {"session_id": sid, "lead_key": "short", "turns": [{"role": "user", "text": "hi"}]}
        )
        is False
    )
    assert (
        store.append_session(
            {
                "session_id": sid,
                "lead_key": "wc_testuser01",
                "turns": [{"role": "user", "text": "hi"}],
            }
        )
        is True
    )
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
    store.append_session(
        {"session_id": sid, "lead_key": lead, "turns": [{"role": "bot", "text": "namaste"}]}
    )
    row = store.get_session(sid, lead)
    assert row and row["session_id"] == sid
    assert store.get_session(sid, "wc_otherkey9") is None


def test_mirror_writes_call_transcripts_for_training(isolated_store, tmp_path):
    lead = "wc_trainkey01"
    sid = "sess-train-01"
    ok = store.append_session(
        {
            "session_id": sid,
            "lead_key": lead,
            "started_at": "2026-06-21T10:00:00+00:00",
            "ended_at": "2026-06-21T10:02:00+00:00",
            "duration_s": 120,
            "niche": "solar_residential",
            "turns": [
                {"role": "assistant", "text": "Namaste"},
                {"role": "user", "text": "Solar chahiye"},
            ],
        }
    )
    assert ok
    tfile = tmp_path / "call_transcripts" / "2026-06-21.jsonl"
    assert tfile.is_file()
    rec = json.loads(tfile.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert rec["stream_sid"] == sid
    assert rec["source"] == "web_call_test"
    assert rec["messages"][-1]["content"] == "Solar chahiye"
    assert rec["user_turns"] == 1
    row = store.get_session(sid, lead)
    assert row and store.mirror_session_to_training_transcript(row) is False
