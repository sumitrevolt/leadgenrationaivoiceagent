# Persistent Project Context — MCP + project-context layer

> Token-saving session memory. Two cooperating layers: the **graphify MCP** AST
> code-graph (navigation) and the **project-context store** (project-level facts).
> Both are DEV-only, secret-safe, and degrade to `memory/` markdown if absent.
> Last verified: HEAD `6fd188f` (2026-07-12).

## 1. What exists

| Layer | Artifact | Answers | Refresh | Token cost |
|---|---|---|---|---|
| **graphify MCP** (`.mcp.json` → `graphify-mcp`) | `app/graphify-out/graph.json` (~14 MB, 14,615 nodes / 26,521 edges) | "who calls `build_snapshot()`", call-paths, affected files | `scripts\graphify_refresh.bat` | 0 (AST-only) |
| **project-context store** | `app/graphify-out/project_context.json` (252 nodes / 26 edges) + `CONTEXT_SNAPSHOT.md` | products, agents, flags, tenants, decisions, incidents, landmines, Unity components, routes, tests, deployment | `scripts\sync_project_context.py` | 0 (repo docs/code only) |
| **fallback** | `memory/INDEX.md` + `memory/*.md` | same facts, human-authored | manual | read-on-demand |

The MCP server is **graphify** (the only entry in `.mcp.json`). There is no second
"Graphy/Graphiti" server — use the real configured name.

## 2. Commands

```powershell
# refresh the project-context store (idempotent — writes only on change)
.venv\Scripts\python.exe scripts\sync_project_context.py --dry-run
.venv\Scripts\python.exe scripts\sync_project_context.py
.venv\Scripts\python.exe scripts\sync_project_context.py --changed-since HEAD~1

# bounded keyword query (load ONLY task-relevant facts)
.venv\Scripts\python.exe scripts\query_project_context.py "unity office authentication flow" --k 6

# health check (graphify binary + graph freshness + store validity + memory fallback)
.venv\Scripts\python.exe scripts\context_health.py

# generate a bounded task packet for a worker/sub-agent (no whole-repo re-explain)
.venv\Scripts\python.exe scripts\agent_task_packet.py --objective "..." --files a.py,b.py --query "..." --test tests/x.py

# refresh the AST code-graph if stale (FREE, AST-only)
scripts\graphify_refresh.bat
```

## 3. Session boot protocol (compact — do this instead of re-reading the repo)

1. Read `memory/INDEX.md` + `CLAUDE.md ## Current State` (hot cache).
2. `context_health.py` → confirm the store is FRESH vs HEAD (else `sync_project_context.py`).
3. `query_project_context.py "<task keywords>"` → pull the bounded fact set + relationships.
4. `graphify query "<subsystem>"` (or MCP `query`/`affected`) → entrypoints/callers/tests.
5. Read ONLY the ~3–8 impl + 1–4 test files the query surfaced. Verify exact lines in source (graph = navigation, not proof).
6. Do the work; run the `/verify` gates.
7. **Write-back same session:** new decision → `memory/decisions.md`; incident → `memory/incidents.md`; then `sync_project_context.py` so the store reflects it.

## 4. Guarantees (tested — `tests/test_project_context_sync.py`)

- **Idempotent** — the store is a deterministic function of repo content; re-running with no change writes nothing (`content_hash` stable). `--changed-since REF` preserves `verified_sha` on untouched facts.
- **Secret-safe** — never reads `.env*`; masks secret-shaped substrings (`sk-…`, `AKIA…`, `AIza…`, `ghp_…`, `KEY=…`) before storing. `scripts\check_secrets.py` gates the repo.
- **Degrades** — any missing/unreadable source is skipped, never crashes; `context_health.py` returns `DEGRADED-BUT-USABLE` (memory fallback) rather than failing hard.
- **No PII to external models** — the store ingests only committed repo docs/code (no customer/lead/transcript data); nothing is sent to an external context server.

## 5. Schema

Nodes: `Project, Product, Service, UnityScript, UnityScene, ApiRoute, Auth,
FeatureFlag, Test, Deployment, ArchitectureDecision, Incident, PendingTask,
GlossaryTerm, Invariant, Landmine, CurrentState, Blocker`.
Relationships: `BELONGS_TO_PROJECT, AUTHORIZES, CONTROLLED_BY_FLAG, BLOCKED_BY`
(extend in `scripts/project_context.py` `_OFFICE_ROUTES` / `_FLAG_ROUTE` + ingestors).

Each node carries `{id, type, label, source, verified_sha, summary}` — provenance is
mandatory. See `docs/GRAPHIFY.md` for the code-graph layer this complements.
