"""
Live-transcript evaluation (P4-3) — close the eval loop on REAL calls.
=====================================================================

`eval_metrics.transcript_quality` + `eval_suite` personas score SYNTHETIC convos.
This module scores the **live** call transcripts (`data/call_transcripts/*.jsonl`,
written by vobiz_stream / web_call) so quality drift on real calls feeds
`eval_gate` — the missing "eval_gate → live transcripts" edge.

Three layers:
  * `score_transcript(messages)` — deterministic 0..1 quality = `voice_turn_score`
    (empty/too-long/double-question/repeat) DENTED by the D-13 `qa_checks`
    findings (pushy-after-softno / talk-listen / missing-permission / literal).
  * `eval_recent_calls(n)` — score the last N live calls, mean → `eval_gate`
    (suite `live_calls`, metric `conversation_quality`); reports per-call findings
    + interruption stats. Used by the nightly Arjun guardrail.
  * `llm_judge_transcript(messages)` — OPTIONAL free-LLM judge that returns a score
    WITH a rationale (gated `LLM_JUDGE`, default OFF = cost-free).

Interruption tracking: reports the barge count per call (`barge_count`, logged by
vobiz_stream) + per-turn outcome distribution. The false-vs-missed CLASSIFICATION
needs STT-validated barge events (ties to the D-6 backchannel-allowlist arch gap)
and is flagged as `classification: "unclassified"` until that lands.

Import-safe, never raises; deterministic layers are free (no LLM/network).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _TRANSCRIPTS_DIR() -> Path:
    """Live call transcripts dir — resolved per call, never frozen at import."""
    from app.platform.runtime_recording_paths import call_transcripts_dir

    return call_transcripts_dir()


_QA_DENT = 0.5  # qa_checks findings can dent the deterministic score by up to 50%


def score_transcript(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministic live-call quality 0..1 = voice_turn_score DENTED by D-13
    qa_checks findings. Never raises (empty/odd input -> score 1.0, no findings)."""
    try:
        from app.agents.eval_metrics import voice_turn_score
        from app.voice_agent import qa_checks

        base = voice_turn_score(messages or [])
        findings = qa_checks.run_all(messages or [])
        bot_turns = max(1, int(base.get("bot_turns") or 1))
        qa_penalty = min(1.0, len(findings) / float(bot_turns))
        score = round(max(0.0, float(base.get("score", 1.0)) * (1.0 - _QA_DENT * qa_penalty)), 4)
        return {
            "score": score,
            "base_score": base.get("score"),
            "bot_turns": base.get("bot_turns"),
            "flags": base.get("flags"),
            "qa_findings": findings,
            "qa_finding_count": len(findings),
        }
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("live_eval.score_transcript error: %s", exc)
        return {"score": 1.0, "qa_findings": [], "qa_finding_count": 0}


def interruption_stats(rec: dict[str, Any]) -> dict[str, Any]:
    """Per-call interruption + turn-outcome stats from a transcript record.

    `barge_count` is logged by vobiz_stream. The false-vs-missed split needs
    STT-validated barge events (D-6), so classification stays 'unclassified'."""
    try:
        barges = int(rec.get("barge_count") or 0)
        tm = rec.get("turn_metrics")
        outcomes: dict[str, int] = {}
        turns = 0
        if isinstance(tm, list):
            turns = len(tm)
            for t in tm:
                if isinstance(t, dict):
                    oc = str(t.get("outcome") or "ok")
                    outcomes[oc] = outcomes.get(oc, 0) + 1
        return {
            "barges": barges,
            "turns": turns,
            "outcomes": outcomes,
            "classification": "unclassified",  # false-vs-missed needs STT-validated barge (D-6)
        }
    except Exception:  # pragma: no cover
        return {"barges": 0, "turns": 0, "outcomes": {}, "classification": "unclassified"}


def _load_recent_transcripts(n: int = 5, *, base_dir: Path | None = None) -> list[dict[str, Any]]:
    """Last N live call records (newest files, tail). Never raises -> []."""
    out: list[dict[str, Any]] = []
    try:
        d = base_dir or _TRANSCRIPTS_DIR()
        if not d.is_dir():
            return out
        for fp in sorted(d.glob("*.jsonl"))[-3:]:  # last few day-files is plenty
            try:
                for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict) and isinstance(rec.get("messages"), list):
                        out.append(rec)
            except Exception:
                continue
    except Exception as exc:  # pragma: no cover
        logger.debug("live_eval load error: %s", exc)
    return out[-n:] if n and len(out) > n else out


def eval_recent_calls(n: int = 5, *, base_dir: Path | None = None) -> dict[str, Any]:
    """Score the last N live calls, feed the mean to eval_gate (suite live_calls,
    metric conversation_quality), and return per-call findings + interruptions.
    Deterministic (no LLM). eval_gate recording is itself gated by EVAL_GATE."""
    recs = _load_recent_transcripts(n, base_dir=base_dir)
    per_call: list[dict[str, Any]] = []
    scores: list[float] = []
    total_findings = 0
    for rec in recs:
        s = score_transcript(rec.get("messages") or [])
        ints = interruption_stats(rec)
        scores.append(float(s["score"]))
        total_findings += int(s.get("qa_finding_count") or 0)
        per_call.append(
            {
                "call_id": rec.get("stream_sid") or rec.get("call_id") or "",
                "niche": rec.get("niche"),
                "score": s["score"],
                "qa_finding_count": s.get("qa_finding_count"),
                "qa_findings": s.get("qa_findings"),
                "interruptions": ints,
            }
        )
    mean = round(sum(scores) / len(scores), 4) if scores else 1.0
    gate: dict[str, Any] = {}
    try:
        from app.agents import eval_gate

        gate = eval_gate.score_and_gate(
            "live_calls",
            "conversation_quality",
            mean,
            agent="arjun",
            artifact=f"n={len(recs)}",
        )
    except Exception as exc:  # pragma: no cover
        logger.debug("live_eval eval_gate hook skip: %s", exc)
    return {
        "n": len(recs),
        "mean_score": mean,
        "total_qa_findings": total_findings,
        "gate": gate,
        "per_call": per_call,
    }


def _judge_enabled() -> bool:
    return (os.environ.get("LLM_JUDGE", "0") or "0").strip().lower() in ("1", "true", "yes", "on")


_JUDGE_SYSTEM = (
    "You are a strict QA judge for a Hindi/Hinglish AI telecaller (Swara). Read the "
    "transcript and rate the BOT's conversation quality 0.0-1.0 on: brevity (<=2 "
    "sentences, 1 question/turn), listening (not over-talking), respecting polite-no "
    "(stop pushing after 2 refusals), permission opener, natural Hinglish (no robotic "
    "translation), no banned/meta phrases. Reply EXACTLY two lines:\n"
    "SCORE: <0.0-1.0>\nRATIONALE: <one short sentence>"
)


async def llm_judge_transcript(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Optional free-LLM judge that returns a score WITH a rationale (P4-3).
    Gated `LLM_JUDGE` (default OFF). Never raises; returns
    {available: False} when disabled/unparseable."""
    if not _judge_enabled():
        return {"available": False, "reason": "disabled"}
    try:
        convo = "\n".join(
            f"{str(m.get('role', '?'))[:9]}: {str(m.get('content', ''))}"
            for m in (messages or [])
            if isinstance(m, dict)
        )[:4000]
        if len(convo) < 10:
            return {"available": False, "reason": "empty"}
        from app.voice_agent.free_ai import chat

        text, prov = await chat(
            _JUDGE_SYSTEM,
            [{"role": "user", "content": convo}],
            max_tokens=120,
            temperature=0.0,
            profile="bulk",
        )
        if not text:
            return {"available": False, "reason": "no_reply"}
        m = re.search(r"score\s*[:=]\s*([01](?:\.\d+)?)", text, re.IGNORECASE)
        score = max(0.0, min(1.0, float(m.group(1)))) if m else None
        rm = re.search(r"rationale\s*[:=]\s*(.+)", text, re.IGNORECASE | re.DOTALL)
        rationale = rm.group(1).strip()[:300] if rm else text.strip()[:300]
        return {"available": True, "score": score, "rationale": rationale, "provider": prov}
    except Exception as exc:  # pragma: no cover
        logger.debug("live_eval.llm_judge error: %s", exc)
        return {"available": False, "reason": "error"}


__all__ = [
    "score_transcript",
    "interruption_stats",
    "eval_recent_calls",
    "llm_judge_transcript",
]
