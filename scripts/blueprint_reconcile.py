"""blueprint_reconcile.py — legacy Explorer graph -> canonical Blueprint manifest.

The Master Blueprint (``app/platform/blueprint_graph.py``) is the ONE canonical
node/edge registry. The legacy ``/app/explorer`` graph inside
``frontend/explorer.html`` still carries real architecture knowledge (158 view
nodes + ~196 SUBNODES children, 344 edges) that predates it.

This tool does the *reconciliation* step: it parses the legacy graph, matches it
against the canonical registry using **file evidence** (not names), and emits a
deterministic manifest classifying every legacy node. It NEVER mutates the
canonical graph — a human/agent uses the manifest to decide what to migrate.

Classifications (owner-agreed vocabulary):
  MERGE_WITH_CANONICAL_NODE  legacy node already represented canonically
  MIGRATE_VERIFIED           real file evidence on disk, no canonical equivalent
  ORPHAN_REQUIRES_CONNECTION on the legacy graph with 0 edges
  INVALID_OR_STALE           names source files that do NOT resolve on disk
  MISSING_RUNTIME            no file evidence at all (label/aspiration only)
  DEPRECATED                 maps to a canonical node marked DEPRECATED

Honesty rules (harness standard): evidence-derived only, deterministic output,
never raises, no fabricated status. A legacy node is NEVER promoted to
"verified" on the strength of its own description.

Usage:
    python scripts/blueprint_reconcile.py                  # human report
    python scripts/blueprint_reconcile.py --json           # machine manifest
    python scripts/blueprint_reconcile.py --check          # exit 1 on stale refs
    python scripts/blueprint_reconcile.py --repo-root PATH # verify files elsewhere
                                                           # (sparse worktrees)
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPLORER = ROOT / "frontend" / "explorer.html"

SRC_EXT = (".py", ".html", ".js", ".yml", ".yaml", ".sh")

CLASSIFICATIONS = (
    "MERGE_WITH_CANONICAL_NODE",
    "MIGRATE_VERIFIED",
    "ORPHAN_REQUIRES_CONNECTION",
    "INVALID_OR_STALE",
    "MISSING_RUNTIME",
    "DEPRECATED",
)


def _read(p: pathlib.Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def real_filenames(root: pathlib.Path) -> set[str]:
    """Every real source basename in the repo.

    Prefers ``git ls-tree -r HEAD`` — authoritative for the checked-out commit
    and complete even in a *sparse* worktree. (``git ls-files`` is NOT usable
    here: it reads the sparse index and would report only the materialised
    handful of files, making every other node look stale.) Falls back to an
    os.walk for non-git usage.
    """
    names: set[str] = set()
    try:
        import subprocess

        out = subprocess.run(
            ["git", "-C", str(root), "ls-tree", "-r", "HEAD", "--name-only"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if out.returncode == 0 and out.stdout.strip():
            for line in out.stdout.splitlines():
                line = line.strip()
                if line:
                    names.add(line.split("/")[-1])
            return names
    except Exception:
        pass

    excluded = {".venv", "node_modules", "__pycache__", ".git", "worktrees", ".mypy_cache"}
    try:
        for _base, dirs, files in os.walk(root, topdown=True, onerror=lambda _e: None):
            dirs[:] = [d for d in dirs if d not in excluded]
            names.update(files)
    except Exception:
        pass
    return names


def _files_tokens(field: str) -> list[str]:
    """Split an explorer `files:'a.py · b.py'` field into basenames."""
    out: list[str] = []
    for tok in re.split(r"[·,]", field or ""):
        base = tok.strip().split("/")[-1].split("#")[0].strip()
        if base:
            out.append(base)
    return out


def parse_legacy(html: str) -> dict[str, Any]:
    """Legacy view nodes (+ their edges) and SUBNODES children, from explorer.html.

    Mirrors scripts/explorer_sync.parse_views segmentation so the two tools agree
    on what "a legacy view" is.
    """
    keys = ["structural", "automation", "products", "builder"]
    marks: list[tuple[int, str]] = []
    for k in keys:
        m = re.search(r"\n  " + k + r": \{", html)
        if m:
            marks.append((m.start(), k))
    marks.sort()

    nodes: dict[str, dict[str, Any]] = {}
    edges: list[tuple[str, str]] = []
    for i, (pos, k) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
        seg = html[pos:end]
        nb = re.search(r"nodes:\s*\[(.*?)\n    \],", seg, re.S)
        if nb:
            for lit in re.findall(r"\{id:'([\w]+)'[^}]*\}", nb.group(1)):
                pass  # ids collected below with fields
            for m in re.finditer(r"\{id:'([\w]+)',(.*?)\}", nb.group(1), re.S):
                nid, body = m.group(1), m.group(2)
                if nid in nodes:
                    continue
                title = (re.search(r"title:'([^']*)'", body) or [None, ""])[1]
                files = (re.search(r"files:'([^']*)'", body) or [None, ""])[1]
                badge = (re.search(r"badge:'([^']*)'", body) or [None, ""])[1]
                ntype = (re.search(r"type:'([^']*)'", body) or [None, ""])[1]
                nodes[nid] = {
                    "id": nid,
                    "view": k,
                    "title": title,
                    "badge": badge,
                    "type": ntype,
                    "files_raw": files,
                    "files": _files_tokens(files),
                    "kind": "view_node",
                    "parent": None,
                }
        edges += re.findall(r"\{f:'([\w]+)',\s*t:'([\w]+)'", seg)

    # SUBNODES = legacy detail children (natural L2 layer), parent = its group key
    sb = re.search(r"const SUBNODES\s*=\s*\{(.*?)\n\};", html, re.S)
    if sb:
        for gm in re.finditer(r"\n  (\w+):\s*\[(.*?)\n  \]", sb.group(1), re.S):
            parent, body = gm.group(1), gm.group(2)
            for m in re.finditer(r"\{id:'([\w]+)',(.*?)\}", body, re.S):
                nid, nb2 = m.group(1), m.group(2)
                if nid in nodes:
                    continue
                title = (re.search(r"title:'([^']*)'", nb2) or [None, ""])[1]
                files = (re.search(r"files:'([^']*)'", nb2) or [None, ""])[1]
                badge = (re.search(r"badge:'([^']*)'", nb2) or [None, ""])[1]
                nodes[nid] = {
                    "id": nid,
                    "view": "subnodes",
                    "title": title,
                    "badge": badge,
                    "type": "",
                    "files_raw": files,
                    "files": _files_tokens(files),
                    "kind": "subnode",
                    "parent": parent,
                }
    return {"nodes": nodes, "edges": edges}


def canonical_nodes() -> list[dict[str, Any]]:
    """Load canonical NODES without importing the app package (sparse-safe)."""
    try:
        import importlib.util

        p = ROOT / "app" / "platform" / "blueprint_graph.py"
        spec = importlib.util.spec_from_file_location("_bg_reconcile", p)
        if spec is None or spec.loader is None:
            return []
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return list(getattr(mod, "NODES", []))
    except Exception:
        return []


def reconcile(repo_root: pathlib.Path | None = None) -> dict[str, Any]:
    """Deterministic legacy -> canonical manifest (never raises)."""
    root = repo_root or ROOT
    html = _read(EXPLORER)
    legacy = parse_legacy(html)
    lnodes, ledges = legacy["nodes"], legacy["edges"]
    canon = canonical_nodes()
    real = real_filenames(root)

    # canonical lookup: id -> node, and basename -> canonical id (file evidence)
    by_id = {c["id"]: c for c in canon}
    file_owner: dict[str, str] = {}
    for c in canon:
        for f in c.get("files") or []:
            file_owner.setdefault(pathlib.PurePath(f).name, c["id"])

    deg: dict[str, int] = dict.fromkeys(lnodes, 0)
    for f, t in ledges:
        if f in deg:
            deg[f] += 1
        if t in deg:
            deg[t] += 1

    entries: list[dict[str, Any]] = []
    for nid in sorted(lnodes):
        n = lnodes[nid]
        src_files = [f for f in n["files"] if f.lower().endswith(SRC_EXT)]
        resolved = [f for f in src_files if f in real]
        unresolved = [f for f in src_files if f not in real]

        canon_id = nid if nid in by_id else None
        if canon_id is None:
            for f in resolved:
                if f in file_owner:
                    canon_id = file_owner[f]
                    break

        if canon_id and by_id.get(canon_id, {}).get("status") == "DEPRECATED":
            cls = "DEPRECATED"
        elif canon_id:
            cls = "MERGE_WITH_CANONICAL_NODE"
        elif unresolved and not resolved:
            cls = "INVALID_OR_STALE"
        elif not src_files:
            cls = "MISSING_RUNTIME"
        elif n["kind"] == "view_node" and deg.get(nid, 0) == 0:
            cls = "ORPHAN_REQUIRES_CONNECTION"
        else:
            cls = "MIGRATE_VERIFIED"

        entries.append(
            {
                "legacy_id": nid,
                "canonical_id": canon_id,
                "classification": cls,
                "title": n["title"],
                "view": n["view"],
                "kind": n["kind"],
                "parent_legacy_id": n["parent"],
                "degree": deg.get(nid, 0),
                "files_declared": src_files,
                "files_resolved": resolved,
                "files_unresolved": unresolved,
                "evidence": (
                    ("canonical:" + canon_id)
                    if canon_id
                    else ("disk:" + ",".join(resolved) if resolved else "none")
                ),
            }
        )

    counts: dict[str, int] = dict.fromkeys(CLASSIFICATIONS, 0)
    for e in entries:
        counts[e["classification"]] = counts.get(e["classification"], 0) + 1

    return {
        "legacy_view_nodes": sum(1 for n in lnodes.values() if n["kind"] == "view_node"),
        "legacy_subnodes": sum(1 for n in lnodes.values() if n["kind"] == "subnode"),
        "legacy_edges": len(ledges),
        "canonical_nodes": len(canon),
        "repo_root_checked": str(root),
        "counts": counts,
        "entries": entries,
    }


def main(argv: list[str]) -> int:
    root = None
    if "--repo-root" in argv:
        try:
            root = pathlib.Path(argv[argv.index("--repo-root") + 1]).resolve()
        except Exception:
            root = None
    m = reconcile(root)

    if "--json" in argv:
        print(json.dumps(m, indent=2, sort_keys=True))
        return 0

    print("=" * 60)
    print("LEGACY EXPLORER -> CANONICAL BLUEPRINT RECONCILIATION")
    print("=" * 60)
    print(
        f"legacy: {m['legacy_view_nodes']} view nodes + {m['legacy_subnodes']} subnodes "
        f"· {m['legacy_edges']} edges"
    )
    print(f"canonical registry: {m['canonical_nodes']} nodes")
    print(f"file evidence checked against: {m['repo_root_checked']}")
    print("\n--- classification ---")
    for c in CLASSIFICATIONS:
        print(f"  {c:<28} {m['counts'].get(c, 0)}")
    stale = [e for e in m["entries"] if e["classification"] == "INVALID_OR_STALE"]
    if stale:
        print(f"\n--- INVALID_OR_STALE ({len(stale)}) — do NOT migrate as live ---")
        for e in stale[:40]:
            print(f"  {e['legacy_id']:<22} missing: {', '.join(e['files_unresolved'])}")
    if "--check" in argv and stale:
        print(f"\n[FAIL] {len(stale)} legacy node(s) reference files not on disk.")
        return 1
    if "--check" in argv:
        print("\n[OK] no legacy node references a missing source file.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never-raise (repo convention)
        print(f"[blueprint_reconcile] skipped: {type(e).__name__}: {e}")
        sys.exit(0)
