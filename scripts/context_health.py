#!/usr/bin/env python3
"""context_health.py — health check for the persistent-context layer.

Checks (all read-only, no network):
  1. graphify MCP binary present (AST code-graph navigation).
  2. graphify graph.json present + fresh vs git HEAD (via GRAPH_REPORT.md).
  3. project_context.json present + valid + head_sha matches current HEAD.
  4. memory/ fallback files present (safe degradation target).

Exit code: 0 if usable (context available OR memory fallback present); 1 only on
hard failure (store unreadable/corrupt AND memory fallback also missing).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project_context as pc  # noqa: E402

ROOT = pc.REPO_ROOT


def _graph_report_sha() -> str | None:
    rpt = ROOT / "app" / "graphify-out" / "GRAPH_REPORT.md"
    txt = pc.read_text_safe(rpt)
    m = re.search(r"(?:Built from commit|commit)\s*[:=]?\s*([0-9a-f]{7,40})", txt, re.I)
    return m.group(1) if m else None


def check() -> dict:
    head = pc.git_head()
    results = {}

    results["graphify_binary"] = {
        "ok": bool(shutil.which("graphify") or shutil.which("graphify-mcp")),
        "detail": shutil.which("graphify") or shutil.which("graphify-mcp") or "not on PATH",
    }

    graph = ROOT / "app" / "graphify-out" / "graph.json"
    grpt = _graph_report_sha()
    graph_present = graph.is_file()
    results["code_graph"] = {
        "ok": graph_present,
        "detail": (
            f"graph.json present; report_sha={grpt or '?'} head={head[:8]} "
            f"{'FRESH' if grpt and head.startswith(grpt) else 'STALE/unknown'}"
            if graph_present
            else "FAIL-LOUD: app/graphify-out/graph.json MISSING — Graphify MCP cold. "
            "Run scripts/graphify_refresh.bat (or .sh) before graphify query/explain."
        ),
    }

    store_path = pc.DEFAULT_STORE
    store = pc.load_store(store_path)
    if store is None:
        results["project_context"] = {"ok": False, "detail": f"MISSING/corrupt: {store_path}"}
    else:
        recomputed = pc.content_hash(store)
        sha_ok = store.get("meta", {}).get("head_sha", "").startswith(head[:8]) or head == "unknown"
        results["project_context"] = {
            "ok": store.get("meta", {}).get("content_hash") == recomputed,
            "detail": f"nodes={store['meta'].get('node_count')} "
            f"store_sha={store['meta'].get('head_sha', '?')[:8]} head={head[:8]} "
            f"{'FRESH' if sha_ok else 'STALE — run sync'} "
            f"hash={'valid' if store['meta'].get('content_hash') == recomputed else 'CORRUPT'}",
        }

    mem = [
        p for p in ("INDEX.md", "decisions.md", "incidents.md") if (ROOT / "memory" / p).is_file()
    ]
    results["memory_fallback"] = {
        "ok": len(mem) >= 1,
        "detail": f"present: {', '.join(mem) or 'NONE'}",
    }
    return results


def main() -> int:
    pc.force_utf8_stdout()
    r = check()
    print("context layer health:")
    for k, v in r.items():
        if k == "code_graph" and not v["ok"]:
            tag = "FAIL"
        else:
            tag = "PASS" if v["ok"] else "WARN"
        print(f"  [{tag}] {k}: {v['detail']}")
    hard_fail = (not r["project_context"]["ok"]) and (not r["memory_fallback"]["ok"])
    require_graph = __import__("os").environ.get("GRAPHIFY_REQUIRE_GRAPH", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    graph_missing = not r["code_graph"]["ok"]
    if hard_fail:
        verdict = "FAILED"
    elif graph_missing and require_graph:
        verdict = "FAILED-GRAPH-MISSING"
    elif graph_missing:
        verdict = "DEGRADED-GRAPH-MISSING"
    elif not r["project_context"]["ok"]:
        verdict = "DEGRADED-BUT-USABLE"
    else:
        verdict = "HEALTHY"
    print(f"verdict: {verdict}")
    if hard_fail or (graph_missing and require_graph):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
