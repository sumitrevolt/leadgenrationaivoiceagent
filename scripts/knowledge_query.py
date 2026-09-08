#!/usr/bin/env python3
"""LeadGen Knowledge Retrieval — Phase 5 of the Agentic Knowledge OS upgrade.

Turns a symptom/task into a minimal context bundle:
    query -> Owner Truth -> playbook -> runbook -> incidents -> evidence

Usage:
    python scripts/knowledge_query.py "Calls are failing with Busy Line" [--json]
    python scripts/knowledge_query.py --list

Design:
- metadata filters first (domain tags), then keyword scoring over registries.
- Returns ONLY relevant context (minimal tokens); never the whole KB.
- fail-open: if no match, returns suggestions rather than fabricating.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPS = ROOT / "ops"


# ---------------------------------------------------------------- helpers
def load_yaml_safe(path: Path) -> dict:
    """Load YAML without external dep (pyyaml may not be in lock)."""
    import yaml  # pyproject has pyyaml via requirements; fallback below

    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:  # pragma: no cover
        raise SystemExit(f"YAML load failed {path}: {e}")


def load_runbooks() -> dict:
    return load_yaml_safe(OPS / "runbooks" / "registry.yaml")


def load_playbooks() -> dict:
    return load_yaml_safe(OPS / "playbooks" / "registry.yaml")


def load_truth() -> dict:
    return load_yaml_safe(OPS / "owner_truth.yaml")


def load_incidents() -> list[dict]:
    """Parse memory/incidents.md into lightweight records (dated headings)."""
    p = ROOT / "memory" / "incidents.md"
    out: list[dict] = []
    if not p.exists():
        return out
    cur = {"title": "", "date": ""}
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    for ln in lines:
        m = re.match(r"^#{1,3}\s+(.*)$", ln.strip())
        if m:
            title = m.group(1)
            d = re.search(r"(\d{4}-\d{2}-\d{2})", title)
            cur = {"title": title.strip("# ").strip(), "date": d.group(1) if d else ""}
            out.append(cur)
    return out


# ---------------------------------------------------------------- scoring
VOICE_WORDS = {"call", "voice", "swara", "sip", "busy", "busy line", "dial", "vobiz", "trunk", "latency", "stream"}
INFRA_WORDS = {"deploy", "prod", "health", "container", "redis", "db", "database", "disk", "vps", "outage", "rollback", "ci", "regression", "secret"}
SALES_WORDS = {"lead", "sale", "revenue", "whatsapp", "email", "payment", "upi", "invoice", "hot", "crm", "outreach"}
VIDEO_WORDS = {"video", "render", "publish", "asset", "branding", "social"}
AGENT_WORDS = {"agent", "stuck", "task", "duplicate", "hallucin", "sandbox", "quota", "budget", "heartbeat"}


def score_text(text: str, words: set[str]) -> int:
    t = text.lower()
    return sum(1 for w in words if w in t)


def domain_for(query: str) -> tuple[str, set[str]]:
    scores = [
        ("voice", VOICE_WORDS), ("infra", INFRA_WORDS),
        ("sales", SALES_WORDS), ("video", VIDEO_WORDS), ("agent", AGENT_WORDS),
    ]
    best = max(scores, key=lambda kv: score_text(query, kv[1]))
    return best


def match_runbooks(query: str, runbooks: list[dict]) -> list[dict]:
    scored = []
    for rb in runbooks:
        hay = " ".join([rb.get("name", ""), rb.get("trigger", ""), rb.get("detection", ""), rb.get("source", "")])
        s = score_text(query, set(hay.lower().split()))
        # keyword overlap
        q_words = set(re.findall(r"[a-z0-9]+", query.lower()))
        h_words = set(re.findall(r"[a-z0-9]+", hay.lower()))
        overlap = len(q_words & h_words)
        if s > 0 or overlap > 0:
            scored.append((s + overlap, rb))
    scored.sort(key=lambda x: -x[0])
    return [rb for _, rb in scored[:5]]


def match_playbooks(query: str, playbooks: list[dict]) -> list[dict]:
    q = query.lower()
    scored = []
    for pb in playbooks:
        hay = " ".join([pb.get("name", ""), pb.get("trigger", ""), pb.get("source", "")]).lower()
        s = sum(1 for w in q.split() if w in hay)
        if s > 0:
            scored.append((s, pb))
    scored.sort(key=lambda x: -x[0])
    return [pb for _, pb in scored[:3]]


def match_incidents(query: str, incidents: list[dict]) -> list[dict]:
    q = query.lower()
    scored = []
    for inc in incidents:
        s = sum(1 for w in q.split() if w in inc["title"].lower())
        if s > 0:
            scored.append((s, inc))
    scored.sort(key=lambda x: -x[0])
    return [pb for _, pb in scored[:3]]


# ---------------------------------------------------------------- bundle
def build_bundle(query: str, verbose: bool = False) -> dict:
    rbs = load_runbooks()
    pbs = load_playbooks()
    truth = load_truth()
    incidents = load_incidents()

    domain, _ = domain_for(query)
    runbooks = match_runbooks(query, rbs.get("runbooks", []))
    playbooks = match_playbooks(query, pbs.get("playbooks", []))
    incs = match_incidents(query, incidents)

    # Owner truth: always include the priority + relevant section
    truth_prio = truth.get("priorities", [])
    truth_blockers = truth.get("blockers", [])

    bundle = {
        "query": query,
        "domain": domain,
        "truth": {
            "priorities": truth_prio[:3],
            "blockers": truth_blockers[:5],
            "production": truth.get("production", {}),
        },
        "playbooks": playbooks,
        "runbooks": runbooks,
        "incidents": incs,
        "classifier_note": "Follow the runbook class: GREEN=autonomous, AMBER=owner approval, RED=human-only. Fail-closed: unknown/missing permission -> escalate.",
    }
    if verbose:
        bundle["_stats"] = {
            "runbooks_indexed": len(rbs.get("runbooks", [])),
            "playbooks_indexed": len(pbs.get("playbooks", [])),
            "incidents_indexed": len(incidents),
            "matched_runbooks": len(runbooks),
            "matched_playbooks": len(playbooks),
            "matched_incidents": len(incs),
        }
    return bundle


def main():
    ap = argparse.ArgumentParser(description="LeadGen Knowledge Retrieval")
    ap.add_argument("query", nargs="?", help="symptom / task description")
    ap.add_argument("--json", action="store_true", help="raw JSON output")
    ap.add_argument("--list", action="store_true", help="list indexed runbooks/playbooks")
    args = ap.parse_args()

    if args.list:
        rbs = load_runbooks()
        pbs = load_playbooks()
        print("RUNBOOKS (%d):" % len(rbs.get("runbooks", [])))
        for rb in rbs.get("runbooks", []):
            print(f"  {rb['id']} [{rb['class']}] {rb['name']}")
        print("\nPLAYBOOKS (%d):" % len(pbs.get("playbooks", [])))
        for pb in pbs.get("playbooks", []):
            print(f"  {pb['id']} [{pb.get('priority','')}] {pb['name']}")
        return

    if not args.query:
        ap.error("query required (or --list)")

    bundle = build_bundle(args.query, verbose=True)
    if args.json:
        print(json.dumps(bundle, indent=2, ensure_ascii=False))
        return

    print(f"\n=== KNOWLEDGE BUNDLE for: {bundle['query']} ===")
    print(f"Domain: {bundle['domain']}")
    print(f"Statistics: {bundle.get('_stats', {})}")
    print("\n-- RUNBOOKS --")
    if bundle["runbooks"]:
        for rb in bundle["runbooks"]:
            print(f"  {rb['id']} [{rb['class']}] {rb['name']}")
            print(f"      trigger: {rb.get('trigger')}")
            print(f"      source: {rb.get('source')}")
    else:
        print("  (no runbook match — check registry)")
    print("\n-- PLAYBOOKS --")
    for pb in bundle["playbooks"]:
        print(f"  {pb['id']} [{pb.get('priority','')}] {pb['name']} -> {pb.get('source')}")
    print("\n-- RECENT INCIDENTS --")
    if bundle["incidents"]:
        for inc in bundle["incidents"]:
            print(f"  ({inc['date'] or '?'}) {inc['title']}")
    else:
        print("  (no incident match — see memory/incidents.md)")
    print("\n-- TRUTH (priorities/blockers) --")
    for p in bundle["truth"]["priorities"]:
        print(f"  PRIO: {p}")
    for b in bundle["truth"]["blockers"]:
        print(f"  BLOCKER: {b}")
    print(f"\n{'-'*20}\n{bundle['classifier_note']}")


if __name__ == "__main__":
    main()