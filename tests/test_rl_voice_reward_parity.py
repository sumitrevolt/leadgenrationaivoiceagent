"""RL voice-reward parity regression (2026-09-05).

Root cause fixed here: of the 3 qualification writers, only
post_call_hooks.auto_qualify_and_downstream recorded a voice reward — the
LIVE vobiz_stream._auto_qualify path and the legacy call_manager path wrote
data/call_qualifications.jsonl without any reward hook, so the voice domain
had 0 rewards despite 159 qualifications (prod evidence 2026-09-05).

These tests pin that EVERY qualification writer also records a reward
(ref=call_id — record_reward's ref-dedupe makes double-record impossible
when two paths fire for the same call), plus a functional end-to-end check
through the vobiz_stream handler method.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os

import pytest

from app.agents.rl import reward as rl


def _src(mod) -> str:
    return inspect.getsource(mod)


def test_all_qualification_writers_record_voice_reward():
    from app.telephony import call_manager, post_call_hooks, vobiz_stream

    for mod, name in (
        (post_call_hooks, "post_call_hooks"),
        (vobist := vobiz_stream, "vobiz_stream"),
        (call_manager, "call_manager"),
    ):
        src = _src(mod)
        assert "record_reward(" in src, f"{name}: missing record_reward hook"
        assert '"voice"' in src or "'voice'" in src, f"{name}: reward not voice-domain"


def test_reward_dedupe_same_call_id_single_row(tmp_path, monkeypatch):
    """ref=call_id idempotency: two writers for the same call -> 1 reward."""
    rewards = tmp_path / "rl_rewards.jsonl"
    monkeypatch.setattr(rl, "_REWARDS", str(rewards))
    monkeypatch.setenv("RL_ENGINE", "1")

    q = {"interest_score": 72, "qualified": True, "outcome": "interested"}
    rl.record_reward("voice", "gym", rl.voice_reward(q), ref="CALL-1")
    rl.record_reward("voice", "gym", rl.voice_reward(q), ref="CALL-1")  # mirror path
    rows = [json.loads(l) for l in rewards.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    assert rows[0]["domain"] == "voice"
    assert rows[0]["ref"] == "CALL-1"


def test_reward_hook_sits_after_qual_write_in_each_writer():
    """Static structure pin: in EVERY qual-writer file, the reward hook must
    appear after the call_qualifications.jsonl write (i.e. it fires on real
    qualifications). Heavy-module functional import avoided deliberately —
    vobiz_stream pulls STT/whisper at import time (netguard-unsafe in tests)."""
    for rel in (
        "app/telephony/post_call_hooks.py",
        "app/telephony/vobiz_stream.py",
        "app/telephony/call_manager.py",
    ):
        src = open(rel, encoding="utf-8").read()
        q_at = src.find("call_qualifications.jsonl")
        r_at = src.find("record_reward(")
        assert q_at != -1, f"{rel}: not a qualification writer anymore?"
        assert r_at != -1, f"{rel}: reward hook missing (2026-09-05 regression)"
        assert r_at > q_at, f"{rel}: reward hook must follow the qual write"


def test_vobiz_reward_hook_context_fields():
    """The live-path hook must tag its rewards (ref=stream_sid, path marker)
    so ops can attribute voice rewards to the stream pipeline."""
    src = open("app/telephony/vobiz_stream.py", encoding="utf-8").read()
    assert '"path": "vobiz_stream"' in src or "'path': 'vobiz_stream'" in src
    assert "ref=str(self.stream_sid" in src


def test_voice_reward_score_sane():
    assert rl.voice_reward({"outcome": "appointment"}) == 1.0
    assert rl.voice_reward({"outcome": "dnd"}) == 0.0
    assert rl.voice_reward({}) == 0.4  # unqualified default
