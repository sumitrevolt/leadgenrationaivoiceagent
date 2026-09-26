#!/usr/bin/env python3
"""agent_task_packet.py — generate a BOUNDED task packet for a worker agent.

Token-saving rule: never re-explain the whole project to a sub-agent. This emits a
small packet (objective, exact files, relevant context nodes, constraints pulled
from the project's invariants/landmines, and an acceptance-test hint) so a cheap
worker model can execute without re-loading the repo.

  python scripts/agent_task_packet.py --objective "add schema_version to office snapshot" \
      --files app/platform/office_hq.py --query "office snapshot schema" --test tests/test_office_contract.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_context as pc  # noqa: E402
import query_project_context as q  # noqa: E402


def build_packet(objective: str, files: list[str], query: str, test: str | None) -> str:
    store = pc.load_store(pc.DEFAULT_STORE) or {"nodes": [], "edges": [], "meta": {}}
    head = store.get("meta", {}).get("head_sha", pc.git_head())[:8]
    ctx = q.query(store, query or objective, k=8)
    invariants = [n for n in store.get("nodes", []) if n["type"] in ("Invariant", "Landmine")][:6]

    out = [
        "# AGENT TASK PACKET",
        f"(HEAD {head} — do NOT re-scan the repo; this is your bounded context)",
        "",
        f"## Objective\n{objective}",
        "",
        "## Exact files (read only these + their direct callers)",
    ]
    out += [f"- {f}" for f in files] or ["- (discover via query below)"]
    out += ["", "## Relevant project context"]
    out += [f"- [{n['type']}] {n['label']} «{n['source']}» — {n['summary']}" for n in ctx] or [
        "- (none matched)"
    ]
    out += ["", "## Hard constraints (never violate)"]
    out += [f"- {n['summary']}" for n in invariants] or ["- Follow CLAUDE.md §5 invariants."]
    out += [
        "",
        "## Mandatory execution protocol",
        "- Use the existing canonical ledger/orchestrator only: claim/lease/fencing-token, heartbeat, idempotency, evidence, retry/DLQ. Never create a second task DB or control plane.",
        "- For substantial reasoning work, use the canonical TypeSafe integration with real secure API calls at distinct stages: plan/route, intermediate QA or revision, and final/outcome validation when applicable.",
        "- TypeSafe calls must be stage-specific, not repeated identical-input calls. Record only redacted decision metadata (stage/source/reason/consumed_calls/latency/action); never print, commit, or paste API keys.",
        "- A transport/provider failure is probe-unsuccessful, not INVALID. Never fabricate a TypeSafe call or mark MOCK/CACHED/SKIPPED as REAL.",
        "- After every result, persist evidence and assign or state the next concrete bounded task; do not stop at a status report.",
        "",
        "## Acceptance test",
        (
            f"- {test}"
            if test
            else "- Add/extend a targeted pytest; changed behaviour needs a new assertion."
        ),
        "",
        "## Definition of done",
        "- targeted pytest green + scripts/prod_check.py PASS + scripts/check_secrets.py clean.",
        "- additive over rewrite; copy neighbouring convention; no duplicate routes.",
        "- TypeSafe stage evidence and canonical task-lifecycle evidence are present when the task is substantial.",
    ]
    return "\n".join(out)


def main(argv=None) -> int:
    pc.force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--objective", required=True)
    ap.add_argument("--files", default="", help="comma-separated exact files")
    ap.add_argument("--query", default="", help="context query (defaults to objective)")
    ap.add_argument("--test", default=None)
    args = ap.parse_args(argv)
    files = [f.strip() for f in args.files.split(",") if f.strip()]
    print(build_packet(args.objective, files, args.query, args.test))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
