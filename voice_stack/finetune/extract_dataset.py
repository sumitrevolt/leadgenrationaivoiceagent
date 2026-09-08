"""
Phase 2 — CAPTURE: build the raw training manifest from our own call recordings.
============================================================================
Standalone OFFLINE tool. Does NOT import or touch the live app — it only reads
files the app already writes, and emits one JSONL manifest for the labeling step.

Reads (real app paths):
  data/call_recordings/<YYYY-MM-DD>/        phone: call_{sid}.wav  (merged, both speakers)
                                            phone: call_{sid}_caller.wav / _bot.wav (legacy split)
                                            web:   webcall_{id}.{webm,mp4,ogg,wav} (mixed mic+bot)
  data/web_call_sessions.jsonl              web transcripts: {session_id, turns:[{role,text}]}
                                            -> we attach the customer (user-role) text as a
                                               weak baseline "live_hypothesis" for cross-check.
Writes:
  data/voice_train/raw.jsonl                one row per recording:
    {call_id, audio_path, channel, track, date, ext, lang, live_hypothesis, source}

Run:
  python voice_stack/finetune/extract_dataset.py
  python voice_stack/finetune/extract_dataset.py --rec-dir data/call_recordings --out data/voice_train/raw.jsonl

NOTE on tracks:
  - phone "caller" track = customer-only audio = BEST for STT training.
  - phone "merged" + web "mixed" contain bot audio too → ideally diarize/segment per
    turn before training (that is a later refinement; captured here so nothing is lost).
  - "bot" tracks are skipped (synthetic TTS output, known text — not useful STT supervision).

CONSENT/COMPLIANCE: only consented recordings should ever be exported for training.
The app's consent ledger + 90-day retention govern what exists on disk; this tool does
not bypass them — it just lists what is already there.
"""
from __future__ import annotations

import argparse
import json
import os
import re

REC_DIR_DEFAULT = os.path.join("data", "call_recordings")
SESSIONS_JSONL = os.path.join("data", "web_call_sessions.jsonl")
OUT_DEFAULT = os.path.join("data", "voice_train", "raw.jsonl")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PHONE_RE = re.compile(r"^call_(?P<sid>[A-Za-z0-9_\-]+?)(?:_(?P<track>caller|bot))?\.wav$")
_WEB_RE = re.compile(r"^webcall_(?P<id>[A-Za-z0-9_\-]+)\.(?P<ext>webm|mp4|ogg|wav)$")


def _load_web_transcripts(path: str) -> dict[str, str]:
    """session_id -> concatenated customer (user-role) text = weak baseline hypothesis."""
    out: dict[str, str] = {}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    s = json.loads(line)
                except Exception:
                    continue
                sid = s.get("session_id") or s.get("sid") or s.get("id")
                if not sid:
                    continue
                user_text = " ".join(
                    str(t.get("text") or "").strip()
                    for t in (s.get("turns") or [])
                    if isinstance(t, dict) and str(t.get("role")) == "user"
                ).strip()
                if user_text:
                    out[str(sid)] = user_text
    except Exception:
        pass
    return out


def extract(rec_dir: str, sessions_path: str, out_path: str, lang: str = "hi") -> list[dict]:
    web_tx = _load_web_transcripts(sessions_path)
    rows: list[dict] = []
    seen: set[str] = set()

    if os.path.isdir(rec_dir):
        for date in sorted(os.listdir(rec_dir)):
            if not _DATE_RE.match(date):
                continue
            day_dir = os.path.join(rec_dir, date)
            if not os.path.isdir(day_dir):
                continue
            for fn in sorted(os.listdir(day_dir)):
                ap = os.path.join(day_dir, fn)
                if ap in seen or not os.path.isfile(ap):
                    continue
                m = _PHONE_RE.match(fn)
                if m:
                    track = m.group("track") or "merged"
                    if track == "bot":  # synthetic TTS, not STT supervision
                        continue
                    rows.append({
                        "call_id": m.group("sid"), "audio_path": ap, "channel": "phone",
                        "track": track, "date": date, "ext": "wav", "lang": lang,
                        "live_hypothesis": "", "source": "recording",
                    })
                    seen.add(ap)
                    continue
                m = _WEB_RE.match(fn)
                if m:
                    wid = m.group("id")
                    rows.append({
                        "call_id": wid, "audio_path": ap, "channel": "web",
                        "track": "mixed", "date": date, "ext": m.group("ext"), "lang": lang,
                        "live_hypothesis": web_tx.get(wid, ""), "source": "recording",
                    })
                    seen.add(ap)
                    continue

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Build raw.jsonl training manifest from call recordings.")
    ap.add_argument("--rec-dir", default=REC_DIR_DEFAULT)
    ap.add_argument("--sessions", default=SESSIONS_JSONL)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--lang", default="hi")
    args = ap.parse_args()

    rows = extract(args.rec_dir, args.sessions, args.out, args.lang)

    by_channel: dict[str, int] = {}
    by_track: dict[str, int] = {}
    with_hyp = 0
    for r in rows:
        by_channel[r["channel"]] = by_channel.get(r["channel"], 0) + 1
        by_track[r["track"]] = by_track.get(r["track"], 0) + 1
        if r.get("live_hypothesis"):
            with_hyp += 1

    print(f"[extract] {len(rows)} recordings -> {args.out}")
    print(f"  by channel : {by_channel}")
    print(f"  by track   : {by_track}")
    print(f"  with live baseline transcript (web): {with_hyp}")
    if not rows:
        print("  (no recordings found — enable VOBIZ_CALL_RECORD=1 / web-call recording first)")
    print("  next: python voice_stack/finetune/label_dataset.py")


if __name__ == "__main__":
    main()
