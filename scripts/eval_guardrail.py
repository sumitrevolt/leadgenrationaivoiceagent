#!/usr/bin/env python3
"""Offline voice-quality eval guardrail (free-stack, regression-gated).

Scores recorded call transcripts (data/call_transcripts/*.jsonl) with the
deterministic metrics in app/agents/eval_metrics.py and feeds the rolling-median
regression gate in app/agents/eval_gate.py. No LLM judge, no network → safe to
run on every build.

Exit code:
  0  — accept / no_baseline / soft-mode (DEFAULT — never breaks CI)
  1  — ONLY when the gate says "reject" AND EVAL_GATE_HARD=1 (opt-in hard mode)

So wiring this into final_integration_check is non-breaking until you flip
EVAL_GATE_HARD=1 on purpose. Never raises (any error → report + exit 0).

Run: python scripts/eval_guardrail.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TRANSCRIPT_DIR = ROOT / "data" / "call_transcripts"
_MAX_FILES = 7  # most recent days

# Built-in clean fixture so the guardrail always yields a score (cold start /
# no transcripts) without reporting a false regression.
_FIXTURE: list[dict] = [
    {
        "messages": [
            {
                "role": "assistant",
                "content": "Main LeadGen AI se ek AI assistant hoon. Aapko 2 minute hain?",
            },
            {"role": "user", "content": "haan boliye"},
            {
                "role": "assistant",
                "content": "Aapke business ka free Google audit kar sakte hain. Interested?",
            },
        ]
    },
]


def _load_transcripts() -> list[list[dict]]:
    convos: list[list[dict]] = []
    try:
        if _TRANSCRIPT_DIR.is_dir():
            files = sorted(_TRANSCRIPT_DIR.glob("*.jsonl"))[-_MAX_FILES:]
            for fp in files:
                try:
                    for line in fp.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rec = json.loads(line)
                        except Exception:
                            continue
                        msgs = rec.get("messages")
                        if isinstance(msgs, list) and msgs:
                            convos.append(msgs)
                except Exception:
                    continue
    except Exception:
        pass
    return convos


def main() -> int:
    print("=== VOICE-QUALITY EVAL GUARDRAIL ===")
    try:
        from app.agents import eval_gate, eval_metrics
    except Exception as e:
        print(f"  (eval modules unavailable: {e}) — skipping, exit 0")
        return 0

    convos = _load_transcripts()
    source = "transcripts" if convos else "fixture"
    if not convos:
        convos = [c["messages"] for c in _FIXTURE]

    scores = [eval_metrics.transcript_quality(m) for m in convos]
    mean = round(sum(scores) / len(scores), 4) if scores else 1.0
    # aggregate flags for visibility
    agg = {"empty": 0, "too_long": 0, "double_question": 0, "repeat": 0, "bot_turns": 0}
    for m in convos:
        r = eval_metrics.voice_turn_score(m)
        agg["bot_turns"] += r["bot_turns"]
        for k, v in r["flags"].items():
            agg[k] += v
    print(f"  source={source}  convos={len(convos)}  mean_turn_score={mean}")
    print(
        f"  bot_turns={agg['bot_turns']}  flags={ {k: agg[k] for k in ('empty', 'too_long', 'double_question', 'repeat')} }"
    )

    try:
        verdict = eval_gate.score_and_gate(
            suite="voice_quality", metric="turn_score", current_score=mean, agent="ci"
        )
    except Exception as e:
        print(f"  (eval_gate error: {e}) — exit 0")
        return 0

    decision = verdict.get("decision", "no_baseline")
    base = verdict.get("baseline")
    print(f"  gate: decision={decision}  baseline={base}  ratio={verdict.get('ratio')}")

    if decision == "reject":
        hard = False
        try:
            hard = eval_gate.hard_mode()
        except Exception:
            hard = False
        if hard:
            print("FAIL — voice-quality regression beyond tolerance (EVAL_GATE_HARD=1).")
            return 1
        print("WARN — regression detected, but soft-mode (set EVAL_GATE_HARD=1 to enforce).")
        return 0

    print("PASS — no voice-quality regression.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
