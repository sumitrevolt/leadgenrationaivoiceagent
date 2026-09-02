# Explorer v2 → LeadGen AI "Control Center" — Architecture Blueprint

> Status: design-of-record. Ships at a **new route `/app/control-center`**, flag-gated `CONTROL_CENTER=1` (default-off). The live `/app/explorer` is **never touched**.

---

## 1. Executive Summary

The Control Center turns the curated 239-node `/app/explorer` diagram into a 4-level operator cockpit: **L1 Executive Overview** (is everything OK + are we earning), **L2 Stack Explorer** (the architecture graph, now with a live-status overlay), **L3 Workflow Explorer** (Flow Runner runs, journal, replay, breakpoints), **L4 Agent Explorer** (the 18 AI staff). It is a **shell + client router that reuses existing endpoints and deep-links into existing operator pages** (`/app/automation`, `/app/team`, `/app/agents`, `/app/admin`, `/app/dashboards`) rather than re-implementing them. Built **vanilla single-file** (no React/Vite — the `.dockerignore` strips the JS toolchain) with **Sigma.js + Graphology (WebGL) + elkjs-in-worker** for the graph, vendored as pinned ESM with zero new build step. The honesty constraint is hard: every panel carries a `live / curated / projection` data-source badge — real-today data is colored, everything else is explicitly grey; mock figures from the reference screenshots (`$18.73`, `43,681`, `62 runs`, `500 agents`) are **never** rendered as live. **Phase 1 = L1 only**, composed entirely from endpoints that ship today, behind the flag, no graph rewrite.

---

## 2. Honest Reality-Check

The reference screenshots imply a runtime scale this platform does not have. Grep-verified truth vs reference:

| Reference value | Real-today value | Source of truth | Real vs needs-instrumentation |
|---|---|---|---|
| "500 agents" | **18 AI staff** (hardcoded) | `team.py` STAFF → `team_status()` (`admin_dashboard.py:535`) | REAL |
| "~214 / large node graph" | **~239 curated nodes** | `frontend/explorer.html` node literals | REAL (curated architecture, NOT runtime telemetry) |
| (implied many jobs) | **~24 scheduled jobs** | `automation_health._EXPECT` cadence map | REAL |
| "62 runs" | however many Flow Runner runs exist (few; ad-hoc + ~11:30 autostart) | `flow_dispatch.list_runs()` | REAL (render actual count, never fabricate) |
| "$18.73 cost" | **₹0 / no number** — free providers | — | MISSING. No cost/token capture anywhere (`grep cost\|token\|spend` in `llm_metrics.py`/`flow_dispatch.py` = 0). Only NVIDIA NIM is soft-paid. Show "projection / instrument pending", never a dollar figure. |
| "43,681 queue" | real DLQ/queue depth (small) | `automation_health.queue_depth()` (Redis `llen`) | REAL |
| Per-agent cost / runs / success | — | — | MISSING (events exist in `agent_events`, not rolled up per agent) |
| Per-API hit counts ("unused API") | — | — | MISSING (no route-hit counter across ~980 routes) |
| Per-node live status on the graph | partial | node↔job/agent id map must be built (client-side) | PARTIAL (most nodes are static-architecture, render grey) |

**Rule:** colored = backed by a real endpoint today; grey `◌ static` = architecture map; `~`-prefixed = clearly-labeled projection. The 10k-node count is a **capacity target**, not a populated reality — it gets real-today data plus explicitly-styled projection nodes.

---

## 3. Target Architecture — 4-Level Nav, Component Tree, URL Scheme

**One shell, four lenses, zero duplication.** Each level is a lens over data that already exists; where a deep operator surface already exists it is **deep-linked / embedded**, not re-rendered.

| Level | Lens | Reuses | Primary data source |
|---|---|---|---|
| **L1** Executive Overview | "Sab theek hai + paisa aa raha?" | NET-NEW shell home | `GET /api/growth/overview/today` |
| **L2** Stack Explorer | The 239-node architecture graph + live overlay | explorer `structural`/`products` views | curated graph + per-node live status join |
| **L3** Workflow Explorer | Flow Runner runs, journal, replay, breakpoints | explorer `automation` view + `/app/automation` | `GET /api/growth/process/runs`, `/run/{id}` |
| **L4** Agent Explorer | 18 AI staff: status, schedule, last action | `/app/team` + `/app/agents` | `GET /api/platform/team`, `agent_events`, `llm_metrics` |

### Component hierarchy

```
ControlCenterShell  (frontend/control_center.html — single file)
├── TopStrip            brand · L1–L4 breadcrumb · 6 live metric cards · env-pill · clock · ⌘K
├── LeftRail            icon nav: L1·L2·L3·L4 + saved views (collapse 60↔220px, persisted)
├── CenterCanvas        (per-level swap)
│   ├── L1.OverviewGrid       headline · problems[kya,fix] · staff-pulse · jobs · flags-off
│   │                         · activation · eval-gate · provider-chain
│   ├── L2.StackGraph         Sigma WebGL canvas + ELK layout + live-status overlay + minimap
│   │   └── NodeInspector     Overview·Health·Links·Workflows·Agents tabs
│   ├── L3.WorkflowExplorer   RunList + DAGCanvas + SwimlaneToggle
│   │   └── RunInspector      Timeline·Logs·Metrics + Approve/Reject/Replay
│   └── L4.AgentExplorer      StaffGrid (product filter, 3-tier status)
│       └── AgentInspector    role·next-run·today-events·owned-workflows·owned-nodes
├── RightInspector      380px, drag-resize, collapsible — context tabs per selection
├── BottomPanel         4 cells: Live Log (SSE) · Recent Runs · Active Alerts · DLQ/Queue
└── core/
    ├── store.js        ~40-line pub/sub UI store (level, selection, view, filters)
    ├── fetchJSON.js    SWR Map cache + AbortController + Bearer-token inject
    ├── sse.js          EventSource('/api/events/stream') + backoff + live/reconnect dot
    └── router.js       path-segment client router (deep-link + hard-refresh survival)
```

### URL scheme

```
/app/control-center                          L1 Executive Overview (home)
/app/control-center/stack                     L2 graph (default sub-view: structural)
/app/control-center/stack?view=products       L2 products view
/app/control-center/stack/{nodeId}            L2 node inspector
/app/control-center/workflow                  L3 run list
/app/control-center/workflow/{runId}          L3 run journal + replay + breakpoints
/app/control-center/agent                     L4 staff grid
/app/control-center/agent/{key}               L4 agent detail
```

- **One page-route** `@app.get("/app/control-center")` → `FileResponse(control_center.html)` + **server catch-all** `@app.get("/app/control-center/{rest:path}")` returning the same HTML so deep-links survive hard refresh; sub-paths resolve client-side.
- **Breadcrumbs** mirror the path (`Control Center › Stack › Voice Agent` / `› Workflow › run a3f1 › step "qualify"`).
- **Deep-linking is the integration glue:** L1 blocks, L2 nodes, L3 steps, L4 agents cross-link by id (node↔workflow↔agent); leaf actions deep-link out to the existing operator page in a new tab. Extends the explorer's existing `🔗 Share` deep-link precedent to all four levels.

---

## 4. Graph Engine + ELK + 10k-Node Scale

### What exists today (verified)
`frontend/explorer.html` is a **hybrid DOM+SVG diagram renderer**, not a graph engine: nodes = absolutely-positioned `<div>`s with **hand-authored `x/y/w/h`** (no layout algorithm); edges = per-edge **local bezier** (`buildPath()`, control points `dist*0.35` off-anchor → the literal source of crossing-spaghetti); render = full `innerHTML=''` teardown every pass. Auto-layout, edge-routing, and virtualization are **entirely absent** — fine at 239 nodes, dead past ~2–3k.

### Single recommendation: **Sigma.js v3 + Graphology (WebGL render) + elkjs in a Web Worker (layout + routing)**

This **merges the correct half of two lenses** rather than picking a rhetorical winner:
- **Graphology** = the graph data model (nodes/edges/attributes).
- **elkjs** (`elk-worker.min.js` in a real `Worker`) = computes layout: `layered` (Sugiyama) for the structural/automation DAGs with **orthogonal, crossing-minimized edge routing** (deletes both the hand-authored `x/y` tax and the bezier spaghetti); `mrtree` for the products/hierarchy view.
- **Sigma.js v3** = **WebGL** renderer — the only one of the candidates that actually reaches 10k nodes via quad-tree culling. All three are MIT, ESM-vendorable, zero build pipeline.

**Why NOT React Flow (rejected explicitly):** React Flow (`@xyflow/react`) renders nodes as **HTML divs + SVG edges** — it culls but stays DOM-bound, which dies at the same ~2–3k ceiling we are escaping, so it **cannot honestly hit the 10k target**. It also drags in the React runtime, fighting the `.dockerignore`/vanilla reality (§7). ELK's layout virtue is engine-agnostic; we keep ELK, we drop React Flow.

### Honest migration cost
- **Vendor + wire (~1 day):** drop Sigma + Graphology + elkjs into `frontend/vendor/` (or `design-system/assets/`), import-map, worker bootstrap, dark-theme. **No npm / no `vite build`** — baked by the existing `COPY frontend/` exactly like every other static asset.
- **Data port (~1 day):** transform existing `VIEWS` node/edge literals into a static manifest `frontend/design-system/assets/explorer_graph.json` (served via the `/design-system` StaticFiles mount). Curated content preserved; **drop every `x/y/w/h`** — ELK computes them. Manifest = data, git-pull-live, no rebuild (like `data/skills_extra`).
- **Live-data adapters (~1–2 days):** map existing fetches onto node `data`. *Less* code than today's bespoke status-pill logic.
- **Risk:** isolated by new-route + flag → zero blast radius. **This cost is NOT paid in Phase 1** (L1 has no graph); it lands in P2/P3.

### 10k-node strategy (concrete)
1. **Worker-side ELK layout (non-negotiable)** — off main thread; cache computed positions in `sessionStorage` keyed by graph-hash so re-opening a view is instant.
2. **Level-of-detail: cluster → stack → node**, driven by zoom — `z<0.4` ~20–30 super-nodes (reuse the curated domain groups as ELK parent containers) · `0.4–1.0` expand focused cluster · `z>1.0` full detail + live pills. Default view = ~20 collapsed super-nodes (the single biggest readability win over today's flat 239-node dump).
3. **Incremental re-layout** — live data (heartbeat/flag/run-status) only mutates node attributes (status color, packet); positions stay frozen. ELK re-layout fires **only** on structural change, **only** on the touched subtree. Retires today's full-`innerHTML` rebuild.
4. **Edge routing** — ELK orthogonal + edge-bundling for near-parallel edges. Replaces `buildPath()`.
5. **Live packets** — animate an edge only when its source node has a real event in the last N seconds (from SSE `/api/events/stream`); decorative always-on `flowDash` retired so a moving packet *means* something. Ship first using node-level liveness (edge active when source active = zero new backend); per-edge event tags on SSE can come later.
6. **Minimap + viewport culling** — Sigma built-ins.

---

## 5. Observability / Ops-Center — Features → Real Signals

The Ops layer is a **read-side computation over signals that already exist** — no new engines, thin additive aggregators (`growth_process.py` pattern: `@router.get` + `Depends(require_admin)`, import-safe, never-raises).

| Feature | Signal / endpoint | Computable today? |
|---|---|---|
| L1 system headline + problems[{kya,fix}] + flags-off | `GET /api/growth/overview/today` (`today_overview.build()`) | ✅ REAL |
| Dead-man heartbeats · overdue · DLQ/queue depth | `GET /api/growth/infra/automation-health` (+`queue_depth()`) | ✅ REAL |
| DLQ contents drill | `GET /api/growth/infra/dlq?key=failed\|dead` | ✅ REAL |
| Launch readiness + blockers | `GET /api/activation/summary` (+eval-gate probe) | ✅ REAL |
| LLM provider success/fallback/breaker | `GET /api/growth/infra/llm` (`llm_metrics.stats()`) | ✅ REAL (per-provider, **no cost**) |
| Infra score (disk/mem/backups) | `GET /api/growth/infra/hermes` (`infra_handler.snapshot()`) | ✅ REAL |
| Live log tail | SSE `GET /api/events/stream` (Redis `lgai:events`, heartbeat + DB-poll fallback) | ✅ REAL |
| Workflow run list + status | `GET /api/growth/process/runs` (`flow_dispatch.list_runs()`) | ✅ REAL |
| Run replay state + immutable journal | `GET /api/growth/process/run/{id}` (`replay()` + `journal()`) | ✅ REAL |
| **Time-travel / step-scrub** | client-side fold over the returned journal up to event-index k | ✅ REAL (zero new backend) |
| Pause / step / abort (breakpoints) | `POST /api/growth/process/run/{id}/approve\|reject` (+`node_id` for DAG) | ✅ REAL |
| Failure / retry highlight + RCA per run | `run_failed.error` + last `node_started` + in-edges (all in `replay()`) | ✅ REAL |
| Voice per-turn latency p50/p95 | `GET /api/admin/voice/latency` (`turn_metrics`) | ✅ REAL (voice only) |
| Eval-gate regression | `GET /api/eval-gate/summary` | ✅ REAL |
| Agent roster (18, product-split, 3-tier status) | `GET /api/platform/team` (`team_status()`) | ✅ REAL |
| Slowest-node / critical-path | diff `node_started.at`↔`node_completed.at` in journal | ⚠️ PARTIAL — derive only (`flow_dispatch.timings()`); no stored field yet |
| Cross-run bottleneck (p95 per node) | fold timings across `list_runs()` | ❌ NEW read-only rollup (`/process/node-stats`) |
| Per-agent runs / success / avg-duration | aggregate existing `agent_events` table | ❌ NEW read-only rollup (`team.agent_metrics()`) |
| System-level RCA ({symptom,cause,fix}) | join overdue + fallback-rate + queue + recent run_failed | ❌ NEW read-only aggregator (`/infra/rca`) |
| Highest-cost agents / cost-per-run ("$18.73") | tokens captured in `free_ai` but **dropped** by `llm_metrics` (keyed by provider, no agent/run attribution) | ❌ MISSING — only real new **write-path**; label "token-cost / quota-pressure", not dollars |
| Unused-API ("dead route") | — | ❌ NEW instrumentation (Redis `HINCRBY` per-path middleware) — do NOT pretend curated nodes are hit-data |
| Stuck/looping-run · dead-workflow · unused-agent anomalies | step_index not advancing / zero-run flow keys / agent with no events in N days | ⚠️ PARTIAL — computable from existing signals |

---

## 6. Visual System + ASCII Wireframes

Reuse `explorer.html`'s dark base (`#0a0a0c` surfaces, `#e2e8f0` text, amber `#f59e0b` accent) so v2 feels native.

**Tokens (essentials):** 4-step surface elevation `--bg-0..4` (`#08090c`→`#22252e`); text `--tx-1..4` (`#e6eaf0`→`#475569`); accent `#f59e0b`. **Status semantics** (orthogonal to domain hue): healthy `#22c55e` · processing `#3b82f6` · waiting `#eab308` · retry `#f97316` · failed `#ef4444` · AI-decision `#a855f7` · idle/curated-static `#64748b`. Status drives **dot + 3px left-accent-border + 12% bg tint**; domain hue = base color. 4px spacing scale; `--radius 6px`. Density: Comfortable (row 34px) default, Compact (26px) toggle for >500-node graphs, persisted `localStorage`.

**Honesty rule (hard):** curated-architecture nodes with no live binding render idle-grey at 70% opacity with a `◌ static` tag. Only nodes/runs backed by a real endpoint get live status colors. Canvas legend: *"colored = live today · gray = architecture map."* Status is **never color-only** — each carries a glyph (●▢◆▲■◌) + text label (colorblind-safe). `prefers-reduced-motion` kills dash-march/pulse/slide. Keyboard: `1–4` switch levels, arrows pan, `+/-` zoom, `Enter` open inspector, `Esc` close, `[`/`]` collapse rails, `⌘K` palette; visible `2px var(--accent)` focus ring.

### L1 — Executive Overview

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ● LeadGen AI  ▸ L1 Executive            ⌘K Search…        prod · 14:32 IST   ⚙  ◑  👤 │
│ ┌Staff──┐ ┌Jobs────┐ ┌Runs───┐ ┌Queue/DLQ┐ ┌Heartbeat┐ ┌LLM────┐                       │
│ │18 ●12 │ │24 ✓21  │ │ 8 ▶2  │ │ 0  ⚠ 3  │ │ 9/9 ●  │ │99% ok │   (cards = live-today) │
│ │▁▃▅▂▄  │ │ 3 prob │ │▁▂▅▃▁  │ │ DLQ red │ │ all up │ │mistral│                       │
│ └───────┘ └────────┘ └───────┘ └─────────┘ └────────┘ └───────┘                       │
├──┬──────────────────────────────────────────────────────────────────┬─────────────────┤
│L1│  AAJ KA HAAL (plain Hinglish — /overview/today.headline)          │  INSPECTOR      │
│▣ │  ⚠️ 3 cheez dhyan maangti hai — neeche dekho                       │  (kuch select   │
│L2│                                                                    │   karo)         │
│▢ │  ┌── PROBLEMS (kya → fix) ────────┐ ┌── STAFF PULSE ───────────┐  │                 │
│L3│  │ ● DLQ me 3 task failed         │ │ ●working  Isha  Rohan    │  │  Overview       │
│▢ │  │   fix: /infra/dlq sweep chalao │ │ ●active   Swara Neha …   │  │  Logs           │
│L4│  │ ● Email warmup cap hit         │ │ ○offline  Arjun(02:30)   │  │  Metrics        │
│▢ │  │   fix: WARMUP ramp dekho       │ │  18 total · 12 active    │  │  Deps           │
│  │  └────────────────────────────────┘ └──────────────────────────┘  │  Config         │
│─ │  ┌── TODAY'S JOBS (24 scheduled) ─┐ ┌── FLAGS OFF (safe-to-on) ─┐  │                 │
│👁│  │ ✓06:30 blog   ✓07:00 content   │ │ JOURNEY_ENGINE  matlab…  │  │                 │
│  │  │ ✓09:30 prospect ▶10:30 email   │ │ LIGHTRAG        matlab…  │  │                 │
│⊕ │  │ ⧖11:00 pipeline …  3 ✗ failed  │ │ … 6 off                  │  │                 │
│  │  └────────────────────────────────┘ └──────────────────────────┘  │                 │
│  │  ┌── ACTIVATION ──┐ ┌── EVAL GATE ──┐ ┌── PROVIDER CHAIN ──────┐  │                 │
│  │  │ ready_for_paid │ │ no regression │ │ mistral▰ groq▰ cere▱…  │  │                 │
│  │  │  ✓ true        │ │ ● green       │ │ /llm_metrics ok-rate   │  │                 │
│  │  └────────────────┘ └───────────────┘ └────────────────────────┘  │                 │
├──┴──────────────────────────────────────────────────────────────────┴─────────────────┤
│ ▾ LIVE  │ Live Log (SSE) │ Recent Runs │ Active Alerts │ DLQ / Queue │        ⤢ □ ▾    │
│ 14:32:11 job email_outreach ▶ start · 14:32:09 lead.qualified id=4821 · …               │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

L1 = composed entirely of REAL endpoints (`/overview/today`, `/platform/team`, `/infra/automation-health`, `/activation/summary`, eval-gate, llm_metrics). No graph, no mock counts.

### L3 — Workflow Explorer

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│ ● LeadGen AI  ▸ L3 Workflow ▸ run #a3f1 (email_outreach)   prod · 14:32   ⚙ ◑ 👤      │
│ ┌Staff┐ ┌Jobs┐ ┌Runs ▶2┐ ┌Queue┐ ┌Heartbeat┐ ┌LLM┐   ← strip persists across levels   │
├──┬──────────────────────────────────────────────────────────────────┬─────────────────┤
│L1│ RUNS (left list)        │  DAG CANVAS  (process/run/{id} journal)  │ INSPECTOR: RUN  │
│▢ │ ▸#a3f1 email ▶running   │                                          │ ┌─────────────┐ │
│L2│  #a3e7 prospect ✓ok     │   [scrape]──►[score]──◆decision◆──►[draft]│ │●running #a3f1│ │
│▢ │  #a3d2 pipeline ✗fail   │    green     green    purple      blue   │ │email_outreach│ │
│L3│  #a3c0 content ✓ok      │                 │                        │ ├─Timeline────┤ │
│▣ │  #a3b1 digest ⧖wait     │                 ▼ (yellow=waiting        │ │✓ scrape 1.2s │ │
│L4│  ──────────────────     │            [approval]◀── BREAKPOINT      │ │✓ score  0.4s │ │
│▢ │  filter: ✓ ▶ ✗ ⧖        │             ⧖ waiting human              │ │◆ decision    │ │
│  │  range: today ▾         │                 │                        │ │⧖ approval ◀━ │ │
│👁│  SWIMLANE (toggle)      │                 ▼                        │ │  [Approve][✗]│ │
│  │  ┌agent────steps──────┐ │            [send]───►[log.completed]      │ ├─Logs────────┤ │
│⊕ │  │Rohan │■■◆■□        │ │             orange(retry x2)   green     │ │14:31 send 429│ │
│  │  │Neha  │  ■■         │ │   ◀ minimap ▶   zoom[─●──] fit  replay▶  │ │  retry 1/3 … │ │
│  │  └─────────────────────┘ │   legend: ●healthy ▶proc ⧖wait ↻retry    │ │[Replay run]  │ │
│  │                         │           ✗fail ◆ai ◌static              │ │              │ │
├──┴──────────────────────────────────────────────────────────────────┴─────────────────┤
│ ▾ LIVE │ Run Journal (immutable) │ Step Logs │ Breakpoints (1 ⧖) │ Replay State │ ⤢ □ ▾│
│ step=approval state=PAUSED awaiting human · prior: decision→draft(ok)→send(retry 1/3)   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

L3 binds to the real Flow Runner: `/process/runs` (list), `/process/run/{id}` (immutable journal + replay), `POST /process/run/{id}/approve|reject` (the ⧖ buttons), SSE for live transitions. Swimlane maps steps→AI-staff. Purple ◆ = AI-decision; orange = retry. Static-only workflows render grey `◌static` + inspector note naming the instrumentation gap.

---

## 7. Frontend Tech / State / Data-Layer Decision

**Decision: vanilla single-file `frontend/control_center.html`, no React/Vite.** Ground truth forces it: `.dockerignore` (lines 35–44) strips `node_modules`, `frontend/src`, `frontend/public`, and `frontend/*.{ts,js,json}` from the build context; `Dockerfile.lock:88` is `COPY frontend/ ./frontend/` — a Vite `dist/*.js` bundle would be **ignored and 404 in prod**. The existing `package.json`/`vite.config.ts`/`dist/` is a dead starter nothing serves. Every working cockpit (`automation.html`, `admin_dashboard.html`, `explorer.html`) is vanilla single-file; v2 matches that so deploy = `docker cp` / rebuild with zero new step.

- **State** = ~40-line hand-rolled pub/sub store (level, selection, view, filters) persisted to `localStorage` + `location` path so deep-links/back-button work. No Zustand/Redux.
- **Data layer** = hand-written `fetchJSON(url,{ttl})` — in-memory `Map` SWR cache, `AbortController` per request, `Authorization: Bearer` injected for `require_admin` endpoints. "TanStack Query without the dependency," ~60 lines.
- **Real-time** = **SSE primary** (`EventSource('/api/events/stream')`, already exists, one-directional, survives the Caddy/uvicorn proxy with no WS upgrade) to invalidate cache + nudge counters; **visibility-gated polling** for event-less endpoints (overview 15s, automation-health 10s, process/runs 5s-with-drawer/30s-idle, team 30s, activation 60s, latency 20s); **pause all polling on `document.hidden`**. **No WebSocket** — breakpoint approve/reject are plain POSTs, then SSE/poll reflects new state.
- **Graph** = Sigma.js v3 + Graphology + elkjs (§4), pinned ESM via import-map, over the static `explorer_graph.json` manifest. WebGL, ≥50fps pan/zoom at 10k, default-collapsed clustering, ≤768px degrades to a virtualized list/tree.

---

## 8. Minimal NEW Backend Endpoints

All thin, `require_admin`, import-safe, flag-gated default-off, in a new `app/api/control_center.py` (read-side composition unless noted):

- `GET /api/control-center/overview` — fan-in aggregator over `today_overview.build()` + `automation_health.health()` + `llm_metrics.stats()` + `activation.summary()`; one call for L1. **Ship first.**
- `GET /api/control-center/agents/metrics` — per-agent rollup (runs, ok%, avg_ms, last_action, last_event_ts) from existing `agent_events`; powers L4 honestly (`team.agent_metrics()`).
- `GET /api/control-center/graph` — server-side merge of overview+team+runs+flags into one node-status map (cached 5–10s) to avoid N client fetches at 10k scale.
- `GET /api/growth/process/node-stats` — cross-run slowest-node / critical-path rollup from journal timings (`flow_dispatch.timings()`).
- `GET /api/growth/infra/rca` — joins overdue + fallback-rate + queue + recent run_failed → plain-Hinglish `{symptom,cause,fix}`.
- `GET /api/control-center/cost-rollup` — token/quota-pressure rollup (**only new write-path**: extend `llm_metrics.record()` to accept `tokens`/`run_id`); render as "projection / instrument pending" until live, never dollars.
- (later) route-hit middleware — Redis `HINCRBY` per path, to make "unused-API" real.

---

## 9. Phased Roadmap P0 → P4

| Phase | Goal | Ships | Effort | Flag | Non-breaking? |
|---|---|---|---|---|---|
| **P0** | Scaffold the shell | new route `/app/control-center` + catch-all; `control_center.html` shell (TopStrip/LeftRail/empty canvas); `store.js`/`fetchJSON.js`/`sse.js`/`router.js`; register `CONTROL_CENTER` in `AUTOMATION_FLAGS` | S | `CONTROL_CENTER=1` | ✅ new route only; `/app/explorer` untouched |
| **P1** | **L1 Executive Overview (START HERE)** | L1 grid wired to existing endpoints + 6 live metric cards + bottom Live-Log SSE panel + inspector skeleton | S | `CONTROL_CENTER=1` | ✅ |
| **P2** | L3 Workflow Explorer + L4 Agent Explorer | run list/journal/replay/breakpoints (`/process/*`) + DAG canvas + swimlane; staff grid + agent detail (+`agents/metrics`); `node-stats`, `rca` | M | `CONTROL_CENTER=1` | ✅ |
| **P3** | L2 Stack graph (engine migration) | vendor Sigma+Graphology+elkjs-worker; port `VIEWS`→`explorer_graph.json`; live-status overlay; LOD clustering; `control-center/graph` aggregator | L | `CONTROL_CENTER=1` (+optional `CC_GRAPH`) | ✅ — graph rewrite isolated to new file/route |
| **P4** | Cost/quota truth + 10k scale-out + anomaly/RCA polish | `cost-rollup` (token/quota write-path), per-edge live packets via SSE tags, route-hit middleware (unused-API), projection-node capacity test | M | `CONTROL_CENTER=1` (+`CC_COST`, `ROUTE_HIT_COUNTER`) | ✅ |

### PHASE 1 = START HERE (concrete first slice)

Ship **L1 Executive Overview only**, reusing existing endpoints, behind `CONTROL_CENTER=1`, at the **new route `/app/control-center`**, touching **nothing** in `/app/explorer`. No graph, no Sigma, no migration cost.

1. **Route** — add to `app/main.py` (beside the other `FileResponse` page routes):
   ```python
   @app.get("/app/control-center", tags=["Frontend"])
   async def app_control_center():
       return FileResponse(str(FRONTEND_DIR / "control_center.html"))
   ```
   (P0 adds the `/{rest:path}` catch-all; for P1 the single home route suffices.)
2. **Flag** — register `CONTROL_CENTER` in `AUTOMATION_FLAGS` (`growth.py`) so it shows in `GET /api/growth/infra/flags`. The page renders only when the flag is on (or gate the route on `os.getenv("CONTROL_CENTER")=="1"`).
3. **File** — `frontend/control_center.html`: TopStrip with 6 live metric cards + L1 grid + bottom SSE Live-Log, reusing `explorer.html`'s dark tokens.
4. **Data (all existing — zero new backend for P1):**
   - `GET /api/growth/overview/today` → headline · problems[{kya,fix}] · staff[] · jobs[] · flags_off[]
   - `GET /api/growth/infra/automation-health` → heartbeats · DLQ/queue cards
   - `GET /api/activation/summary` → readiness card
   - `GET /api/platform/team` → 18-staff pulse
   - `GET /api/growth/infra/llm` → provider-chain card (note: route is `/infra/llm`, not `/infra/llm-metrics`)
   - SSE `GET /api/events/stream` → bottom Live-Log
   - `GET /api/eval-gate/summary` → eval-gate card
5. **Honesty** — every card carries a `live / curated / projection` badge; cost stays a labeled `~projection` tile, never `$18.73`; staff shows the real **18**, jobs the real **24**, runs the actual count.
6. **Verify** — `python scripts/prod_check.py` + targeted test, hard-reload the container (stale-`.pyc` 404 gotcha), confirm `/health` = `production`, then hit `/app/control-center` with the flag on.

The aggregator `GET /api/control-center/overview` is the **first P1.5 optimization** (5 round-trips → 1) — not required for the initial slice, which fans out client-side over endpoints that ship today.
