#!/usr/bin/env python3
"""eval_gate_ci.py — record DeepEval CI results into the rolling baseline.

Reads pytest's JUnit XML (each parametrized test == one metric × niche combo),
maps pass/fail to a 0-1 score, and pipes every result through
`app.agents.eval_gate.score_and_gate`. Baseline persists across CI runs via the
`data/eval_history.jsonl` file (workflow caches that path).

A summary `evals/eval_gate_summary.json` artifact captures per-metric verdicts
so a PR comment / dashboard can pick up regressions without parsing JUnit again.

Exit codes:
  0 — no regressions OR EVAL_GATE_HARD unset (advisory, default)
  1 — at least one "reject" decision AND EVAL_GATE_HARD=1 (hard-gate active)

The CI workflow keeps the step as `continue-on-error: true` for the first
weeks so a misbehaving baseline can't redden every PR — once we trust the
signal, drop the flag from the workflow.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Ensure project root is importable when running as `python evals/eval_gate_ci.py`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# The CI step must record by default; turn it on explicitly here so the script
# works whether or not the workflow exported the env var.
os.environ.setdefault("EVAL_GATE", "1")

from app.agents import eval_gate  # noqa: E402


def _parse_junit(xml_path: Path) -> list[dict]:
    """Return [{name, score, niche, metric}] for every testcase. Errors -> []."""
    if not xml_path.exists():
        return []
    try:
        tree = ET.parse(xml_path)
    except Exception as exc:
        print(f"[eval-gate-ci] failed to parse {xml_path}: {exc}", file=sys.stderr)
        return []
    out: list[dict] = []
    for tc in tree.iter("testcase"):
        name = tc.attrib.get("name", "?")
        # JUnit nests <failure> / <error> / <skipped> as children
        failed = any(child.tag in ("failure", "error") for child in tc)
        skipped = any(child.tag == "skipped" for child in tc)
        if skipped:
            continue  # skipped tests have no score signal
        score = 0.0 if failed else 1.0
        # parametrize ids look like "test_rag_answer_quality[salon]" -> niche=salon
        niche = "?"
        if "[" in name and name.endswith("]"):
            niche = name[name.index("[") + 1 : -1]
        metric = name.split("[")[0]
        out.append({"name": name, "score": score, "niche": niche, "metric": metric})
    return out


def main() -> int:
    xml = Path(os.environ.get("DEEPEVAL_JUNIT", "evals/deepeval-results.xml"))
    rows = _parse_junit(xml)
    if not rows:
        print(f"[eval-gate-ci] no testcases parsed from {xml} — nothing to gate")
        return 0

    verdicts: list[dict] = []
    for row in rows:
        v = eval_gate.score_and_gate(
            "rag_quality_ci",
            row["metric"],
            current_score=row["score"],
            agent="ci",
            artifact=row["niche"],
        )
        verdicts.append(
            {
                "metric": row["metric"],
                "niche": row["niche"],
                "score": row["score"],
                "decision": v.get("decision"),
                "baseline": v.get("baseline"),
                "ratio": v.get("ratio"),
            }
        )

    rejects = [v for v in verdicts if v["decision"] == "reject"]
    summary = {
        "total_cases": len(rows),
        "rejects": len(rejects),
        "no_baseline": sum(1 for v in verdicts if v["decision"] == "no_baseline"),
        "verdicts": verdicts,
        "hard_mode": eval_gate.hard_mode(),
    }
    out_path = Path(os.environ.get("EVAL_GATE_SUMMARY", "evals/eval_gate_summary.json"))
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[eval-gate-ci] wrote {out_path} — {len(rejects)}/{len(rows)} regressions")

    if rejects:
        print("[eval-gate-ci] REGRESSIONS:")
        for v in rejects:
            print(
                f"  - {v['metric']}[{v['niche']}]: "
                f"score={v['score']:.2f} baseline={v['baseline']:.2f} "
                f"ratio={v['ratio']:.2f}"
            )
        if eval_gate.hard_mode():
            return 1  # hard-gate active -> fail workflow step
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
