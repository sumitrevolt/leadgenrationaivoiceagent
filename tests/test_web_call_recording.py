"""Regression tests for web test-call recording + per-turn latency instrumentation
(2026-06-28). Pure-function coverage — no live WS / no network.

Covers:
  - web_call._rec_ext        magic-byte container detection
  - web_call._turn_meta      perceived latency + stage-clock assembly
  - web_call._log_turn(meta) timing fields persisted on the turn
  - web_call._normalize_session_id_safe
  - call_recordings._SERVE_RE / _MEDIA_BY_EXT accept webcall_*.{webm,mp4,ogg}
  - web_call_admin._recording_url  disk-check → admin serve URL
"""

from __future__ import annotations

import os

from app.api import call_recordings, web_call, web_call_admin


# ---------------------------------------------------------------- _rec_ext
def test_rec_ext_magic_bytes():
    assert web_call._rec_ext(b"\x1aE\xdf\xa3rest") == "webm"  # EBML/webm
    assert web_call._rec_ext(b"....ftypisom") == "mp4"  # ISO-BMFF
    assert web_call._rec_ext(b"OggS....") == "ogg"
    assert web_call._rec_ext(b"garbage") == "webm"  # unknown → webm


# ------------------------------------------------------ _normalize_session_id_safe
def test_normalize_session_id_safe():
    good = "abc12345-XYZ_67"
    assert web_call._normalize_session_id_safe(good) == good
    assert web_call._normalize_session_id_safe("short") is None  # < 8
    assert web_call._normalize_session_id_safe("bad space!!") is None
    assert web_call._normalize_session_id_safe(None) is None


# ---------------------------------------------------------------- _turn_meta
def test_turn_meta_uses_first_chunk_for_latency():
    t_recv = 100.0
    timing = {"stt_ms": 1100, "llm_ms": 2800, "tts_ms": 1300, "first_chunk_at": 104.5}
    meta = web_call._turn_meta(timing, t_recv, "bijli ka bill zyada aata hai")
    # perceived latency = first audio chunk send (104.5) - recv (100.0) = 4500ms
    assert meta["latency_ms"] == 4500
    assert meta["stt_ms"] == 1100 and meta["llm_ms"] == 2800 and meta["tts_ms"] == 1300
    assert meta["heard"] == "bijli ka bill zyada aata hai"


def test_turn_meta_handles_missing_first_chunk():
    # No audio sent (first_chunk_at absent) → latency falls back to elapsed-now,
    # must still be a non-negative int and never raise.
    meta = web_call._turn_meta({"llm_ms": 500}, 0.0, "x")
    assert isinstance(meta["latency_ms"], int) and meta["latency_ms"] >= 0
    assert meta["stt_ms"] is None  # was an audio-less (typed) turn


# ---------------------------------------------------------------- _log_turn meta
def test_log_turn_persists_timing_meta():
    session: dict = {}
    web_call._log_turn(
        session,
        "assistant",
        "Ji bilkul, bataiye.",
        meta={
            "heard": "haan boliye",
            "stt_ms": 900,
            "llm_ms": 2200,
            "tts_ms": 1000,
            "latency_ms": 4100,
        },
    )
    turn = session["turns"][-1]
    assert turn["role"] == "assistant"
    assert turn["heard"] == "haan boliye"
    assert turn["latency_ms"] == 4100 and turn["llm_ms"] == 2200
    # user turns (no meta) stay lean — no timing keys leak in
    web_call._log_turn(session, "user", "haan boliye")
    assert "latency_ms" not in session["turns"][-1]


# ------------------------------------------------- call_recordings serve regex
def test_serve_regex_accepts_webcall_and_phone():
    R = call_recordings._SERVE_RE
    assert R.match("webcall_abc12345.webm")
    assert R.match("webcall_abc12345.mp4")
    assert R.match("webcall_abc12345.ogg")
    assert R.match("call_cd512ca0-1.wav")  # phone WAV still allowed
    assert R.match("call_cd512ca0_bot.wav")  # legacy split
    assert not R.match("../etc/passwd")  # traversal blocked
    assert not R.match("webcall_abc12345.exe")  # arbitrary ext blocked


def test_media_by_ext_maps_containers():
    assert call_recordings._MEDIA_BY_EXT["webm"] == "audio/webm"
    assert call_recordings._MEDIA_BY_EXT["mp4"] == "audio/mp4"
    assert call_recordings._MEDIA_BY_EXT["wav"] == "audio/wav"


# ------------------------------------------------- web_call_admin _recording_url
def test_recording_url_none_when_absent():
    assert web_call_admin._recording_url("doesnotexist1234", "2026-06-28T10:00:00+00:00") is None
    assert web_call_admin._recording_url(None, "2026-06-28T10:00:00+00:00") is None
    assert web_call_admin._recording_url("abc12345", "bad-date") is None


def test_recording_url_found_when_file_exists(tmp_path, monkeypatch):
    sid = "sess12345abc"
    day = "2026-06-28"
    rec_dir = tmp_path / "data" / "call_recordings" / day
    rec_dir.mkdir(parents=True)
    (rec_dir / f"webcall_{sid}.webm").write_bytes(b"\x1aE\xdf\xa3audio-bytes-here")
    monkeypatch.chdir(tmp_path)
    url = web_call_admin._recording_url(sid, f"{day}T09:30:00+00:00")
    assert url == f"/api/admin/call-recordings/{day}/webcall_{sid}.webm"
