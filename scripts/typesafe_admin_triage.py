#!/usr/bin/env python3
"""TypeSafe admin triage — evidence-backed findings -> one traceable next action.

WHY THIS EXISTS
---------------
Owner mandate: "use TypeSafe skills and API for decision-making, work like admin
for the owner." A TypeSafe judgment that no workflow consumes is decoration, so this
tool exists to make the decision layer *operational*, not decorative:

  1. STATE   — read the canonical findings registry
               (`docs/coordination/ADMIN_FINDINGS.json`), which carries concrete
               evidence per finding. Only `status: open` items are judged.
  2. JUDGE   — ONE System One request containing independent questions that run
               in parallel (the skill's recommended shape).
  3. CONSUME — rank the findings and emit the chosen next action; write the
               decision to the canonical trace ledger (gitignored).
  4. CLOSE THE LOOP — `--record-outcome <task_id> --outcome "..."`.

FAIL-CLOSED
-----------
If TypeSafe is INERT (no key) or the request fails, this tool exits 3 and writes
NO decision. It never invents a priority.

LOCAL CREDENTIAL BOOTSTRAP (admin tooling only)
----------------------------------------------
The app (typesafe_integration) is deliberately env-only (no load_dotenv) — that is
the correct product security contract and is NOT changed here. But this *local
admin* tool should not sit fail-closing just because the operator didn't hand-export
the variable: the key already lives, gitignored, in the repo `.env` (or the key
file). `bootstrap_local_credential()` resolves it the same way a human admin would
(env -> repo .env -> gitignored key file) and publishes it into the process env so
the env-only app client works for this local run. The key VALUE is never printed,
logged, or put on argv.

This is a DURABLE COPY saved to `.workbuddy-ai/durable/` (2026-09-19). The live,
runnable location is `scripts/typesafe_admin_triage.py` — apply this file there
(`cp` over it) when the parallel-writer window settles, so the tool is both
runnable and self-sufficient.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _repo_root() -> Path:
    """Find the repo root by walking up to the dir that contains an `app/` dir.

    Robust whether this file lives at `scripts/` (canonical) or is parked in
    `.workbuddy-ai/durable/` (this durable copy).
    """
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "app").is_dir() and (parent / "requirements.lock.txt").exists():
            return parent
    # Fallback: two levels up (works from scripts/), else cwd.
    return Path(__file__).resolve().parent.parent


ROOT = _repo_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.platform.typesafe_integration import (  # noqa: E402
    Choice,
    Noul,
    Score,
    credential_state,
    fingerprint,
    get_typesafe_client,
)

DEFAULT_FINDINGS = ROOT / "docs" / "coordination" / "ADMIN_FINDINGS.json"
# NOT under `data/` on purpose: that tree belongs to the runtime-data ratchets
# (tests/test_runtime_data_a1_ratchet.py pins every data/-rooted path), so a
# trace log must not widen it.
DEFAULT_TRACE = ROOT / ".workbuddy-ai" / "typesafe_decisions.jsonl"

# --------------------------------------------------------------------------- #
# local credential bootstrap (admin tooling ONLY — never the app path)
# --------------------------------------------------------------------------- #
_KEY_ENV = "TYPESAFE_API_KEY"
_LEGACY_KEY_ENV = "TYPEsafe_API_KEY"
_KEY_FILES = (ROOT / ".env", ROOT / ".workbuddy-ai" / ".typesafe_key")


def _read_key_from_file(path: Path) -> str:
    """Extract TYPESAFE_API_KEY/TYPEsafe_API_KEY from a dotenv-ish or bare key file."""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in raw.splitlines():
        m = re.match(r'^\s*(?:export\s+)?(TYPESAFE_API_KEY|TYPEsafe_API_KEY)\s*=\s*(.+)$', line)
        if m:
            return m.group(2).strip().strip('"').strip("'")
    if path.name.endswith(".typesafe_key"):
        bare = raw.strip()
        if bare and "=" not in bare and len(bare) >= 20:
            return bare
    return ""


def bootstrap_local_credential() -> tuple[str, str]:
    """Resolve a local credential into the process env. Returns (source, fingerprint).

    Read order: process env (canonical/legacy) -> repo `.env` -> gitignored key
    file. If found and not already exported, it is exported so the env-only app
    client works for this local admin run. The value is never returned or shown.
    """
    for name in (_KEY_ENV, _LEGACY_KEY_ENV):
        val = (os.environ.get(name) or "").strip()
        if val:
            os.environ[_KEY_ENV] = val
            return f"env:{name}", fingerprint(val)
    for path in _KEY_FILES:
        if not path.exists():
            continue
        val = _read_key_from_file(path).strip()
        if val and len(val) >= 20:
            os.environ[_KEY_ENV] = val  # publish to process env; never print
            return f"local:{path.relative_to(ROOT)}", fingerprint(val)
    return "none", ""


# Severity levels are concrete situations (skill: levels must stand alone).
_REVENUE_LEVELS = [
    "no revenue or customer effect",
    "small or indirect revenue effect",
    "meaningful revenue or delivery-time effect",
    "blocks revenue, breaks a compliance gate, or stops a live customer path",
]
_ANSWER_VALUE_KEYS = ("noul", "choice", "score", "value", "probability")


# --------------------------------------------------------------------------- #
# state
# --------------------------------------------------------------------------- #
def load_findings(path: Path = DEFAULT_FINDINGS) -> list[dict[str, Any]]:
    """Open findings from the canonical registry."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        f for f in data.get("findings", []) if f.get("status") == "open" and f.get("id")
    ]


def build_state(findings: list[dict[str, Any]], registry_path: Path) -> dict[str, Any]:
    return {
        "task": "admin_findings_triage",
        "registry": str(registry_path.relative_to(ROOT)).replace("\\", "/"),
        "note": (
            "Each finding carries the evidence that was actually observed. "
            "Judge only from the supplied evidence; do not assume unlisted problems."
        ),
        "findings": {
            f["id"]: {
                "title": f.get("title", ""),
                "class": f.get("class", "unknown"),
                "evidence": f.get("evidence", ""),
                "blast_radius": f.get("blast_radius", ""),
                "owner_only_claimed": bool(f.get("owner_only", False)),
                "next_step": f.get("next_step", ""),
            }
            for f in findings
        },
    }


def build_questions(findings: list[dict[str, Any]]) -> dict[str, Any]:
    questions: dict[str, Any] = {}
    for f in findings:
        fid = f["id"]
        questions[f"f{fid}_real_risk"] = Noul(
            f"Finding {fid} ('{f.get('title', '')}') — is this a genuine risk to "
            "revenue, a live customer path, or a compliance gate, as opposed to "
            "cosmetic, speculative, or purely informational? Answer yes only if "
            "the supplied evidence shows a real consequence."
        )
    questions["revenue_impact"] = Score(
        "Across the open findings as a whole, how much revenue or customer "
        "delivery is at stake right now?",
        _REVENUE_LEVELS,
    )
    questions["next_action"] = Choice(
        "Which single finding must the admin fix FIRST to protect the most "
        "revenue, given that one fix at a time is executed and some findings "
        "need an owner-only action before any code change?",
        {
            f["id"]: f"{f['id']} — {f.get('title', '')} ({f.get('class', '')})"
            for f in findings
        },
    )
    questions["needs_owner_action"] = Noul(
        "Does the chosen next action require an owner-only irreversible step "
        "(a credential rotation, a production deploy, or a kill-switch decision) "
        "that the admin must request rather than execute alone?"
    )
    return questions


def state_hash(state: dict[str, Any], questions: dict[str, Any]) -> str:
    payload = json.dumps(
        {"state": state, "questions": sorted(questions.keys())},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# answers
# --------------------------------------------------------------------------- #
def answer_value(answer: Any) -> Any:
    if not isinstance(answer, dict):
        return answer
    for key in _ANSWER_VALUE_KEYS:
        if answer.get(key) is not None:
            return answer[key]
    return None


def answer_confidence(answer: Any) -> float | None:
    if isinstance(answer, dict) and answer.get("confidence") is not None:
        return float(answer["confidence"])
    return None


def answer_distribution(answer: Any) -> dict[str, float]:
    if isinstance(answer, dict) and isinstance(answer.get("probabilities"), dict):
        return {
            str(k): float(v)
            for k, v in answer["probabilities"].items()
            if isinstance(v, (int, float))
        }
    return {}


def score_level(answer: Any) -> tuple[int, str]:
    raw = answer_value(answer)
    if not isinstance(raw, (int, float)):
        return 0, f"unparsed:{raw!r}"
    level = max(0, min(int(round(float(raw))), len(_REVENUE_LEVELS) - 1))
    legend = answer.get("legend") if isinstance(answer, dict) else None
    desc = ""
    if isinstance(legend, dict):
        desc = str(legend.get(str(int(round(float(raw))))) or "")
    return level, desc or _REVENUE_LEVELS[level]


def interpret(
    findings: list[dict[str, Any]], answers: dict[str, Any]
) -> dict[str, Any]:
    ranking: list[dict[str, Any]] = []
    for f in findings:
        fid = f["id"]
        answer = answers.get(f"f{fid}_real_risk")
        raw_risk = answer_value(answer)
        real_risk = float(raw_risk) if isinstance(raw_risk, (int, float)) else None
        ranking.append(
            {
                "id": fid,
                "title": f.get("title", ""),
                "class": f.get("class", "unknown"),
                "real_risk": real_risk,
                "owner_only_claimed": bool(f.get("owner_only", False)),
            }
        )

    impact_answer = answers.get("revenue_impact")
    severity, impact_level = score_level(impact_answer)

    for row in ranking:
        row["priority"] = round((row["real_risk"] or 0.0) * (severity + 1), 4)
    ranking.sort(key=lambda r: (-r["priority"], r["id"]))

    action_answer = answers.get("next_action")
    chosen = answer_value(action_answer)
    if not isinstance(chosen, str) or chosen not in {f["id"] for f in findings}:
        chosen = ranking[0]["id"] if ranking else None
        chosen_source = "ranking_fallback"
    else:
        chosen_source = "model_choice"

    owner_answer = answers.get("needs_owner_action")
    owner_value = answer_value(owner_answer)
    needs_owner = bool(owner_value >= 0.5) if isinstance(owner_value, (int, float)) else False

    return {
        "next_action": chosen,
        "next_action_source": chosen_source,
        "next_action_confidence": answer_confidence(action_answer),
        "next_action_distribution": answer_distribution(action_answer),
        "revenue_impact_level": impact_level,
        "revenue_impact_probabilities": answer_distribution(impact_answer),
        "severity_weight": severity,
        "needs_owner_action": needs_owner,
        "owner_action_confidence": (
            float(owner_value) if isinstance(owner_value, (int, float)) else None
        ),
        "ranking": ranking,
    }


# --------------------------------------------------------------------------- #
# trace
# --------------------------------------------------------------------------- #
def trace_record(
    task_id: str,
    state: dict[str, Any],
    questions: dict[str, Any],
    response: Any,
    decision: dict[str, Any],
    evidence_refs: list[str],
    s_hash: str,
    requested_model: str | None = None,
    cred_source: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": "decision",
        "task_id": task_id,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "purpose": state["task"],
        "state_hash": s_hash,
        "evidence_refs": evidence_refs,
        "requested_model": requested_model,
        "credential_source": cred_source,
        "resolved_model": (
            (getattr(response, "result", None) or {}).get("model")
            or getattr(response, "model", None)
        ),
        "latency_sec": round(response.latency_sec, 3),
        "success": bool(response.success),
        "questions": [
            {"id": qid, "primitive": type(q).__name__}
            for qid, q in sorted(questions.items())
        ],
        "answers": response.answers,
        "decision": decision,
        "downstream_action": "pending_admin_execution",
        "outcome": None,
    }


def record_outcome(trace_path: Path, task_id: str, outcome: str) -> dict[str, Any]:
    rec = {
        "kind": "outcome",
        "task_id": task_id,
        "ts": datetime.now().isoformat(timespec="seconds"),
        "outcome": outcome,
    }
    append_jsonl(trace_path, rec)
    return rec


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def _render(decision: dict[str, Any], cred: dict[str, Any], resolved: str | None,
            cred_source: str) -> str:
    lines = [
        "TypeSafe admin triage",
        f"credential: {cred['state']} (fp {cred.get('fingerprint') or '-'}"
        f", source {cred_source})",
        f"model: requested={cred.get('model')} resolved={resolved or '-'}",
        f"revenue impact judged: level {decision['severity_weight']} — "
        f"{decision['revenue_impact_level']}",
        "",
        "priority ranking (real_risk x severity):",
    ]
    for row in decision["ranking"]:
        risk = "-" if row["real_risk"] is None else f"{row['real_risk']:.2f}"
        lines.append(
            f"  {row['id']:<24} risk={risk} prio={row['priority']:<6} {row['title']}"
        )
    lines += [
        "",
        f"NEXT ACTION: {decision['next_action']} "
        f"({decision['next_action_source']}"
        + (
            f", conf {decision['next_action_confidence']:.2f})"
            if decision["next_action_confidence"] is not None
            else ")"
        ),
        "choice distribution: "
        + ", ".join(
            f"{k}={v:.2f}"
            for k, v in sorted(
                decision["next_action_distribution"].items(),
                key=lambda kv: -kv[1],
            )
            if v > 0
        ),
        f"owner-only step required: {decision['needs_owner_action']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="TypeSafe admin triage (System One)")
    ap.add_argument("--findings", default=str(DEFAULT_FINDINGS))
    ap.add_argument("--trace", default=str(DEFAULT_TRACE))
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--dry-run", action="store_true", help="judge but write no trace record")
    ap.add_argument("--record-outcome", metavar="TASK_ID", default="")
    ap.add_argument("--outcome", default="", help="outcome text for --record-outcome")
    args = ap.parse_args(argv)

    trace_path = Path(args.trace)

    if args.record_outcome:
        if not args.outcome.strip():
            print("REFUSED: --record-outcome needs --outcome text", file=sys.stderr)
            return 1
        rec = record_outcome(trace_path, args.record_outcome, args.outcome.strip())
        print(f"recorded outcome for {rec['task_id']} -> {trace_path}")
        return 0

    findings_path = Path(args.findings)
    if not findings_path.exists():
        print(f"REFUSED: findings registry not found: {findings_path}", file=sys.stderr)
        return 1
    findings = load_findings(findings_path)
    if not findings:
        print("no open findings — nothing to triage")
        return 0

    state = build_state(findings, findings_path)
    questions = build_questions(findings)

    # Local admin bootstrap: make the env-only app client see the gitignored key
    # without weakening the product security contract (app stays env-only).
    cred_source, _boot_fp = bootstrap_local_credential()
    cred = credential_state()
    if not cred.get("enabled"):
        print(
            f"FAIL-CLOSED: TypeSafe credential {cred['state']} — no judgment made, "
            "no decision written. Activate a key first "
            "(scripts/typesafe_status.py --set-key-stdin).",
            file=sys.stderr,
        )
        return 3

    client = get_typesafe_client()
    response = client.system_one(state, questions)
    if not response.success:
        print(
            f"FAIL-CLOSED: TypeSafe request failed ({response.error}) — no decision written.",
            file=sys.stderr,
        )
        return 3

    decision = interpret(findings, response.answers)
    s_hash = state_hash(state, questions)
    task_id = f"tsadm-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    rec = trace_record(
        task_id=task_id,
        state=state,
        questions=questions,
        response=response,
        decision=decision,
        evidence_refs=[f"{state['registry']}#{f['id']}" for f in findings],
        s_hash=s_hash,
        requested_model=cred.get("model"),
        cred_source=cred_source,
    )
    if not args.dry_run:
        append_jsonl(trace_path, rec)

    if args.as_json:
        print(json.dumps({"trace": rec, "credential": cred, "wrote": not args.dry_run}, indent=2))
    else:
        print(_render(decision, cred, rec["resolved_model"], cred_source))
        if not args.dry_run:
            print(f"\ntrace: {trace_path} (task_id {task_id})")
            print(f"close the loop later: --record-outcome {task_id} --outcome \"...\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
