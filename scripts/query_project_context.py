#!/usr/bin/env python3
"""query_project_context.py — bounded keyword query over the project-context store.

Returns a compact, token-bounded set of nodes + their immediate relationships so an
agent can load ONLY task-relevant facts instead of re-reading the repo.

  python scripts/query_project_context.py "unity office authentication flow"
  python scripts/query_project_context.py "feature flags" --k 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_context as pc  # noqa: E402


def score(node: dict, terms: list[str]) -> int:
    hay = f"{node['id']} {node['label']} {node['type']} {node['summary']}".lower()
    s = 0
    for t in terms:
        if t in hay:
            s += 3 if (t in node["label"].lower() or t in node["type"].lower()) else 1
    return s


def query(store: dict, text: str, k: int = 10) -> list[dict]:
    terms = [t for t in text.lower().split() if t]
    ranked = sorted(
        ((score(n, terms), n) for n in store.get("nodes", [])),
        key=lambda x: (-x[0], x[1]["id"]),
    )
    return [n for s, n in ranked if s > 0][:k]


def edges_for(store: dict, ids: set[str]) -> list[dict]:
    return [e for e in store.get("edges", []) if e["src"] in ids or e["dst"] in ids]


def main(argv=None) -> int:
    pc.force_utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", nargs="+")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--store", default=str(pc.DEFAULT_STORE))
    args = ap.parse_args(argv)

    store = pc.load_store(Path(args.store))
    if not store:
        print(
            f"[context] no store at {args.store} — run scripts/sync_project_context.py first "
            f"(falling back to memory/INDEX.md for humans)."
        )
        return 1

    hits = query(store, " ".join(args.query), args.k)
    if not hits:
        print("[context] no matches.")
        return 0
    ids = {n["id"] for n in hits}
    print(
        f"# context query: {' '.join(args.query)}  (HEAD {store['meta']['head_sha'][:8]}, top {len(hits)})\n"
    )
    for n in hits:
        print(f"- [{n['type']}] {n['label']}  «{n['source']}»")
        if n["summary"]:
            print(f"    {n['summary']}")
    rels = edges_for(store, ids)
    if rels:
        print("\n## relationships")
        for e in rels[:30]:
            print(f"- {e['src']} --{e['rel']}--> {e['dst']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
