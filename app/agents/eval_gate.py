"""eval_gate.py — close the self-improve loop with DeepEval as reward signal.

The 2026-06-16 billionaire-scale audit named this as the #1 advanced-automation
gap (§G.1): `self_improve` and `code_upgrader` mutate behaviour every cycle,
but nothing automatically scores whether the change *helped*. DeepEval is wired
(evals/test_rag_quality.py) but it's advisory CI — open-loop. This module is
the missing feedback edge.

Two concrete additions:

1. **Baseline-relative regression detection.** The static 0.6 threshold in the
   existing DeepEval suite catches catastrophic breaks. What it misses is slow
   quality drift — a series of changes each barely passing 0.6 while the
   underlying score creeps from 0.85 -> 0.62. This module records every score
   into `data/eval_history.jsonl`, computes a rolling baseline (median of last
   N runs excluding the current), and surfaces `gate_decision()` =
   `accept | reject | no_baseline` based on `current / baseline >= tolerance`.

2. **Reward signal for autonomous agents.** When `self_improve._execute()` or
   `code_upgrader` produces an artifact, the agent calls `score_and_gate()`
   with the metric value from a fresh eval run. The decision is logged into
   the agent's outcome record so the next iteration can prefer (or roll back)
   accordingly. Activated by `EVAL_GATE=1`; hardened to actually BLOCK
   regression actions by `EVAL_GATE_HARD=1` (both OFF default = pure logging).

Storage: a single jsonl file `data/eval_history.jsonl`. One line per
(suite, metric, score, decision, agent, ts) — same project-wide pattern as
llm_metrics, consent_ledger, lead_usage. No DB dependency, no Redis required,
survives container restart.

Project ethos: INERT when EVAL_GATE unset (zero behaviour change); never
raises on storage error (writes are best-effort).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from statistics import median
from typing import Any, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Storage
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_HISTORY_PATH = _DATA_DIR / "eval_history.jsonl"

# Flags (env-gated; default OFF preserves today's open-loop behaviour)
_ENABLED_FLAG = "EVAL_GATE"
_HARD_FLAG = "EVAL_GATE_HARD"

# Defaults
_DEFAULT_TOLERANCE = 0.95  # current must be >= 95% of baseline
_DEFAULT_BASELINE_WINDOW = 20  # last 20 runs feed the baseline median
_MIN_HISTORY_FOR_BASELINE = 5  # need at least 5 prior runs before gating


# --------------------------------------------------------------------------- #
# Flag helpers
# --------------------------------------------------------------------------- #
def enabled() -> bool:
    """Master gate. OFF (default) = pure pass-through; no recording, no decisions."""
    return os.environ.get(_ENABLED_FLAG, "0").strip().lower() in ("1", "true", "yes")


def hard_mode() -> bool:
    """When true, `gate_decision()` returning 'reject' should cause callers to
    actually block (e.g. raise / roll back). When false, decision is logged
    only — observability without enforcement (recommended starting state)."""
    return os.environ.get(_HARD_FLAG, "0").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _ensure_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def record_score(
    suite: str,
    metric: str,
    score: float,
    *,
    agent: str = "ci",
    artifact: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Append a single (suite, metric, score) sample. Best-effort, never raises.

    `agent`: who produced this — "ci" for CI eval runs, "self_improve",
        "code_upgrader", or any custom name from a closed-loop call site.
    `artifact`: optional opaque ID linking back to the artifact whose change
        produced this score (e.g. a self-improve task ID or patch hash).
    """
    if not enabled():
        return
    _ensure_dir()
    rec = {
        "ts": int(time.time()),
        "suite": str(suite),
        "metric": str(metric),
        "score": float(score),
        "agent": str(agent),
    }
    if artifact:
        rec["artifact"] = str(artifact)
    if extra:
        # Keep it small/JSON-safe; bad values silently dropped.
        try:
            json.dumps(extra)
            rec["extra"] = extra
        except Exception:
            pass
    try:
        with _HISTORY_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("eval_gate record_score swallowed: %s", exc)


def _read_history(limit: int = 2000) -> list[dict[str, Any]]:
    """Tail-read recent eval history. Storage error -> []."""
    if not _HISTORY_PATH.exists():
        return []
    try:
        lines = _HISTORY_PATH.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    # tail to `limit` — eval history files stay small (10s/day) so simple slice
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def recent_scores(
    suite: str,
    metric: str,
    *,
    n: int = _DEFAULT_BASELINE_WINDOW,
    exclude_last: int = 0,
) -> list[float]:
    """Return up to `n` most-recent score values for (suite, metric), oldest first.

    `exclude_last` lets baseline calc skip the current run (the one being
    judged) so it can't bootstrap-pollute its own baseline.
    """
    rows = [
        r
        for r in _read_history(limit=max(n * 4, 200))
        if r.get("suite") == suite
        and r.get("metric") == metric
        and isinstance(r.get("score"), (int, float))
    ]
    if exclude_last and exclude_last > 0:
        rows = rows[:-exclude_last]
    rows = rows[-n:]
    return [float(r["score"]) for r in rows]


def baseline(
    suite: str,
    metric: str,
    *,
    window: int = _DEFAULT_BASELINE_WINDOW,
    exclude_last: int = 0,
) -> float | None:
    """Median score across the recent window. None if too few samples.

    Median (not mean) so a single anomalous spike doesn't move the bar.
    """
    samples = recent_scores(suite, metric, n=window, exclude_last=exclude_last)
    if len(samples) < _MIN_HISTORY_FOR_BASELINE:
        return None
    return float(median(samples))


# --------------------------------------------------------------------------- #
# Decisions
# --------------------------------------------------------------------------- #
def gate_decision(
    suite: str,
    metric: str,
    current_score: float,
    *,
    tolerance: float = _DEFAULT_TOLERANCE,
    window: int = _DEFAULT_BASELINE_WINDOW,
) -> dict[str, Any]:
    """Compare `current_score` to historical baseline; return decision.

    Outcomes:
      `no_baseline` — not enough history yet (cold start). Caller should
          treat as accept (you can't gate without a baseline).
      `accept`      — current >= baseline * tolerance. Change is non-regressive.
      `reject`      — current <  baseline * tolerance. Regression beyond
          tolerance — caller should roll back / not apply (in hard mode) or
          log + flag (in observability mode).

    The current run is NOT yet in history when this is called — pass
    `exclude_last=0` so the baseline reflects only prior runs.
    """
    base = baseline(suite, metric, window=window, exclude_last=0)
    if base is None:
        return {
            "decision": "no_baseline",
            "current": float(current_score),
            "baseline": None,
            "ratio": None,
            "tolerance": tolerance,
            "samples": len(recent_scores(suite, metric, n=window)),
        }
    ratio = float(current_score) / base if base else 0.0
    decision = "accept" if ratio >= tolerance else "reject"
    return {
        "decision": decision,
        "current": float(current_score),
        "baseline": base,
        "ratio": ratio,
        "tolerance": tolerance,
        "samples": len(recent_scores(suite, metric, n=window)),
    }


def score_and_gate(
    suite: str,
    metric: str,
    current_score: float,
    *,
    agent: str = "ci",
    artifact: str | None = None,
    tolerance: float = _DEFAULT_TOLERANCE,
    window: int = _DEFAULT_BASELINE_WINDOW,
) -> dict[str, Any]:
    """Convenience: compute decision THEN record. Returns the same dict as
    `gate_decision`, with the decision string also persisted on the history row.

    Call this from self_improve._execute() / code_upgrader once per artifact:

        from app.agents import eval_gate
        verdict = eval_gate.score_and_gate(
            suite="rag_quality", metric="faithfulness",
            current_score=fresh_eval_score,
            agent="self_improve", artifact=task_id,
        )
        if verdict["decision"] == "reject" and eval_gate.hard_mode():
            rollback(task_id)
    """
    verdict = gate_decision(
        suite,
        metric,
        current_score,
        tolerance=tolerance,
        window=window,
    )
    record_score(
        suite,
        metric,
        current_score,
        agent=agent,
        artifact=artifact,
        extra={"decision": verdict["decision"], "ratio": verdict["ratio"]},
    )
    # G.1: burst-of-rejects alert (best-effort — INERT when OPS_ALERTS unset).
    try:
        from app.platform import ops_alerts

        ops_alerts.maybe_alert_eval_reject(suite, metric, verdict)
    except Exception as exc:
        logger.debug("eval_gate alert hook swallowed: %s", exc)
    return verdict


def summary(window: int = _DEFAULT_BASELINE_WINDOW) -> dict[str, Any]:
    """Compact summary for /app/automation dashboard. Cheap (<5ms for normal sizes)."""
    rows = _read_history(limit=2000)
    if not rows:
        return {
            "enabled": enabled(),
            "hard_mode": hard_mode(),
            "total_records": 0,
            "suites": {},
            "recent_decisions": {"accept": 0, "reject": 0, "no_baseline": 0},
        }
    # Group by (suite, metric)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        k = (str(r.get("suite", "?")), str(r.get("metric", "?")))
        by_key.setdefault(k, []).append(r)

    suites: dict[str, Any] = {}
    rec_counts = {"accept": 0, "reject": 0, "no_baseline": 0}
    for (suite, metric), items in by_key.items():
        items = items[-window:]
        scores = [float(i["score"]) for i in items if isinstance(i.get("score"), (int, float))]
        med = float(median(scores)) if scores else None
        latest = items[-1] if items else {}
        ext = latest.get("extra") if isinstance(latest.get("extra"), dict) else {}
        for k in rec_counts:
            rec_counts[k] += sum(
                1
                for i in items
                if isinstance(i.get("extra"), dict) and i["extra"].get("decision") == k
            )
        suites.setdefault(suite, {})[metric] = {
            "samples": len(items),
            "baseline_median": med,
            "latest_score": latest.get("score"),
            "latest_decision": (ext or {}).get("decision"),
            "latest_agent": latest.get("agent"),
            "latest_ts": latest.get("ts"),
        }
    return {
        "enabled": enabled(),
        "hard_mode": hard_mode(),
        "total_records": len(rows),
        "suites": suites,
        "recent_decisions": rec_counts,
    }


def reset_baseline(suite: str, metric: str) -> dict[str, Any]:
    """L.4: clear all history rows for one (suite, metric) combo. Useful when
    a baseline drifted bad (e.g. a model rollback invalidated prior scores)
    and the operator wants a clean cold-start. Returns counts removed +
    remaining so a dashboard shows the operation took.

    Rewrites the entire jsonl file (atomic temp + rename) so a half-written
    state isn't possible. Best-effort: any IO error leaves the file as-is
    and returns {"ok": False}.
    """
    if not _HISTORY_PATH.exists():
        return {"ok": True, "removed": 0, "remaining": 0, "note": "no history yet"}
    try:
        all_rows = _read_history(limit=10**9)  # full file
        keep = [r for r in all_rows if not (r.get("suite") == suite and r.get("metric") == metric)]
        removed = len(all_rows) - len(keep)
        tmp = _HISTORY_PATH.with_suffix(".jsonl.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for r in keep:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(_HISTORY_PATH)
        return {
            "ok": True,
            "removed": removed,
            "remaining": len(keep),
            "suite": suite,
            "metric": metric,
        }
    except Exception as exc:
        logger.error("eval_gate reset_baseline failed: %s", exc)
        return {"ok": False, "error": str(exc)[:120]}


__all__ = [
    "enabled",
    "hard_mode",
    "record_score",
    "recent_scores",
    "baseline",
    "gate_decision",
    "score_and_gate",
    "summary",
    "reset_baseline",
]
