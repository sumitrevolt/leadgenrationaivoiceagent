#!/usr/bin/env python3
"""Live call se seekho → voice agent improve karo.

Flow:
  1. (optional) fire_calls.py se 1+ outbound Vobiz stream call
  2. transcript + recording ka wait
  3. eval_metrics + Meera trainer stats
  4. free-LLM mistake analysis → skill_library lesson
  5. self_improve record_use

Run (VPS container):
  docker exec leadgen_app python3 scripts/voice_learn_from_calls.py --call-limit 1 --platform
  docker exec leadgen_app python3 scripts/voice_learn_from_calls.py --learn-only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BASE = (
    "/app" if os.path.isdir("/app") else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _BASE)
os.chdir(_BASE)

from dotenv import load_dotenv

load_dotenv(os.path.join(_BASE, ".env"), override=True)

_TRANSCRIPTS = Path("data/call_transcripts")
_RECORDINGS = Path("data/call_recordings")


def _latest_transcript_records(limit: int = 5) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not _TRANSCRIPTS.is_dir():
        return out
    files = sorted(_TRANSCRIPTS.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for fp in files[:7]:
        try:
            for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if isinstance(rec, dict) and rec.get("messages"):
                    out.append(rec)
        except Exception:
            continue
    return out[-limit:]


def _transcript_text(rec: dict[str, Any], max_chars: int = 3500) -> str:
    lines: list[str] = []
    for m in rec.get("messages") or []:
        role = (m.get("role") or "?").upper()
        content = str(m.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)[:max_chars]


def _score_transcript(rec: dict[str, Any]) -> dict[str, Any]:
    from app.agents.eval_metrics import voice_turn_score

    msgs = rec.get("messages") or []
    vs = voice_turn_score(msgs)
    return {
        "score": vs.get("score", 0),
        "flags": vs.get("flags", {}),
        "bot_turns": vs.get("bot_turns", 0),
        "duration_s": rec.get("duration_s"),
        "user_turns": rec.get("user_turns"),
        "niche": rec.get("niche"),
        "stream_sid": rec.get("stream_sid"),
    }


async def _llm_mistake_analysis(rec: dict[str, Any], metrics: dict[str, Any]) -> str:
    tx = _transcript_text(rec)
    if len(tx) < 20:
        return "Transcript bahut chhota — koi analysis nahi."
    flags = metrics.get("flags") or {}
    prompt = (
        f"Niche: {rec.get('niche', 'general')}. Duration: {rec.get('duration_s')}s.\n"
        f"Quality score: {metrics.get('score')} flags={flags}\n\n"
        f"TRANSCRIPT:\n{tx}\n\n"
        "Upaar ke phone call me Swara (AI telecaller) ne kya GALTI ki? "
        "3 bullet Hinglish me likho: (1) kya galat bola/zyada bola (2) customer ne kya objection diya "
        "(3) agli call me EXACT kya change karna chahiye (1 line actionable). Sirf bullets, no JSON."
    )
    try:
        from app.voice_agent import free_ai

        raw, prov = await free_ai.chat(
            "Tu voice-agent QA coach ho. Sirf concise Hinglish bullets.",
            [{"role": "user", "content": prompt}],
            max_tokens=280,
            temperature=0.2,
        )
        if raw and str(raw).strip():
            return f"[{prov}] {str(raw).strip()}"
    except Exception as e:
        return f"LLM analysis skip: {e}"
    return "LLM empty response."


async def learn_from_recent(limit: int = 3) -> dict[str, Any]:
    from app.agents.staff import run_trainer
    from app.platform import skill_library

    trainer = await run_trainer()
    recs = _latest_transcript_records(limit)
    if not recs:
        return {"ok": False, "reason": "no_transcripts", "trainer": trainer}

    analyses: list[dict[str, Any]] = []
    lessons_written: list[str] = []

    for rec in recs[-limit:]:
        metrics = _score_transcript(rec)
        analysis = await _llm_mistake_analysis(rec, metrics)
        analyses.append({"metrics": metrics, "analysis": analysis[:600]})

        lesson_body = (
            f"Call {rec.get('stream_sid', '?')[:12]} niche={rec.get('niche')} "
            f"score={metrics.get('score')} | {analysis[:400]}"
        )
        lr = skill_library.record_lesson(
            topic=f"voice_{rec.get('niche', 'general')}",
            lesson=lesson_body,
            source="voice_learn",
            agent="meera",
        )
        if lr.get("ok"):
            lessons_written.append(lesson_body[:120])

        ok_call = float(metrics.get("score") or 0) >= 0.7 and (rec.get("user_turns") or 0) >= 1
        skill_library.record_use(
            "voice_live_call",
            ok=ok_call,
            detail=f"score={metrics.get('score')} turns={rec.get('user_turns')}",
            agent="swara",
        )

    try:
        from app.platform import team

        team.log_event(
            "meera",
            "voice_learn",
            f"{len(recs)} calls analysed, {len(lessons_written)} lessons saved",
            meta={"trainer": trainer, "scores": [a["metrics"].get("score") for a in analyses]},
        )
    except Exception:
        pass

    return {
        "ok": True,
        "trainer": trainer,
        "analysed": len(analyses),
        "lessons": lessons_written,
        "analyses": analyses,
    }


async def place_calls(limit: int, platform: bool) -> dict[str, Any]:
    import subprocess

    cmd = [sys.executable, os.path.join(_BASE, "scripts", "fire_calls.py"), "--limit", str(limit)]
    if platform:
        cmd.append("--platform")
    before = len(_latest_transcript_records(50))
    proc = subprocess.run(cmd, cwd=_BASE, capture_output=True, text=True, timeout=600)
    print(proc.stdout[-2000:] if proc.stdout else "")
    if proc.stderr:
        print(proc.stderr[-800:])
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "placed": limit if proc.returncode == 0 else 0,
        "transcripts_before": before,
    }


async def wait_for_new_transcript(before_count: int, timeout_s: int = 180) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        now = len(_latest_transcript_records(50))
        if now > before_count:
            return True
        await asyncio.sleep(8)
    return False


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--call-limit", type=int, default=0, help="0=skip calling")
    ap.add_argument("--platform", action="store_true", help="LeadGen AI pitch")
    ap.add_argument("--learn-only", action="store_true")
    ap.add_argument("--wait", type=int, default=150, help="seconds wait for transcript after call")
    ap.add_argument("--limit", type=int, default=3, help="transcripts to analyse")
    args = ap.parse_args()

    print("=== Voice Learn From Calls ===")
    print("at:", datetime.now(timezone.utc).isoformat())
    print("VOBIZ_CALL_RECORD:", os.environ.get("VOBIZ_CALL_RECORD", "0"))
    print("AUTO_QUALIFY_CALLS:", os.environ.get("AUTO_QUALIFY_CALLS", "0"))

    before = len(_latest_transcript_records(50))

    if not args.learn_only and args.call_limit > 0:
        print(f"\n>> Placing {args.call_limit} call(s)...")
        placed = await place_calls(args.call_limit, args.platform)
        print("place_result:", placed)
        if not placed.get("ok"):
            print("WARN: call placement failed — learn-only on existing data")
        else:
            print(f">> Waiting up to {args.wait}s for transcript...")
            got = await wait_for_new_transcript(before, args.wait)
            print("transcript_arrived:", got)
            if not got:
                print("WARN: no new transcript yet — analysing whatever exists")

    print("\n>> Learning from transcripts...")
    result = await learn_from_recent(args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))

    rec_dirs = list(_RECORDINGS.glob("*/*.wav")) if _RECORDINGS.is_dir() else []
    if rec_dirs:
        latest = sorted(rec_dirs, key=lambda p: p.stat().st_mtime, reverse=True)[:3]
        print("\nrecordings:", [str(p.relative_to(_RECORDINGS)) for p in latest])

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
