"""W2.3 deferred-half — trainer per-niche metric aggregation.

run_trainer aggregated ALL niches together, so a noisy-STT niche was masked by
the aggregate: global junk_ratio stayed under the threshold while one niche was
drowning, and no suggestion ever named it. Now: summary["by_niche"] carries
per-niche metrics, and a niche-targeted suggestion fires when the worst niche
crosses the junk threshold that the aggregate hides.
"""

from __future__ import annotations

import asyncio
import json

import app.agents.staff as staff
from app.platform import team


def _write_transcripts(tmp_path, recs) -> None:
    d = tmp_path / "data" / "call_transcripts"
    d.mkdir(parents=True)
    with open(d / "2026-07-06.jsonl", "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _rec(niche: str, user_texts: list[str]) -> dict:
    msgs = []
    for i, t in enumerate(user_texts):
        msgs.append({"role": "user", "content": t})
        msgs.append({"role": "assistant", "content": f"theek hai ji, point {i} samjha"})
    return {"niche": niche, "stt_counts": {"groq": len(user_texts)}, "messages": msgs}


def test_by_niche_breakdown(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    _write_transcripts(
        tmp_path,
        [
            _rec("gym", ["haan bhaiya batao", "price kya hai", "theek hai done"]),
            _rec("salon", ["...", "..", ",,"]),
        ],
    )
    res = asyncio.run(staff.run_trainer())
    bn = res["by_niche"]
    assert bn["gym"]["calls"] == 1
    assert bn["salon"]["calls"] == 1
    assert bn["gym"]["junk_stt_ratio"] == 0.0
    assert bn["salon"]["junk_stt_ratio"] == 1.0


def test_niche_masked_junk_gets_targeted_suggestion(tmp_path, monkeypatch):
    """Global junk 3/12 = 0.25 <= 0.3 threshold (no global suggestion), but the
    salon niche is 100% junk — the trainer must name it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    clean = [f"haan bhaiya point number {i} batao" for i in range(9)]
    _write_transcripts(
        tmp_path,
        [
            _rec("gym", clean[:3]),
            _rec("gym", clean[3:6]),
            _rec("gym", clean[6:9]),
            _rec("salon", ["...", "..", ",,"]),
        ],
    )
    res = asyncio.run(staff.run_trainer())
    assert res["junk_stt_ratio"] <= 0.3, "precondition: aggregate must stay under threshold"
    assert any("salon" in s for s in res["suggestions"]), (
        "worst niche crossing the junk threshold must get a targeted suggestion"
    )
