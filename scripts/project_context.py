#!/usr/bin/env python3
"""project_context.py — shared library for the persistent project-context store.

WHY: `graphify` (app/graphify-out/graph.json) is an AST *code* graph — great for
"who calls build_snapshot()". It does NOT hold PROJECT-level knowledge (products,
agents, workflows, feature flags, tenants, decisions, incidents, landmines, Unity
components, tests, deployment). This module ingests that knowledge from
already-committed repo docs/code into ONE compact, secret-safe, idempotent JSON
store so a fresh agent session can boot from a bounded snapshot instead of
re-reading the whole repo.

Design invariants:
  * Secret-safe: never reads `.env*`; masks anything secret-shaped before storing.
  * Idempotent: output is a deterministic function of repo content — re-running
    with no source change rewrites nothing (content_hash unchanged).
  * Degrades: any missing/unreadable source is skipped, never crashes.
  * Provenance: every node records its `source` file + `verified_sha` (git HEAD
    at ingest time).

The CLI wrappers are scripts/sync_project_context.py, query_project_context.py,
context_health.py and agent_task_packet.py.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def force_utf8_stdout() -> None:
    """Windows consoles default to cp1252 and crash on ₹/→/«»/emoji in summaries.
    Call from every CLI main() so printing project facts never raises."""
    import sys as _sys

    for stream in (_sys.stdout, _sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE = REPO_ROOT / "app" / "graphify-out" / "project_context.json"
DEFAULT_SNAPSHOT = REPO_ROOT / "app" / "graphify-out" / "CONTEXT_SNAPSHOT.md"
SCHEMA = "leadgen-project-context/1.0"

# --------------------------------------------------------------------------- #
# Secret safety — mask secret-shaped substrings; NEVER read .env*.
# (git SHAs are intentionally kept, so no bare 40-hex rule.)
# --------------------------------------------------------------------------- #
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
# key=value / key: value where the value looks like a real secret literal.
_KV_SECRET = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|ACCESS[_-]?KEY))\b"
    r"\s*[:=]\s*[\"']?([A-Za-z0-9_\-\./+]{8,})[\"']?"
)
_REDACTED = "«redacted»"


def redact(text: str) -> str:
    """Mask secret-shaped substrings. Keeps env-var NAMES, masks their VALUES."""
    if not text:
        return text
    out = text
    for pat in _SECRET_PATTERNS:
        out = pat.sub(_REDACTED, out)
    out = _KV_SECRET.sub(lambda m: f"{m.group(1)}={_REDACTED}", out)
    return out


def _is_env_path(p: Path) -> bool:
    return p.name.startswith(".env")


def read_text_safe(p: Path, limit: int = 200_000) -> str:
    """Read a text file defensively. Refuses .env*; returns '' on any error."""
    try:
        if _is_env_path(p) or not p.is_file():
            return ""
        return p.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def _clip(s: str, n: int = 240) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# --------------------------------------------------------------------------- #
# git helpers (tolerant — never raise)
# --------------------------------------------------------------------------- #
def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=20
        ).stdout.strip()
    except Exception:
        return ""


def git_head() -> str:
    return _git("rev-parse", "HEAD") or "unknown"


def git_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"


def changed_files(ref: str) -> set[str]:
    out = _git("diff", "--name-only", ref, "HEAD")
    return {ln.strip().replace("\\", "/") for ln in out.splitlines() if ln.strip()}


# --------------------------------------------------------------------------- #
# Node / edge helpers
# --------------------------------------------------------------------------- #
def _node(nodes: dict, ntype: str, name: str, source: str, summary: str, sha: str) -> str:
    nid = f"{ntype}:{name}"
    nodes[nid] = {
        "id": nid,
        "type": ntype,
        "label": name,
        "source": source,
        "verified_sha": sha,
        "summary": redact(_clip(summary)),
    }
    return nid


def _rel(name: str) -> Path:
    return REPO_ROOT / name


def _relpath(p: Path) -> str:
    try:
        return p.relative_to(REPO_ROOT).as_posix()
    except Exception:
        return p.as_posix()


# --------------------------------------------------------------------------- #
# Ingestors — each returns (nodes-added, edges-added). All tolerant.
# --------------------------------------------------------------------------- #
def ingest_project(nodes, edges, sha):
    claude = read_text_safe(_rel("CLAUDE.md"))
    charter = ""
    m = re.search(r"## 1\. PROJECT CHARTER\s*(.+?)(?:\n## )", claude, re.S)
    if m:
        charter = m.group(1)
    pid = _node(
        nodes,
        "Project",
        "leadgenrationaiagent",
        "CLAUDE.md",
        charter or "LeadGen AI SaaS platform",
        sha,
    )
    # Products (charter names them explicitly)
    for prod in ("AI Automated Marketing", "AI Voice Calling Agent"):
        if prod in claude:
            n = _node(nodes, "Product", prod, "CLAUDE.md", f"Product: {prod}", sha)
            edges.append({"src": n, "rel": "BELONGS_TO_PROJECT", "dst": pid})
    return pid


def ingest_current_state(nodes, edges, sha, project_id):
    claude = read_text_safe(_rel("CLAUDE.md"))
    m = re.search(r"## Current State.*?\n(.+)$", claude, re.S)
    block = m.group(1) if m else ""
    if block:
        _node(nodes, "CurrentState", "sprint", "CLAUDE.md", block, sha)
    bm = re.search(r"Blockers.*?:\s*(.+?)(?:\n\*\*|\n## |\Z)", block, re.S)
    if bm:
        for line in re.findall(r"[-*]\s+(.+)", bm.group(1))[:12]:
            n = _node(nodes, "Blocker", _clip(line, 60), "CLAUDE.md", line, sha)
            edges.append({"src": n, "rel": "BLOCKED_BY", "dst": "CurrentState:sprint"})


def _bulleted(md: str, limit: int):
    return re.findall(r"^[-*]\s+(.+)$", md, re.M)[:limit]


def ingest_landmines_invariants(nodes, edges, sha):
    claude = read_text_safe(_rel("CLAUDE.md"))
    for header, ntype, rel in (
        (r"## 7\. KNOWN LANDMINES", "Landmine", None),
        (r"## 5\. CRITICAL INVARIANTS", "Invariant", None),
    ):
        m = re.search(header + r"(.+?)(?:\n## )", claude, re.S)
        if not m:
            continue
        for i, line in enumerate(_bulleted(m.group(1), 25)):
            _node(nodes, ntype, f"{ntype.lower()}-{i:02d}", "CLAUDE.md", line, sha)


def ingest_memory(nodes, edges, sha):
    specs = [
        ("memory/decisions.md", "ArchitectureDecision", 50),
        ("memory/incidents.md", "Incident", 40),
        ("memory/backlog.md", "PendingTask", 40),
        ("memory/glossary.md", "GlossaryTerm", 60),
        ("memory/integrations.md", "Service", 60),
    ]
    for rel, ntype, cap in specs:
        md = read_text_safe(_rel(rel))
        if not md:
            continue
        # Prefer dated/heading entries; fall back to bullets.
        entries = re.findall(r"^(?:#{2,4}\s+.+|[-*]\s+\d{4}-\d{2}-\d{2}.+)$", md, re.M)
        if not entries:
            entries = re.findall(r"^[-*]\s+\*\*(.+?)\*\*", md, re.M)
        seen = 0
        for e in entries:
            key = re.sub(r"[^A-Za-z0-9]+", "-", e).strip("-").lower()[:60]
            if not key:
                continue
            _node(nodes, ntype, key, rel, e, sha)
            seen += 1
            if seen >= cap:
                break


def ingest_flags(nodes, edges, sha):
    src = "app/api/automation_flags.py"
    md = read_text_safe(_rel(src))
    flags = sorted(set(re.findall(r"[\"']([A-Z][A-Z0-9_]{3,})[\"']", md)))
    for f in flags[:150]:
        _node(nodes, "FeatureFlag", f, src, f"Feature flag {f}", sha)


def ingest_unity(nodes, edges, sha, project_id):
    root = _rel("unity")
    if not root.is_dir():
        return
    for cs in sorted(root.rglob("*.cs"))[:60]:
        txt = read_text_safe(cs, limit=4000)
        doc = ""
        dm = re.search(r"///?\s*(.+)|/\*\*?\s*(.+)", txt)
        if dm:
            doc = dm.group(1) or dm.group(2) or ""
        n = _node(nodes, "UnityScript", cs.stem, _relpath(cs), doc or f"Unity C# {cs.stem}", sha)
        edges.append({"src": n, "rel": "BELONGS_TO_PROJECT", "dst": project_id})
    # Generated scenes (declared in the generator, not committed as .unity)
    gen = read_text_safe(
        root / "LeadGenVirtualOffice" / "Assets" / "Editor" / "GenerateOfficeScenes.cs"
    )
    for scene in sorted(set(re.findall(r"Assets/Scenes/([A-Za-z0-9_]+)\.unity", gen))):
        _node(
            nodes,
            "UnityScene",
            scene,
            "unity/.../GenerateOfficeScenes.cs",
            f"Generated Unity scene {scene}",
            sha,
        )


# Unity-facing API routes + the flags that gate them (deterministic mapping).
_OFFICE_ROUTES = [
    (
        "GET /api/platform/office/snapshot",
        "app/api/office_hq.py",
        "Admin office snapshot (rooms/agents/pipeline/health)",
        "require_admin",
    ),
    (
        "GET /api/customer/office",
        "app/api/customer_dashboard.py",
        "Tenant-scoped customer office payload",
        "require_customer",
    ),
    (
        "GET /app/office",
        "app/main.py",
        "Admin office page (3d shell / 2d map fallback)",
        "require_admin",
    ),
    (
        "GET /app/customer/office",
        "app/main.py",
        "Customer office page (3d shell / redirect fallback)",
        "require_customer",
    ),
    ("GET /api/events/stream", "app/api/events.py", "Admin SSE event stream", "require_admin"),
]
_FLAG_ROUTE = {
    "UNITY_VIRTUAL_OFFICE_ENABLED": "GET /app/office",
    "UNITY_CUSTOMER_OFFICE_ENABLED": "GET /app/customer/office",
    "CUSTOMER_OFFICE": "GET /api/customer/office",
}


def ingest_routes(nodes, edges, sha):
    for route, src, summary, auth in _OFFICE_ROUTES:
        n = _node(nodes, "ApiRoute", route, src, f"{summary} [{auth}]", sha)
        edges.append({"src": n, "rel": "AUTHORIZES", "dst": f"Auth:{auth}"})
        _node(nodes, "Auth", auth, "app/api/auth_deps.py", f"Auth dependency {auth}", sha)
    for flag, route in _FLAG_ROUTE.items():
        rid = f"ApiRoute:{route}"
        if rid in nodes:
            edges.append({"src": f"FeatureFlag:{flag}", "rel": "CONTROLLED_BY_FLAG", "dst": rid})


def ingest_tests(nodes, edges, sha):
    tdir = _rel("tests")
    if not tdir.is_dir():
        return
    pat = re.compile(r"office|unity|tenant|dashboard|activation", re.I)
    for t in sorted(tdir.glob("test_*.py")):
        if pat.search(t.name):
            _node(nodes, "Test", t.stem, _relpath(t), f"Test suite {t.name}", sha)


def ingest_deployment(nodes, edges, sha):
    dc = read_text_safe(_rel("docker-compose.vps.yml"))
    for svc in sorted(set(re.findall(r"^\s{2}([a-z0-9_-]+):\s*$", dc, re.M)))[:30]:
        _node(nodes, "Deployment", svc, "docker-compose.vps.yml", f"Compose service {svc}", sha)


INGESTORS = [
    ingest_landmines_invariants,
    ingest_current_state,
    ingest_memory,
    ingest_flags,
    ingest_unity,
    ingest_routes,
    ingest_tests,
    ingest_deployment,
]


# --------------------------------------------------------------------------- #
# Build / hash / persist
# --------------------------------------------------------------------------- #
def build_store(root: Path | None = None) -> dict[str, Any]:
    global REPO_ROOT
    if root is not None:
        REPO_ROOT = Path(root).resolve()
    sha = git_head()
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    project_id = ingest_project(nodes, edges, sha)
    ingest_current_state(nodes, edges, sha, project_id)
    ingest_landmines_invariants(nodes, edges, sha)
    ingest_memory(nodes, edges, sha)
    ingest_flags(nodes, edges, sha)
    ingest_unity(nodes, edges, sha, project_id)
    ingest_routes(nodes, edges, sha)
    ingest_tests(nodes, edges, sha)
    ingest_deployment(nodes, edges, sha)

    node_list = [nodes[k] for k in sorted(nodes)]
    edge_list = sorted(edges, key=lambda e: (e["src"], e["rel"], e["dst"]))
    # de-dup edges
    seen, uniq = set(), []
    for e in edge_list:
        k = (e["src"], e["rel"], e["dst"])
        if k not in seen:
            seen.add(k)
            uniq.append(e)
    store = {
        "meta": {
            "schema": SCHEMA,
            "head_sha": sha,
            "branch": git_branch(),
            "node_count": len(node_list),
            "edge_count": len(uniq),
        },
        "nodes": node_list,
        "edges": uniq,
    }
    store["meta"]["content_hash"] = content_hash(store)
    return store


def content_hash(store: dict) -> str:
    payload = json.dumps(
        {"nodes": store["nodes"], "edges": store["edges"]}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def merge_changed(old: dict, new: dict, changed: set[str]) -> dict:
    """--changed-since mode: keep old nodes whose source did NOT change; refresh
    only nodes whose source file is in the changed set. Preserves verified_sha
    for untouched facts (idempotency + honest provenance)."""
    old_by_id = {n["id"]: n for n in old.get("nodes", [])}
    merged = {}
    for n in new["nodes"]:
        src = n["source"].split()[0]
        if src in changed or n["id"] not in old_by_id:
            merged[n["id"]] = n  # refreshed / brand-new
        else:
            merged[n["id"]] = old_by_id[n["id"]]  # unchanged -> keep old sha
    node_list = [merged[k] for k in sorted(merged)]
    out = {"meta": dict(new["meta"]), "nodes": node_list, "edges": new["edges"]}
    out["meta"]["node_count"] = len(node_list)
    out["meta"]["content_hash"] = content_hash(out)
    return out


def load_store(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def snapshot_md(store: dict) -> str:
    m = store["meta"]
    by_type: dict[str, int] = {}
    for n in store["nodes"]:
        by_type[n["type"]] = by_type.get(n["type"], 0) + 1
    lines = [
        "# Project Context Snapshot (derived — regenerate with scripts/sync_project_context.py)",
        "",
        f"- Schema: `{m['schema']}`  |  HEAD: `{m['head_sha'][:8]}`  |  branch: `{m['branch']}`",
        f"- Nodes: {m['node_count']}  |  Edges: {m['edge_count']}  |  content_hash: `{m['content_hash'][:12]}`",
        "",
        "## Node counts by type",
        "",
    ]
    for t in sorted(by_type):
        lines.append(f"- **{t}**: {by_type[t]}")
    lines += ["", "## Blockers / Current State", ""]
    for n in store["nodes"]:
        if n["type"] in ("Blocker", "CurrentState"):
            lines.append(f"- ({n['type']}) {n['summary']}")
    lines.append("")
    return "\n".join(lines)


def write_store(store: dict, store_path: Path, snapshot_path: Path) -> bool:
    """Write only if content changed. Returns True if written."""
    existing = load_store(store_path)
    if existing and existing.get("meta", {}).get("content_hash") == store["meta"]["content_hash"]:
        return False
    store = dict(store)
    store["meta"] = dict(store["meta"])
    store["meta"]["generated_at"] = datetime.now(timezone.utc).isoformat()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
    snapshot_path.write_text(snapshot_md(store), encoding="utf-8")
    return True
