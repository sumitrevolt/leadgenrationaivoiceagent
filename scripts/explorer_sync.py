"""explorer_sync.py — architecture-graph drift auditor (graph <-> codebase).

frontend/explorer.html (/app/explorer) is a HAND-CURATED graph: nodes have
manual x/y coords + human descriptions. We deliberately do NOT auto-regenerate
it (that would destroy the curated layout). Instead this tool AUDITS whether the
graph still reflects the code, reports what's missing, and can emit ready-to-
paste node stubs for the gaps — so the curation stays, but drift is visible.

Usage:
    python scripts/explorer_sync.py            # report (coverage + missing lists)
    python scripts/explorer_sync.py --stubs    # + paste-ready node literals for missing engine modules
    python scripts/explorer_sync.py --check     # exit 1 if any scheduler-engine module is missing (CI gate)

Coverage sources (the architecture backbone):
  - engine modules wired into team_scheduler._run_job (the scheduled engines)
  - STAFF_JOBS scheduler jobs
  - AUTOMATION_FLAGS (info — graph tags only key flags, not all)
Never raises. Windows venv: .venv\\Scripts\\python.exe scripts/explorer_sync.py
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPLORER = ROOT / "frontend" / "explorer.html"
SCHED = ROOT / "app" / "platform" / "team_scheduler.py"
STAFF = ROOT / "app" / "tasks" / "staff_jobs.py"
GROWTH = ROOT / "app" / "api" / "growth.py"

_DROP = {
    "os",
    "json",
    "asyncio",
    "datetime",
    "timezone",
    "time",
    "random",
    "typing",
    "annotations",
    "contextlib",
    "io",
    "logging",
    "math",
    "uuid",
    "re",
    "logger",
    "settings",
    "config",
    "models",
    "base",
    "celery_app",
}


def _read(p: pathlib.Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def engine_modules() -> set[str]:
    """Modules imported inside team_scheduler (= the scheduled engines)."""
    txt = _read(SCHED)
    mods: set[str] = set()
    for m in re.finditer(r"from\s+(app[\w.]+)\s+import\s+([\w_, ]+)", txt):
        path, names = m.group(1), m.group(2)
        parts = path.split(".")
        if len(parts) >= 3:
            mods.add(parts[-1])  # from app.pkg.module import x -> module
        else:
            for n in names.split(","):  # from app.pkg import module [as alias]
                n = n.strip().split(" as ")[0].strip()
                if n and n[0].islower():
                    mods.add(n)
    return {m for m in mods if m not in _DROP and len(m) > 2}


def staff_jobs() -> list[str]:
    m = re.search(r"STAFF_JOBS\s*=\s*\((.*?)\)", _read(STAFF), re.S)
    return re.findall(r'"([\w_]+)"', m.group(1)) if m else []


def automation_flags() -> list[str]:
    # AUTOMATION_FLAGS literal moved to app/api/automation_flags.py (2026-06-20 refactor);
    # growth.py now only re-exports it, so read the new home (growth.py fallback).
    src = _read(ROOT / "app" / "api" / "automation_flags.py") or _read(GROWTH)
    m = re.search(r"AUTOMATION_FLAGS\s*=\s*\[(.*?)\]", src, re.S)
    return re.findall(r'"([A-Z][A-Z0-9_]+)"', m.group(1)) if m else []


SRC_EXT = (".py", ".html", ".js", ".yml", ".yaml", ".sh")


def _real_filenames() -> set[str]:
    """All real source filenames in the repo (excl. venv/cache/git/worktrees)."""
    names: set[str] = set()
    excluded = {".venv", "node_modules", "__pycache__", ".git", "worktrees"}
    for _base, dirs, files in os.walk(ROOT, topdown=True, onerror=lambda _e: None):
        # Prune before descent: Path.rglob can enter a stale worktree junction
        # before its path reaches the exclusion check and raise FileNotFoundError.
        dirs[:] = [d for d in dirs if d not in excluded]
        names.update(files)
    return names


def files_ref_audit(html: str) -> list[str]:
    """Reverse-sync (graph -> code): explorer `files:` tokens that EXPLICITLY name
    a source file (ext in SRC_EXT) but don't resolve to a real repo file = drift.
    Loose capability labels / routes / plan-ids (no extension) are ignored on
    purpose — product-view nodes use them as human descriptions, not file claims."""
    real = _real_filenames()
    missing: set[str] = set()
    for fld in re.findall(r"files:'([^']*)'", html):
        for tok in re.split(r"[·,]", fld):
            base = tok.strip().split("/")[-1].split("#")[0].strip()
            if base.lower().endswith(SRC_EXT) and base not in real:
                missing.add(base)
    return sorted(missing)


def audit() -> dict:
    html = _read(EXPLORER)
    blob = html.lower()
    mods = sorted(engine_modules())
    jobs = staff_jobs()
    flags = automation_flags()
    miss_mods = [x for x in mods if x.lower() not in blob]
    miss_jobs = [j for j in jobs if j.lower() not in blob]
    miss_flags = [f for f in flags if f.lower() not in blob]
    nodes = len(re.findall(r"\{id:'", html))
    edges = len(re.findall(r"\{f:'", html))
    return {
        "nodes": nodes,
        "edges": edges,
        "mods": mods,
        "miss_mods": miss_mods,
        "jobs": jobs,
        "miss_jobs": miss_jobs,
        "flags": flags,
        "miss_flags": miss_flags,
        "miss_files": files_ref_audit(html),
    }


def parse_views(html: str) -> dict[str, dict]:
    """Split explorer.html into its VIEWS (structural/automation/products/builder)
    and collect each view's node-id set + edge (f,t) list. Edges only connect
    WITHIN a view, so dangling/orphan checks are per-view."""
    keys = ["structural", "automation", "products", "builder"]
    marks: list[tuple[int, str]] = []
    for k in keys:
        m = re.search(r"\n  " + k + r": \{", html)
        if m:
            marks.append((m.start(), k))
    marks.sort()
    views: dict[str, dict] = {}
    for i, (pos, k) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(html)
        seg = html[pos:end]
        # node ids ONLY from the nodes:[...] block (presets/tour also use {id:'..'})
        nb = re.search(r"nodes:\s*\[(.*?)\n    \],", seg, re.S)
        ids = set(re.findall(r"\{id:'([\w]+)'", nb.group(1))) if nb else set()
        edges = re.findall(r"\{f:'([\w]+)',\s*t:'([\w]+)'", seg)
        if ids or edges:
            views[k] = {"ids": ids, "edges": edges}
    return views


def edge_audit(html: str) -> dict[str, dict]:
    """Per-view connection health: dangling edges (f/t not a node in that view),
    orphan nodes (degree 0 — on the graph but wired to nothing), leaf nodes
    (degree 1 — likely missing downstream/upstream)."""
    out: dict[str, dict] = {}
    for k, v in parse_views(html).items():
        ids, edges = v["ids"], v["edges"]
        if not edges:
            continue
        deg = dict.fromkeys(ids, 0)
        dangling = []
        for f, t in edges:
            if f not in ids or t not in ids:
                dangling.append((f, t))
            if f in deg:
                deg[f] += 1
            if t in deg:
                deg[t] += 1

        # rm_*/gap_* = intentional roadmap/status marker tiles → allowed standalone
        def _marker(i):
            return i.startswith(("rm_", "gap_"))

        out[k] = {
            "nodes": len(ids),
            "edges": len(edges),
            "dangling": dangling,
            "orphans": sorted(i for i, d in deg.items() if d == 0 and not _marker(i)),
            "markers": sorted(i for i, d in deg.items() if d == 0 and _marker(i)),
            "leaves": sorted(i for i, d in deg.items() if d == 1),
        }
    return out


def _stub(name: str, i: int) -> str:
    x = 40 + (i % 6) * 300
    y = 1700 + (i // 6) * 140
    return (
        "      {id:'%s', type:'platform', badge:'AUTO', cx:'simple', "
        "title:'%s', desc:'TODO: describe', files:'%s.py', x:%d, y:%d, w:250, h:100},"
        % (name, name.replace("_", " ").title(), name, x, y)
    )


def main(argv: list[str]) -> int:
    a = audit()
    pct = round(100 * (len(a["mods"]) - len(a["miss_mods"])) / max(1, len(a["mods"])))
    print("=" * 56)
    print("EXPLORER GRAPH <-> CODEBASE DRIFT")
    print("=" * 56)
    print(f"graph: {a['nodes']} nodes, {a['edges']} edges")
    print(
        f"engine modules on graph: {len(a['mods']) - len(a['miss_mods'])}/{len(a['mods'])} ({pct}%)"
    )
    if a["miss_mods"]:
        print(f"  MISSING engine modules ({len(a['miss_mods'])}): {', '.join(a['miss_mods'])}")
    print(
        f"staff jobs not named on graph (info): {len(a['miss_jobs'])}/{len(a['jobs'])}"
        + (f" -> {', '.join(a['miss_jobs'])}" if a["miss_jobs"] else "")
    )
    print(
        f"flags tagged on graph (info): {len(a['flags']) - len(a['miss_flags'])}/{len(a['flags'])}"
    )
    if a["miss_files"]:
        print(
            f"  DRIFT — `files:` refs not on disk ({len(a['miss_files'])}): {', '.join(a['miss_files'])}"
        )
    else:
        print("file refs (graph -> code): all resolve to real files")

    ea = edge_audit(_read(EXPLORER))
    print("\n--- connection health (per view) ---")
    for view, r in ea.items():
        print(
            f"{view}: {r['nodes']} nodes · {r['edges']} edges"
            + (f" · DANGLING {len(r['dangling'])}" if r["dangling"] else "")
            + (f" · orphans {len(r['orphans'])}" if r["orphans"] else "")
            + (f" · markers {len(r['markers'])}" if r["markers"] else "")
            + (f" · leaves {len(r['leaves'])}" if r["leaves"] else "")
        )
        if r["dangling"]:
            print(
                f"    DANGLING (f/t not a node): {', '.join(f'{f}->{t}' for f, t in r['dangling'])}"
            )
        if r["orphans"]:
            print(f"    ORPHAN (0 edges): {', '.join(r['orphans'])}")
        if r["leaves"]:
            print(f"    leaf (1 edge — maybe needs more): {', '.join(r['leaves'])}")

    if "--stubs" in argv and a["miss_mods"]:
        print("\n--- paste-ready node stubs (place + edit coords/desc) ---")
        for i, name in enumerate(a["miss_mods"]):
            print(_stub(name, i))

    if "--check" in argv:
        dangling = {v: r["dangling"] for v, r in ea.items() if r["dangling"]}
        orphans = {v: r["orphans"] for v, r in ea.items() if r["orphans"]}
        if a["miss_mods"]:
            print(
                f"\n[FAIL] {len(a['miss_mods'])} scheduled engine module(s) not on the graph "
                "— add nodes (--stubs) or this drift was intentional."
            )
            return 1
        if dangling:
            print(f"\n[FAIL] dangling edges (target/source node missing): {dangling}")
            return 1
        if orphans:
            print(f"\n[FAIL] orphan nodes (on graph, 0 edges): {orphans}")
            return 1
        if a["miss_files"]:
            print(f"\n[FAIL] explorer `files:` references not found on disk: {a['miss_files']}")
            return 1
        print(
            "\n[OK] every engine module represented · no dangling edges · no orphan nodes "
            "· all file refs resolve"
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never-raise
        print(f"[explorer_sync] skipped: {type(e).__name__}: {e}")
        sys.exit(0)
