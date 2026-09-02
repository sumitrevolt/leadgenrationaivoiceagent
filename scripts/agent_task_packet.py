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
