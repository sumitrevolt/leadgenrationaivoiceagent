"""P3c (2026-06-28): per-call self-improve gate — classify failures, propose a better
candidate, and the promotion-gate that only promotes if quality improves. Proposals are
never auto-applied."""

from __future__ import annotations

import asyncio

from app.voice_agent import voice_self_improve as vsi


def test_classify_failures_detects_dodge():
    msgs = [
        {"role": "user", "content": "kitne features hain?"},
        {"role": "assistant", "content": "Google pe dikhta hai kya?"},  # question-back dodge
    ]
    tags = vsi.classify_failures(msgs, score=0.5, flags={})
    assert "unanswered_question" in tags


def test_classify_failures_clean_is_empty():
    msgs = [
        {"role": "user", "content": "haan boliye"},
        {
            "role": "assistant",
            "content": "Char features hain sir — posts, ads, ranking, follow-up.",
        },
    ]
    assert vsi.classify_failures(msgs, score=1.0, flags={}) == []


def test_promotion_gate_passes_real_improvement():
    p = {
        "user_question": "kitne features hain?",
        "bad_reply": "ji zara dobara boliye?",
        "candidate": "Char features hain sir — posts, ads, Google ranking aur follow-up.",
    }
    g = vsi.promotion_gate(p)
    assert g["pass"] is True and g["reason"] == "ok"


def test_promotion_gate_rejects_question_back_and_placeholder():
    assert (
        vsi.promotion_gate({"candidate": "aap interested hain kya?", "bad_reply": "x"})["pass"]
        is False
    )
    assert (
        vsi.promotion_gate({"candidate": "[Company] aapki madad karega", "bad_reply": "x"})[
            "reason"
        ]
        == "placeholder_leak"
    )
    assert vsi.promotion_gate({"candidate": "", "bad_reply": "x"})["reason"] == "no_candidate"


def test_propose_and_status_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(vsi, "_STORE", str(tmp_path / "voice_proposals.jsonl"))

    async def _fake_candidate(niche, q, bad):
        return "Char features hain sir — posts, ads, Google ranking aur follow-up."

    monkeypatch.setattr(vsi, "_candidate_reply", _fake_candidate)
    session = {"niche": "ai_marketing", "session_id": "sess123abc"}
    msgs = [
        {"role": "user", "content": "kitne features hain?"},
        {"role": "assistant", "content": "Google pe dikhta hai kya?"},
    ]
    p = asyncio.run(vsi.propose_from_session(session, msgs, score=0.5, flags={}))
    assert p and p["status"] == "proposed" and p["gate"]["pass"] is True
    rows = vsi.list_proposals(status="proposed")
    assert any(r["id"] == p["id"] for r in rows)
    assert vsi.set_proposal_status(p["id"], "promoted") is True
    assert vsi.list_proposals(status="proposed") == [] or all(
        r["id"] != p["id"] for r in vsi.list_proposals(status="proposed")
    )


def test_propose_skips_clean_call(tmp_path, monkeypatch):
    monkeypatch.setattr(vsi, "_STORE", str(tmp_path / "voice_proposals.jsonl"))
    session = {"niche": "ai_marketing", "session_id": "clean123abc"}
    msgs = [
        {"role": "user", "content": "haan boliye"},
        {
            "role": "assistant",
            "content": "Char features hain sir — posts, ads, ranking, follow-up.",
        },
    ]
    assert asyncio.run(vsi.propose_from_session(session, msgs, score=1.0, flags={})) is None
