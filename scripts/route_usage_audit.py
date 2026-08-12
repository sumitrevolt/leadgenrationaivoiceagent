#!/usr/bin/env python3
"""route_usage_audit.py - find genuinely-unused API routes from REAL traffic.

Static cross-referencing canNOT prove a route is dead: the frontend builds many
URLs dynamically and external/webhook clients call endpoints that never appear
as string literals in the repo. Real access logs are the source of truth.

Usage (run on the VPS, over >=30 days of logs):
  python scripts/route_usage_audit.py --access-log /opt/leadgen/logs/access.log
  python scripts/route_usage_audit.py --access-log <file> --show-hits

Output: routes with 0 hits = real deprecation candidates. Then VERIFY, deprecate,
run prod_check.py + run_tests.bat, /ship, confirm /health=production. Small batches.

Note: matches by path (ignores method) and assumes the API mount prefix is /api
(adjust MOUNT below if different). Page routes from main.py are included.
"""

import argparse
import glob
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOUNT = "/api"  # adjust if your include_router prefix differs


def extract_routes():
    routes = []
    for rf in glob.glob(str(ROOT / "app/api/*.py")):
        name = os.path.basename(rf)
        if name == "__init__.py":
            continue
        g = open(rf, encoding="utf-8", errors="ignore").read()
        m = re.search(r'APIRouter\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', g)
        rprefix = m.group(1) if m else ""
        for mm in re.finditer(r'@router\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']', g):
            method, path = mm.group(1).upper(), mm.group(2)
            rpath = (rprefix.rstrip("/") + "/" + path.lstrip("/")) if rprefix else path
            full = rpath if rpath.startswith(MOUNT) else MOUNT + rpath
            routes.append((method, full, f"{method:6} {full}   [{name}]"))
    mp = ROOT / "app/main.py"
    if mp.exists():
        g = open(mp, encoding="utf-8", errors="ignore").read()
        for mm in re.finditer(r'@app\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\"]', g):
            routes.append(
                (
                    mm.group(1).upper(),
                    mm.group(2),
                    f"{mm.group(1).upper():6} {mm.group(2)}   [main.py]",
                )
            )
    return routes


def to_regex(path):
    parts = [
        "[^/]+" if (s.startswith("{") and s.endswith("}")) else re.escape(s)
        for s in path.split("/")
    ]
    return re.compile("^" + "/".join(parts) + "/?$")


RX = re.compile(r'(?:GET|POST|PUT|DELETE|PATCH)\s+([^ ?"]+)')


def log_paths(fp):
    with open(fp, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            m = RX.search(line)
            if m:
                yield m.group(1).split("?")[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--access-log", required=True)
    ap.add_argument("--show-hits", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.access_log):
        sys.exit(f"access log not found: {a.access_log}")
    routes = extract_routes()
    comp = [(to_regex(p), d) for _, p, d in routes]
    hits = {d: 0 for _, _, d in routes}
    for p in log_paths(a.access_log):
        for rx, d in comp:
            if rx.match(p):
                hits[d] += 1
                break
    dead = sorted(d for d, c in hits.items() if c == 0)
    print(f"# {len(routes)} routes vs {a.access_log}")
    print(f"# UNUSED (0 hits): {len(dead)}  -> deprecation candidates (verify first)\n")
    for d in dead:
        print("  0      " + d)
    if a.show_hits:
        print("\n# WITH HITS:")
        for d, c in sorted(hits.items(), key=lambda x: -x[1]):
            if c:
                print(f"  {c:<7}{d}")


if __name__ == "__main__":
    main()
