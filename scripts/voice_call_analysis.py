"""Analyze historical call transcripts → quantified voice-quality findings.

Reads data/call_transcripts/*.jsonl (the same store the phone loop writes),
aggregates turn latency, repetition, opener-pitch behavior, STT garbage, and
conversation depth, then prints a findings summary.

Usage:
  python scripts/voice_call_analysis.py [transcript_dir]

Output: a findings report (stdout). No writes, no side effects.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

TRANSCRIPT_DIR = Path("data") / "call_transcripts"

_OPENERS = Counter()
_CANNED = Counter()
_TURN_MS = []
_TTS_FIRST_MS = []
_STT_MS = []
_DUR_S = []
_USER_TURNS = []
_BARGES = []
_REPLY_WORDS = []
_SLOW_TURNS = []  # (turn_ms, reply_words, first_line)
_IVR = 0
_EMPTY_CALLS = 0
_TOTAL_CALLS = 0
_TOTAL_TURNS = 0
_LONG_GAP_TURNS = 0
_LONG_GAP_PCT_MS = []
_STT_GARBAGE_TURNS = 0
_BY_DATE = defaultdict(lambda: {"calls": 0, "turns": 0, "user_turns": 0})


def _garbled(text: str) -> bool:
    """Heuristic: Devanagari replacement-glyph garbage from broken STT encode."""
    if not text:
        return False
    glyph = "\ufffd"
    if glyph in text and text.count(glyph) >= 2:
        return True
    # Zero-width + private-use junk
    if any(0xE000 <= ord(c) <= 0xF8FF for c in text):
        return True
    return False


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip().lower()


def analyze_file(path: Path) -> None:
    global _IVR, _EMPTY_CALLS, _TOTAL_CALLS, _TOTAL_TURNS, _LONG_GAP_TURNS, _STT_GARBAGE_TURNS
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as e:
        print(f"!! skip {path}: {e}")
        return
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            rec = json.loads(ln)
        except Exception:
            continue
        _TOTAL_CALLS += 1
        msgs = rec.get("messages") or []
        day = path.stem
        _BY_DATE[day]["calls"] += 1
        _BY_DATE[day]["turns"] += max(0, len(msgs) - 1)
        ut = int(rec.get("user_turns") or 0)
        _BY_DATE[day]["user_turns"] += ut
        _USER_TURNS.append(ut)
        _DUR_S.append(float(rec.get("duration_s") or 0))
        _BARGES.append(int(rec.get("barge_count") or 0))
        if ut == 0:
            _EMPTY_CALLS += 1

        # Canned message repetition
        for m in msgs:
            if m.get("role") == "assistant":
                c = _norm(m.get("content") or "")
                if c:
                    _CANNED[c] += 1
                    if len(c) < 130:
                        _OPENERS[c] += 1

        # IVR/voicemail detection
        joined = " ".join(_norm(m.get("content") or "") for m in msgs if m.get("role") == "user")
        if any(
            k in joined
            for k in (
                "press 1",
                "voicemail",
                "not available",
                "record your message",
                "forwarded to voicemail",
                "welcome to",
                "your call has been",
                "not entered any input",
                "existing ",
            )
        ):
            _IVR += 1

        # Turn metrics
        tm = rec.get("turn_metrics") or []
        for t in tm:
            _TOTAL_TURNS += 1
            turn_ms = float(t.get("turn_ms") or 0)
            tts_first = float(t.get("tts_first_ms") or 0)
            stt = float(t.get("stt_ms") or 0)
            rw = int(t.get("reply_words") or 0)
            _TURN_MS.append(turn_ms)
            _TTS_FIRST_MS.append(tts_first)
            _STT_MS.append(stt)
            _REPLY_WORDS.append(rw)
            if t.get("outcome") == "ivr":
                _IVR += 1
            # Long-gap turn: TTFA ok but full turn huge relative to words
            if turn_ms >= 3500 and rw <= 20:
                _LONG_GAP_TURNS += 1
                _LONG_GAP_PCT_MS.append(turn_ms)
                first_line = ""
                # find the assistant line this turn produced (approx: last assistant before a user)
                _SLOW_TURNS.append((turn_ms, rw, round(tts_first, 0)))


def pct(data, p):
    if not data:
        return 0.0
    s = sorted(data)
    i = min(len(s) - 1, int(p / 100 * len(s)))
    return s[i]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else TRANSCRIPT_DIR
    if not root.is_dir():
        print(f"transcript dir not found: {root}")
        return 1
    files = sorted(root.glob("*.jsonl"))
    if not files:
        print(f"no *.jsonl under {root}")
        return 1
    for f in files:
        analyze_file(f)

    print("=" * 62)
    print("VOICE CALL ANALYSIS — historical transcripts")
    print(f"  source : {root}  ({len(files)} daily files)")
    print(f"  calls  : {_TOTAL_CALLS}   assistant turns: {_TOTAL_TURNS}")
    print("=" * 62)
    print("\nCALL SHAPE")
    print(
        f"  calls with 0 user turns (voicemail/IVR/no-talk): {_EMPTY_CALLS}/{_TOTAL_CALLS} "
        f"({100 * _EMPTY_CALLS / max(1, _TOTAL_CALLS):.0f}%)"
    )
    print(f"  IVR/voicemail/announcement detected           : {_IVR}")
    print(
        f"  user_turns per call   median={pct(_USER_TURNS, 50):.0f} "
        f"p95={pct(_USER_TURNS, 95):.0f}  max={max(_USER_TURNS) if _USER_TURNS else 0}"
    )
    print(
        f"  call duration_s       median={pct(_DUR_S, 50):.0f} "
        f"p95={pct(_DUR_S, 95):.0f}  max={max(_DUR_S) if _DUR_S else 0}"
    )
    print(
        f"  barge_count/call      median={pct(_BARGES, 50):.0f} "
        f"p95={pct(_BARGES, 95):.0f}  max={max(_BARGES) if _BARGES else 0}"
    )

    print(f"\nLATENCY (turn_metrics, n={len(_TURN_MS)})")
    for name, data in (("stt_ms", _STT_MS), ("tts_first_ms", _TTS_FIRST_MS), ("turn_ms", _TURN_MS)):
        if data:
            print(
                f"  {name:<12} p50={pct(data, 50):8.1f}  p95={pct(data, 95):8.1f}  "
                f"avg={sum(data) / len(data):8.1f}  max={max(data):8.1f}"
            )
    print(
        f"  reply_words           p50={pct(_REPLY_WORDS, 50):.0f}  "
        f"p95={pct(_REPLY_WORDS, 95):.0f}  avg={sum(_REPLY_WORDS) / max(1, len(_REPLY_WORDS)):.1f}"
    )
    if _LONG_GAP_TURNS:
        print(
            f"  TURNS >=3.5s with <=20 words (dead-air suspects): {_LONG_GAP_TURNS} "
            f"(p50={pct(_LONG_GAP_PCT_MS, 50):.0f}ms p95={pct(_LONG_GAP_PCT_MS, 95):.0f}ms max={max(_LONG_GAP_PCT_MS):.0f}ms)"
        )
        print("  worst slow turns (turn_ms, words, tts_first_ms):")
        for t in sorted(_SLOW_TURNS, reverse=True)[:10]:
            print(f"    {t[0]:7.0f}ms  words={t[1]:<3} tts_first={t[2]:.0f}ms")

    print("\nTOP CANNED ASSISTANT MESSAGES (verbatim repetition across calls)")
    for msg, n in _CANNED.most_common(12):
        print(f"  x{n:<4} {msg[:110]}")

    print("\nCONVERSATION DEPTH (calls with >=2 real user turns)")
    deep = [u for u in _USER_TURNS if u >= 2]
    print(
        f"  calls reaching 2+ user turns: {len(deep)} ({100 * len(deep) / max(1, _TOTAL_CALLS):.0f}%)"
    )
    print(f"  calls reaching 4+ user turns: {sum(1 for u in _USER_TURNS if u >= 4)}")

    print("\nDAILY VOLUME")
    for d in sorted(_BY_DATE):
        v = _BY_DATE[d]
        print(f"  {d}: calls={v['calls']:<3} turns={v['turns']:<4} user_turns={v['user_turns']}")

    print(
        "\nNOTE: canned-message repetition = scripted feel; long turn_ms with short reply = dead air."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
