"""
Tests for app.agents.live_eval (P4-3) — live-transcript scoring + eval_gate feed.
Deterministic layers only; LLM judge tested in its disabled (free) path.
"""

import json
from pathlib import Path

from app.agents import live_eval as le


def test_score_transcript_clean_vs_bad():
    clean = [
        {"role": "assistant", "content": "Namaste, do minute baat kar sakti hoon?"},
        {
            "role": "user",
            "content": (
                "haan boliye, main solar lagwane ke baare mein soch raha hoon kyunki "
                "mera bijli ka bill har mahine bahut zyada aata hai aur kam karna chahta hoon"
            ),
        },
        {"role": "assistant", "content": "Achha, samjha."},
    ]
    bad = [
        {"role": "assistant", "content": "main aapki kaise sahayata karu? " + "word " * 50},
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye"},
        {"role": "user", "content": "dekhte hain"},
        {"role": "assistant", "content": "demo book kar du? aur batao kya chahiye?"},
    ]
    cs = le.score_transcript(clean)
    bs = le.score_transcript(bad)
    assert 0.0 <= bs["score"] <= cs["score"] <= 1.0
    assert bs["qa_finding_count"] >= 1  # pushy/literal/etc flagged
    assert cs["qa_finding_count"] == 0


def test_score_transcript_empty_safe():
    out = le.score_transcript([])
    assert out["score"] == 1.0
    assert out["qa_finding_count"] == 0
    assert le.score_transcript(None)["score"] == 1.0  # type: ignore[arg-type]


def test_interruption_stats():
    rec = {
        "barge_count": 3,
        "turn_metrics": [
            {"outcome": "ok"},
            {"outcome": "ok"},
            {"outcome": "empty_stt"},
        ],
    }
    out = le.interruption_stats(rec)
    assert out["barges"] == 3
    assert out["turns"] == 3
    assert out["outcomes"]["ok"] == 2
    assert out["classification"] == "unclassified"  # false-vs-missed needs D-6
    # missing fields -> safe zeros
    assert le.interruption_stats({})["barges"] == 0


def _write_calls(tmp_path: Path) -> Path:
    d = tmp_path / "ct"
    d.mkdir()
    fp = d / "2026-06-21.jsonl"
    rows = [
        {
            "stream_sid": "c1",
            "niche": "solar",
            "barge_count": 1,
            "turn_metrics": [{"outcome": "ok"}],
            "messages": [
                {"role": "assistant", "content": "Namaste, do minute baat kar sakti hoon?"},
                {"role": "user", "content": "haan"},
            ],
        },
        {
            "stream_sid": "c2",
            "niche": "solar",
            "messages": [
                {"role": "assistant", "content": "demo book kar du?"},
                {"role": "user", "content": "abhi nahi"},
                {"role": "user", "content": "dekhte hain"},
                {"role": "assistant", "content": "ek baar dekh lijiye, demo?"},
            ],
        },
    ]
    fp.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return d


def test_load_and_eval_recent_calls(tmp_path):
    d = _write_calls(tmp_path)
    recs = le._load_recent_transcripts(5, base_dir=d)
    assert len(recs) == 2

    out = le.eval_recent_calls(5, base_dir=d)
    assert out["n"] == 2
    assert 0.0 <= out["mean_score"] <= 1.0
    assert len(out["per_call"]) == 2
    assert out["per_call"][0]["interruptions"]["barges"] == 1
    # second call has a polite-no push -> at least one QA finding overall
    assert out["total_qa_findings"] >= 1


def test_eval_recent_calls_empty_dir(tmp_path):
    out = le.eval_recent_calls(5, base_dir=tmp_path / "nope")
    assert out["n"] == 0
    assert out["mean_score"] == 1.0


def test_llm_judge_disabled_by_default(monkeypatch):
    import asyncio

    monkeypatch.delenv("LLM_JUDGE", raising=False)
    out = asyncio.run(le.llm_judge_transcript([{"role": "user", "content": "haan boliye"}]))
    assert out["available"] is False
    assert out["reason"] == "disabled"
