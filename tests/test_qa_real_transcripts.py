"""W2.2 deferred-half — QA real-transcript replay (gated QA_REAL_TRANSCRIPTS).

run_qa replayed only canned SCRIPTS/_GENERIC_TURNS, so QA never exercised what
REAL callers actually say (Hinglish STT quirks included) or the niches real calls
land on. With QA_REAL_TRANSCRIPTS=1: recent transcript user-turns are replayed
(junk-STT skipped, deduped, bounded) and transcript niches join the QA targets.
Flag unset = byte-identical old behaviour (inert default).
"""

from __future__ import annotations

import asyncio
import json

import app.agents.staff as staff
from app.platform import team


class _StubBrain:
    def __init__(self, niche=""):
        self.niche = niche
        self._i = 0

    async def reply(self, history, turn):
        self._i += 1
        return f"theek hai ji, point {self._i} note kiya"


def _write(tmp_path, recs) -> None:
    d = tmp_path / "data" / "call_transcripts"
    d.mkdir(parents=True)
    with open(d / "2026-07-06.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_real_transcript_turns_extraction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write(
        tmp_path,
        [
            {
                "niche": "gym",
                "messages": [
                    {"role": "user", "content": "price kya hai bhaiya"},
                    {"role": "assistant", "content": "haan ji batata hoon"},
                    {"role": "user", "content": "..."},  # junk STT → skip
                    {"role": "user", "content": "price kya hai bhaiya"},  # dupe → skip
                    {"role": "user", "content": "timing kya hai"},
                ],
            },
        ],
    )
    got = staff._real_transcript_turns()
    assert got == {"gym": ["price kya hai bhaiya", "timing kya hai"]}


def test_run_qa_inert_without_flag(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("QA_REAL_TRANSCRIPTS", raising=False)
    _write(
        tmp_path,
        [{"niche": "gym", "messages": [{"role": "user", "content": "price kya hai bhaiya"}]}],
    )
    monkeypatch.setattr("app.voice_agent.telecaller_brain.TelecallerBrain", _StubBrain)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    res = asyncio.run(staff.run_qa(niches=["insurance"]))
    assert res["niches"] == ["insurance"], "flag OFF → transcript niches must NOT be pulled in"
    assert res["turns"] == len(staff.SCRIPTS["insurance"])


def test_run_qa_replays_real_turns_when_enabled(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("QA_REAL_TRANSCRIPTS", "1")
    _write(
        tmp_path,
        [
            {
                "niche": "gym",
                "messages": [
                    {"role": "user", "content": "price kya hai bhaiya"},
                    {"role": "user", "content": "timing kya hai subah"},
                ],
            },
        ],
    )
    monkeypatch.setattr("app.voice_agent.telecaller_brain.TelecallerBrain", _StubBrain)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    res = asyncio.run(staff.run_qa(niches=["insurance"]))
    assert "gym" in res["niches"], "transcript niche must join the QA targets"
    assert res["turns"] == len(staff.SCRIPTS["insurance"]) + 2, "gym must replay its 2 REAL turns"


def test_run_qa_bounds_a_stalled_reply(monkeypatch):
    class _StalledBrain:
        def __init__(self, niche=""):
            self.niche = niche

        async def reply(self, history, turn):
            await asyncio.Event().wait()

    monkeypatch.setattr("app.voice_agent.telecaller_brain.TelecallerBrain", _StalledBrain)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setenv("QA_MAX_TURNS", "1")
    monkeypatch.setenv("QA_REPLY_TIMEOUT_S", "0.05")

    res = asyncio.run(staff.run_qa(niches=["insurance"]))

    assert res["turns"] == 1
    assert res["truncated"] is True
    assert any("REPLY TIMEOUT" in issue for issue in res["issues"])
