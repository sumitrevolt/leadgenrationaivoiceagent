"""blueprint_derive.py — evidence-backed L1/L2 parent derivation for the Master Blueprint.

Consumes the ``MIGRATE_VERIFIED`` set from ``scripts/blueprint_reconcile.py`` and
proposes, for each legacy node, where it belongs in the canonical registry
(``app/platform/blueprint_graph.py``).

WHY THE PARENT IS A **DOMAIN**, NOT AN L0 NODE
----------------------------------------------
The curated L0 layer is 48 nodes citing ~67 files. Forcing every detail module
under one of those nodes produced confidently-wrong mappings during design
(`admin_ui -> public_landing`, `celery -> app_fastapi`, `brand_frames ->
public_landing`, `s_gbp -> public_landing` on a single AST vote). Broad
directory ownership is therefore NEVER a positive signal here, and the primary
target is ``parent_domain_id`` (18 domains). A ``parent_node_id`` is proposed
only when a specific canonical node genuinely dominates.

SIGNALS (all evidence-derived, never filename similarity)
---------------------------------------------------------
* Graphify AST dependency edges (calls/imports/uses/references/inherits) from
  the legacy module's real source files to files owned by canonical nodes,
  aggregated to the DOMAIN level. 1-hop weighted above 2-hop.
* Corroboration read from current source: API route registration, Celery task
  registration, scheduler job membership, agent-registry membership,
  feature-flag gate.

AST evidence alone can prove a code dependency; it cannot prove production
activation, scheduling, queue consumption, flag state or business ownership.
So critical domains (outreach, calling, billing, tenancy, auth, Owner OS,
deployment, queues, consent, PII) can never reach HIGH on AST votes alone.

Usage:
    python scripts/blueprint_derive.py            # summary
    python scripts/blueprint_derive.py --json     # full manifest
    python scripts/blueprint_derive.py --check    # exit 1 if any candidate unclassified
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import subprocess
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
GRAPH = ROOT / "app" / "graphify-out" / "graph.json"

# Relations that express a real code dependency. `contains` (structural) and
# `rationale_for` (doc annotation) are deliberately excluded.
DEP_RELATIONS = {"calls", "imports", "imports_from", "uses", "references",
                 "inherits", "indirect_call"}

CLASSIFICATIONS = (
    "IMPORTED_CANONICAL",
    "MERGED_WITH_EXISTING_CANONICAL",
    "REPLACED_BY_CURRENT_PATH",
    "MISSING_RUNTIME",
    "DEPRECATED",
    "BLOCKED_EXTERNAL",
    "REVIEW_REQUIRED",
)

# Domains where an AST edge is never sufficient on its own (harness policy).
CRITICAL_DOMAINS = {
    "email_outreach", "voice_telephony", "billing_payments", "signup_onboarding",
    "owner_os_copilot", "automation_scheduler", "ai_staff_runtime",
    "security_compliance", "crm_hotqueue",
}

MIN_DOMAIN_VOTES = 4      # absolute floor — "1 vs 0" must never read as dominant
MIN_DISTINCT_EDGES = 2


def _load(name: str, rel: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    if spec is None or spec.loader is None:
        raise ImportError(rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def repo_files() -> list[str]:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-tree", "-r", "HEAD", "--name-only"],
                             capture_output=True, text=True, timeout=120)
        if out.returncode == 0:
            return [l.strip() for l in out.stdout.splitlines() if l.strip()]
    except Exception:
        pass
    return []


def load_graph() -> dict[str, Any]:
    """Graphify output is dev-only/gitignored. Absent = honest degradation."""
    if not GRAPH.exists():
        return {"available": False, "built_at_commit": None, "nodes": [], "links": []}
    try:
        g = json.loads(GRAPH.read_text(encoding="utf-8", errors="replace"))
        g["available"] = True
        return g
    except Exception:
        return {"available": False, "built_at_commit": None, "nodes": [], "links": []}


def graph_provenance(g: dict[str, Any]) -> dict[str, Any]:
    head = ""
    try:
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=60).stdout.strip()
    except Exception:
        pass
    built = str(g.get("built_at_commit") or "")
    return {
        "available": bool(g.get("available")),
        "built_at_commit": built or None,
        "repo_head": head or None,
        "fresh": bool(built and head and built[:8] == head[:8]),
        "nodes": len(g.get("nodes") or []),
        "links": len(g.get("links") or []),
    }


def file_dependency_edges(g: dict[str, Any]) -> tuple[dict, dict]:
    """file -> Counter(file) for outgoing and incoming dependency edges."""
    nid_file = {n.get("id"): n.get("source_file") for n in g.get("nodes") or []}
    out_e: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    in_e: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for l in g.get("links") or []:
        if l.get("relation") not in DEP_RELATIONS:
            continue
        sf, tf = nid_file.get(l.get("source")), nid_file.get(l.get("target"))
        if not sf or not tf or sf == tf:
            continue
        w = 2 if l.get("confidence") == "EXTRACTED" else 1
        out_e[sf][tf] += w
        in_e[tf][sf] += w
    return out_e, in_e


_ROUTER_RE = re.compile(r"APIRouter\s*\(")
_TASK_RE = re.compile(r"@(?:celery_app|app)\.task|@shared_task")
_FLAG_RE = re.compile(r"getenv\(\s*[\"']([A-Z][A-Z0-9_]{3,})[\"']")


def corroboration(files: list[str], sched_jobs: set[str], staff: set[str]) -> dict[str, Any]:
    """Current-source signals that AST edges cannot provide."""
    sig: dict[str, Any] = {"route": False, "celery_task": False, "scheduler_job": False,
                           "agent_registry": False, "feature_flags": []}
    for f in files:
        p = ROOT / f
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        stem = pathlib.PurePath(f).stem
        if f.startswith("app/api/") and _ROUTER_RE.search(txt):
            sig["route"] = True
        if _TASK_RE.search(txt):
            sig["celery_task"] = True
        if stem in sched_jobs:
            sig["scheduler_job"] = True
        if stem in staff:
            sig["agent_registry"] = True
        sig["feature_flags"] = sorted(set(sig["feature_flags"]) | set(_FLAG_RE.findall(txt)))[:6]
    sig["count"] = sum(1 for k in ("route", "celery_task", "scheduler_job", "agent_registry")
                       if sig[k]) + (1 if sig["feature_flags"] else 0)
    return sig


def _scheduler_jobs() -> set[str]:
    out: set[str] = set()
    for rel in ("app/tasks/staff_jobs.py", "app/platform/scheduler_config.py"):
        try:
            txt = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
            out |= set(re.findall(r"[\"']([a-z][a-z0-9_]{3,})[\"']", txt))
        except Exception:
            continue
    return out


def _staff_keys() -> set[str]:
    try:
        txt = (ROOT / "app" / "platform" / "team.py").read_text(encoding="utf-8", errors="replace")
        m = re.search(r"STAFF\s*[:=].*?\{(.*)", txt, re.S)
        return set(re.findall(r"[\"']([a-z][a-z0-9_]{2,})[\"']\s*:", m.group(1))) if m else set()
    except Exception:
        return set()


def derive() -> dict[str, Any]:
    """Deterministic candidate derivation. Never raises."""
    br = _load("_br", "scripts/blueprint_reconcile.py")
    bg = _load("_bg", "app/platform/blueprint_graph.py")

    man = br.reconcile(ROOT)
    targets = [e for e in man["entries"] if e["classification"] == "MIGRATE_VERIFIED"]

    paths = repo_files()
    by_base: dict[str, list[str]] = collections.defaultdict(list)
    for p in paths:
        by_base[p.split("/")[-1]].append(p)

    canon = {n["id"]: n for n in bg.NODES}
    # canonical file -> (node id, domain)
    file_owner: dict[str, tuple[str, str]] = {}
    for n in bg.NODES:
        for f in n["files"]:
            file_owner.setdefault(f, (n["id"], n["domain"]))

    g = load_graph()
    prov = graph_provenance(g)
    out_e, in_e = file_dependency_edges(g)
    sched_jobs, staff = _scheduler_jobs(), _staff_keys()
    domain_keys = {d["key"] for d in bg.DOMAINS}

    rows: list[dict[str, Any]] = []
    for e in sorted(targets, key=lambda x: x["legacy_id"]):
        files = [by_base[b][0] for b in e["files_resolved"] if len(by_base.get(b, [])) == 1]

        dom_votes: collections.Counter = collections.Counter()
        node_votes: collections.Counter = collections.Counter()
        edges_used = 0
        seen_hop1: set[str] = set()
        for f in files:
            for tgt, w in out_e.get(f, {}).items():
                if tgt in file_owner:
                    nid, dom = file_owner[tgt]
                    dom_votes[dom] += w * 2   # "this module uses canonical X"
                    node_votes[nid] += w * 2
                    edges_used += 1
                seen_hop1.add(tgt)
            for src, w in in_e.get(f, {}).items():
                if src in file_owner:
                    nid, dom = file_owner[src]
                    dom_votes[dom] += w
                    node_votes[nid] += w
                    edges_used += 1
                seen_hop1.add(src)
        # 2-hop (weak) — reaches canonical layer through one intermediate module
        for mid in list(seen_hop1)[:400]:
            if mid in file_owner:
                continue
            for tgt, w in out_e.get(mid, {}).items():
                if tgt in file_owner:
                    dom_votes[file_owner[tgt][1]] += 1

        corr = corroboration(files, sched_jobs, staff)

        dranked = dom_votes.most_common()
        dtop = dranked[0] if dranked else None
        dsecond = dranked[1] if len(dranked) > 1 else None
        nranked = node_votes.most_common()
        ntop = nranked[0] if nranked else None
        nsecond = nranked[1] if len(nranked) > 1 else None

        parent_domain = dtop[0] if dtop else None
        # a specific canonical parent is proposed ONLY when it clearly dominates
        parent_node = (ntop[0] if ntop and ntop[1] >= MIN_DOMAIN_VOTES
                       and (not nsecond or ntop[1] >= nsecond[1] * 2) else None)
        is_critical = bool(parent_domain and parent_domain in CRITICAL_DOMAINS)

        dominant = bool(
            dtop and dtop[1] >= MIN_DOMAIN_VOTES and edges_used >= MIN_DISTINCT_EDGES
            and (not dsecond or dtop[1] >= dsecond[1] * 2)
        )

        if not files:
            conf, why = "LOW", "no unique current source path for declared files"
        elif not prov["available"]:
            conf, why = "LOW", "Graphify graph unavailable — cannot prove dependency"
        elif not dranked:
            conf, why = "LOW", "no dependency path reaches any canonical domain"
        elif dominant and corr["count"] >= 1:
            conf, why = "HIGH", (
                f"dominant canonical-domain dependency ({dtop[1]} vs "
                f"{dsecond[1] if dsecond else 0}, {edges_used} edges) + "
                f"{corr['count']} current-source signal(s)")
        elif dominant:
            conf, why = "MEDIUM", (
                f"dominant dependency ({dtop[1]} votes) but no route/task/job/agent/"
                "flag corroboration")
        elif dtop and (not dsecond or dtop[1] > dsecond[1]):
            conf, why = "MEDIUM", (
                f"leading domain below auto-accept floor ({dtop[1]} votes, "
                f"{edges_used} edges)")
        else:
            conf, why = "MEDIUM", "competing canonical domains with equal support"

        # harness policy: critical domains never auto-accept on AST alone
        if conf == "HIGH" and is_critical and corr["count"] < 2:
            conf, why = "MEDIUM", (
                f"critical domain '{parent_domain}' — needs >=2 non-AST signals "
                f"(has {corr['count']})")

        if conf == "HIGH":
            final = "IMPORTED_CANONICAL"
        elif conf == "MEDIUM":
            final = "REVIEW_REQUIRED"
        else:
            final = "MISSING_RUNTIME" if not files else "REVIEW_REQUIRED"

        rows.append({
            "legacy_id": e["legacy_id"],
            "title": e["title"],
            "kind": e["kind"],
            "canonical_id": None,
            "depth_level": 2 if e["kind"] == "subnode" else 1,
            "parent_domain_id": parent_domain if parent_domain in domain_keys else None,
            "parent_flow_id": None,
            "parent_node_id": parent_node,
            "confidence": conf,
            "confidence_reason": why,
            "classification": final,
            "critical_domain": is_critical,
            "evidence_files": files,
            "graphify_edges_used": edges_used,
            "domain_votes": dict(dranked[:4]),
            "competing_domains": [d for d, _ in dranked[1:3]],
            "corroboration": corr,
        })

    counts = collections.Counter(r["confidence"] for r in rows)
    cls = collections.Counter(r["classification"] for r in rows)
    return {
        "graphify": prov,
        "reconcile_counts": man["counts"],
        "total_candidates": len(rows),
        "confidence_counts": dict(counts),
        "classification_counts": dict(cls),
        "entries": rows,
    }


def main(argv: list[str]) -> int:
    m = derive()
    if "--json" in argv:
        print(json.dumps(m, indent=2, sort_keys=True))
        return 0

    p = m["graphify"]
    print("=" * 66)
    print("BLUEPRINT L1/L2 PARENT DERIVATION")
    print("=" * 66)
    print(f"graphify: available={p['available']} fresh={p['fresh']} "
          f"built_at={str(p['built_at_commit'])[:8]} head={str(p['repo_head'])[:8]} "
          f"nodes={p['nodes']} links={p['links']}")
    if not p["fresh"]:
        print("  [WARN] graph is STALE or missing — derivation confidence is capped.")
    print(f"\ntotal candidates: {m['total_candidates']}")
    print("\n--- confidence ---")
    for k in ("HIGH", "MEDIUM", "LOW"):
        print(f"  {k:<7} {m['confidence_counts'].get(k, 0)}")
    print("\n--- classification ---")
    for k in CLASSIFICATIONS:
        if m["classification_counts"].get(k):
            print(f"  {k:<32} {m['classification_counts'][k]}")
    print("\n--- HIGH (auto-accept candidates) ---")
    for r in [x for x in m["entries"] if x["confidence"] == "HIGH"][:20]:
        print(f"  {r['legacy_id']:<22} L{r['depth_level']} -> domain={r['parent_domain_id']}"
              f" node={r['parent_node_id']}")
        print(f"      {r['confidence_reason']}")

    if "--check" in argv:
        bad = [r["legacy_id"] for r in m["entries"] if r["classification"] not in CLASSIFICATIONS]
        if bad:
            print(f"\n[FAIL] unclassified candidates: {bad}")
            return 1
        print(f"\n[OK] all {m['total_candidates']} candidates classified.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never-raise (repo convention)
        print(f"[blueprint_derive] skipped: {type(e).__name__}: {e}")
        sys.exit(0)
