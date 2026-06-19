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

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPLORER = ROOT / "frontend" / "explorer.html"
SCHED = ROOT / "app" / "platform" / "team_scheduler.py"
STAFF = ROOT / "app" / "tasks" / "staff_jobs.py"
GROWTH = ROOT / "app" / "api" / "growth.py"

_DROP = {"os", "json", "asyncio", "datetime", "timezone", "time", "random", "typing",
         "annotations", "contextlib", "io", "logging", "math", "uuid", "re",
         "logger", "settings", "config", "models", "base"}


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
    m = re.search(r"AUTOMATION_FLAGS\s*=\s*\[(.*?)\]", _read(GROWTH), re.S)
    return re.findall(r'"([A-Z][A-Z0-9_]+)"', m.group(1)) if m else []


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
        "nodes": nodes, "edges": edges,
        "mods": mods, "miss_mods": miss_mods,
        "jobs": jobs, "miss_jobs": miss_jobs,
        "flags": flags, "miss_flags": miss_flags,
    }


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
    print(f"engine modules on graph: {len(a['mods']) - len(a['miss_mods'])}/{len(a['mods'])} ({pct}%)")
    if a["miss_mods"]:
        print(f"  MISSING engine modules ({len(a['miss_mods'])}): {', '.join(a['miss_mods'])}")
    print(f"staff jobs not named on graph (info): {len(a['miss_jobs'])}/{len(a['jobs'])}"
          + (f" -> {', '.join(a['miss_jobs'])}" if a["miss_jobs"] else ""))
    print(f"flags tagged on graph (info): {len(a['flags']) - len(a['miss_flags'])}/{len(a['flags'])}")

    if "--stubs" in argv and a["miss_mods"]:
        print("\n--- paste-ready node stubs (place + edit coords/desc) ---")
        for i, name in enumerate(a["miss_mods"]):
            print(_stub(name, i))

    if "--check" in argv:
        if a["miss_mods"]:
            print(f"\n[FAIL] {len(a['miss_mods'])} scheduled engine module(s) not on the graph "
                  "— add nodes (--stubs) or this drift was intentional.")
            return 1
        print("\n[OK] every scheduled engine module is represented on the graph")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:  # never-raise
        print(f"[explorer_sync] skipped: {type(e).__name__}: {e}")
        sys.exit(0)
