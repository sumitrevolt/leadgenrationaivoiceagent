"""
Tests for app.voice_agent.turn_metrics — the per-turn latency helper (P1).

Pure functions; no network/LLM. Disk writes are routed to a tmp dir so the test
never touches the real data/ directory.
"""

import json
import os

from app.voice_agent import turn_metrics as tm


def test_now_ms_monotonic():
    a = tm.now_ms()
    b = tm.now_ms()
    assert isinstance(a, float)
    assert b >= a


def test_enabled_default_on(monkeypatch):
    monkeypatch.delenv("TURN_METRICS", raising=False)
    assert tm.enabled() is True
    for off in ("0", "false", "no", "off", "OFF"):
        monkeypatch.setenv("TURN_METRICS", off)
        assert tm.enabled() is False
    monkeypatch.setenv("TURN_METRICS", "1")
    assert tm.enabled() is True


def test_percentile_basic():
    assert tm.percentile([], 50) is None
    assert tm.percentile([42.0], 95) == 42.0
    # 1..10 -> p50 = 5.5 (linear interpolation); p95 = 9.55 -> 9.5 (round-half-even)
    vals = [float(i) for i in range(1, 11)]
    assert tm.percentile(vals, 50) == 5.5
    assert tm.percentile(vals, 95) == 9.5
    # non-numbers + bools are ignored
    assert tm.percentile([1.0, True, "x", None, 3.0], 50) == 2.0


def test_rollup_over_ms_keys():
    records = [
        {"stt_ms": 100.0, "turn_ms": 900.0, "outcome": "ok"},
        {"stt_ms": 200.0, "turn_ms": 1100.0, "outcome": "ok"},
        {"stt_ms": 300.0, "turn_ms": 1300.0, "llm_first_ms": 400.0},
        {"outcome": "junk"},  # no _ms keys — counted but contributes nothing
    ]
    out = tm.rollup(records)
    assert out["count"] == 4
    m = out["metrics"]
    assert m["stt_ms"]["n"] == 3
    assert m["stt_ms"]["p50"] == 200.0
    assert m["stt_ms"]["max"] == 300.0
    assert m["stt_ms"]["avg"] == 200.0
    assert m["turn_ms"]["n"] == 3
    assert m["llm_first_ms"]["n"] == 1
    # known keys come first in declared order
    keys = list(m.keys())
    assert keys.index("stt_ms") < keys.index("turn_ms")


def test_rollup_ignores_non_ms_and_non_numeric():
    out = tm.rollup([{"stt_ms": "slow", "llm_ms": None, "count_ms": 5}])
    # stt_ms is a string, llm_ms is None -> neither rolled up; count_ms IS numeric *_ms
    assert "stt_ms" not in out["metrics"]
    assert "llm_ms" not in out["metrics"]
    assert out["metrics"]["count_ms"]["n"] == 1


def test_record_turn_writes_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("TURN_METRICS", "1")
    base = str(tmp_path / "tm")
    ok = tm.record_turn(
        {"path": "vobiz_stream", "stt_ms": 120.4, "turn_ms": 980.6, "outcome": "ok"},
        base_dir=base,
    )
    assert ok is True
    recs = tm.load_day(base_dir=base)
    assert len(recs) == 1
    r = recs[0]
    assert r["path"] == "vobiz_stream"
    assert r["stt_ms"] == 120.4
    assert "ts" in r  # auto-stamped
    # summarize over the day works
    summary = tm.summarize_day(base_dir=base)
    assert summary["count"] == 1
    assert summary["metrics"]["stt_ms"]["p50"] == 120.4


def test_record_turn_disabled_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("TURN_METRICS", "0")
    base = str(tmp_path / "off")
    ok = tm.record_turn({"stt_ms": 1.0}, base_dir=base)
    assert ok is False
    assert not os.path.isdir(base) or tm.load_day(base_dir=base) == []


def test_record_turn_drops_none_values(tmp_path, monkeypatch):
    monkeypatch.setenv("TURN_METRICS", "1")
    base = str(tmp_path / "tm2")
    tm.record_turn({"stt_ms": 50.0, "tts_first_ms": None, "outcome": "empty_stt"}, base_dir=base)
    recs = tm.load_day(base_dir=base)
    assert "tts_first_ms" not in recs[0]
    assert recs[0]["outcome"] == "empty_stt"


def test_record_turn_empty_or_bad_input(tmp_path, monkeypatch):
    monkeypatch.setenv("TURN_METRICS", "1")
    base = str(tmp_path / "tm3")
    assert tm.record_turn({}, base_dir=base) is False
    assert tm.record_turn(None, base_dir=base) is False  # type: ignore[arg-type]


def test_turn_stamp_builder_gaps():
    b = tm.TurnStampBuilder(speech_end_ms=1000.0)
    b.stamp("stt_final", at_ms=120.0)
    b.stamp("llm_request_started", at_ms=150.0)
    b.stamp("llm_first_token", at_ms=900.0)
    b.stamp("first_audio", at_ms=1200.0)
    b.generation_id = "abc123"
    b.interrupted = True
    rec = b.build(outcome="ok")
    assert rec["turn_id"]
    assert rec["generation_id"] == "abc123"
    assert rec["stt_final_ms"] == 120.0
    assert rec["llm_first_ms"] == 900.0
    assert rec["first_audio_ms"] == 1200.0
    assert rec["interrupted"] is True
    assert "reply_text" not in rec
