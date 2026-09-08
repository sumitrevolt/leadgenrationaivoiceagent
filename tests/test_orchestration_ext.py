"""Pure-python tests for orchestration-ext (trajectory + agent_consensus).

NO network / DB / LLM — free_ai.chat fully monkeypatched. Trajectory store +
export ko tmp_path pe redirect karte hain (real data/ ko nahi chhuta)."""

from __future__ import annotations

import asyncio
import json
import os

from app.agents import agent_consensus, trajectory


# ----------------------------- trajectory ----------------------------------- #
def _redirect_store(monkeypatch, tmp_path):
    store = os.path.join(str(tmp_path), "agent_trajectories.jsonl")
    monkeypatch.setattr(trajectory, "_STORE", store)
    return store


def test_record_and_best_orders_by_reward(monkeypatch, tmp_path):
    _redirect_store(monkeypatch, tmp_path)

    tid_lo = trajectory.record_trajectory("qualify_lead", [{"step": "ask"}], "ok-low", reward=0.2)
    tid_hi = trajectory.record_trajectory(
        "qualify_lead", [{"step": "ask"}, {"step": "close"}], "ok-high", reward=0.9
    )
    trajectory.record_trajectory("other_action", [], "x", reward=1.0)

    assert tid_lo and tid_hi and tid_lo != tid_hi

    best = trajectory.best_trajectories("qualify_lead", k=5)
    # sirf matching action, reward desc
    assert [b["action"] for b in best] == ["qualify_lead", "qualify_lead"]
    assert best[0]["reward"] == 0.9
    assert best[0]["id"] == tid_hi
    # k cap
    assert len(trajectory.best_trajectories("qualify_lead", k=1)) == 1


def test_record_empty_action_returns_empty(monkeypatch, tmp_path):
    _redirect_store(monkeypatch, tmp_path)
    assert trajectory.record_trajectory("", [], "x", reward=1.0) == ""


def test_best_trajectories_unknown_action_empty(monkeypatch, tmp_path):
    _redirect_store(monkeypatch, tmp_path)
    assert trajectory.best_trajectories("nope") == []


def test_replay_hint_builds_when_present_else_empty(monkeypatch, tmp_path):
    _redirect_store(monkeypatch, tmp_path)
    assert trajectory.replay_hint("qualify_lead") == ""

    trajectory.record_trajectory(
        "qualify_lead",
        [{"step": "greet", "detail": "namaste"}, {"step": "pitch"}],
        "booked demo",
        reward=0.8,
    )
    hint = trajectory.replay_hint("qualify_lead", max_chars=1200)
    assert hint  # non-empty
    assert "reward 0.8" in hint
    assert "booked demo" in hint
    assert len(hint) <= 1400  # cap respected (approx, block-granular)


def test_export_dataset_filters_min_reward(monkeypatch, tmp_path):
    _redirect_store(monkeypatch, tmp_path)
    out_path = os.path.join(str(tmp_path), "exports", "ds.jsonl")

    trajectory.record_trajectory("a", [{"s": 1}], "win", reward=0.9)
    trajectory.record_trajectory("a", [{"s": 2}], "lose", reward=0.1)
    trajectory.record_trajectory("b", [], "win2", reward=0.6)

    res = trajectory.export_dataset(out_path=out_path, min_reward=0.5)
    assert res["ok"] is True
    assert res["count"] == 2
    assert res["path"] == out_path

    lines = [
        json.loads(line)
        for line in open(out_path, encoding="utf-8").read().splitlines()
        if line.strip()
    ]
    assert len(lines) == 2
    assert all(row["reward"] >= 0.5 for row in lines)
    assert {"prompt", "completion", "reward"} <= set(lines[0].keys())


def test_trajectory_enabled_flag(monkeypatch):
    monkeypatch.delenv("TRAJECTORY_LEARN", raising=False)
    assert trajectory.enabled() is False
    monkeypatch.setenv("TRAJECTORY_LEARN", "1")
    assert trajectory.enabled() is True


# ----------------------------- agent_consensus ------------------------------ #
def _patch_voter(monkeypatch, replies):
    """free_ai.chat ko deterministic banao — call index ke hisaab se reply.

    replies = list[str] (index pe) ya callable(messages)->str.
    """
    from app.voice_agent import free_ai

    calls = {"n": 0}

    async def fake_chat(system, messages, **kw):
        i = calls["n"]
        calls["n"] += 1
        if callable(replies):
            text = replies(i, system, messages)
        else:
            text = replies[i % len(replies)]
        return text, "mock"

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    return calls


def test_vote_clear_winner_quorum(monkeypatch):
    # 3 voters, 2 pick "Yes", 1 picks "No" → quorum (2 > 3/2)
    _patch_voter(
        monkeypatch,
        ["reason\nCHOICE: Yes", "reason\nCHOICE: Yes", "reason\nCHOICE: No"],
    )
    res = asyncio.run(agent_consensus.vote("Ship it?", ["Yes", "No"], voters=3))
    assert res["winner"] == "Yes"
    assert res["tally"] == {"Yes": 2, "No": 1}
    assert res["confidence"] == round(2 / 3, 3)
    assert isinstance(res["rationale_samples"], list)


def test_vote_no_quorum_tie(monkeypatch):
    # 2 voters split 1-1 → no clear majority (1 is not > 2/2)
    _patch_voter(monkeypatch, ["CHOICE: Yes", "CHOICE: No"])
    res = asyncio.run(agent_consensus.vote("Ship?", ["Yes", "No"], voters=2))
    assert res["winner"] is None
    assert res["reason"] == "no_quorum"
    assert res["tally"] == {"Yes": 1, "No": 1}


def test_vote_options_too_few_error(monkeypatch):
    _patch_voter(monkeypatch, ["CHOICE: Yes"])
    res = asyncio.run(agent_consensus.vote("?", ["OnlyOne"], voters=3))
    assert res.get("ok") is False
    assert "options" in res["error"].lower() or "2" in res["error"]


def test_vote_voter_fail_abstains(monkeypatch):
    from app.voice_agent import free_ai

    calls = {"n": 0}

    async def flaky_chat(system, messages, **kw):
        i = calls["n"]
        calls["n"] += 1
        if i == 1:
            raise RuntimeError("provider down")
        return "CHOICE: Alpha", "mock"

    monkeypatch.setattr(free_ai, "chat", flaky_chat)
    res = asyncio.run(agent_consensus.vote("Pick", ["Alpha", "Beta"], voters=3))
    # voter 1 abstained → 2 valid votes both Alpha → quorum still holds (2 > 3/2)
    assert res["winner"] == "Alpha"
    assert res["tally"]["Alpha"] == 2
    assert res.get("valid_votes") == 2


def test_vote_unparseable_maps_or_abstains(monkeypatch):
    # garbage reply that contains no option → abstain → no votes
    _patch_voter(monkeypatch, ["I have no idea honestly"])
    res = asyncio.run(agent_consensus.vote("Pick", ["Alpha", "Beta"], voters=1))
    assert res["winner"] is None
    assert res.get("reason") == "no_votes"


def test_map_to_option_index_and_substring():
    opts = ["Increase price", "Keep price"]
    assert agent_consensus._map_to_option("CHOICE: Keep price", opts) == "Keep price"
    assert agent_consensus._map_to_option("2", opts) == "Keep price"
    assert agent_consensus._map_to_option("definitely increase price now", opts) == "Increase price"
    assert agent_consensus._map_to_option("blahblah", opts) is None


def test_consensus_enabled_flag(monkeypatch):
    monkeypatch.delenv("AGENT_CONSENSUS", raising=False)
    assert agent_consensus.enabled() is False
    monkeypatch.setenv("AGENT_CONSENSUS", "yes")
    assert agent_consensus.enabled() is True
