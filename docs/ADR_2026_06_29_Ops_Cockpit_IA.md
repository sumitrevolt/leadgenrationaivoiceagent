# ADR — Ops Cockpit Information Architecture (Automation vs Agent Tools vs Control Center)

- **Date:** 2026-06-29
- **Status:** Accepted (decision); implementation phased (Phase-0 = this doc, no code yet)
- **Scope:** `/app/automation#today` · `/app/agent-tools` · `/app/control-center#/stack` (+ reconciled: `/app/dashboards`, `/app/explorer`, admin_dashboard health embed)
- **Decision owner:** Sumit · **Author:** Claude (code-grounded audit, not URL-guess)

---

## 0. TL;DR (the decisive answer)

**Ye teen pages DUPLICATE NAHI hain. Sab KEEP karo.** They map almost exactly onto a clean SaaS ops IA — three different **verbs**:

| Page | Verb | One-line role | Read/Write |
|---|---|---|---|
| **Control Center** | **OBSERVE** | System/agent/stack health + today snapshot (4-level cockpit) | read-only |
| **Automation** | **ACT** | Mission Control — run / approve / retry / schedule the pipeline | write |
| **Agent Tools** | **CONFIGURE / GOVERN** | Agent capabilities, permissions, code tools, checkpoints | write (governance) |

The overlap that *looks* like duplication is:
1. **Latent, not live** — Control Center is nav-hidden today (`CONTROL_CENTER` flag OFF → `nav_enabled:false`). So the user currently sees **no duplication**; it only activates if/when the flag flips.
2. **Backend already shared** — Control Center and Automation both read the **same** sources (`today_overview.build()`, `automation_health.health()`, `team.team_status()`). It's a shared-data-source, *not* copy-pasted logic. The only real debt is **frontend rendering the same panels twice**.

➡️ So the "merge" task is **not** "merge pages." It is: **before enabling Control Center, dedup the shared render into one contract** (which already exists: `GET /api/control-center/overview`).

---

## 1. Council Summary (6 lenses)

- **Product Architect:** Observe / Act / Configure = three legitimate user intents. Keeping them separate is *more* clear, not less. Killing any one loses a distinct job-to-be-done. Verdict: KEEP 3.
- **UX Designer:** Real confusion is **two pages both claiming to be "the pane"** — `control_center` (built to be THE health cockpit) and `dashboards.html` literally titled *"Unified Dashboards."* Plus Control Center isn't even in the sidebar. Fix nav grouping + rename the impostor pane.
- **Backend Engineer:** No route conflict (all distinct page-routes in `main.py`; `/api/agents-ext/*`, `/api/control-center/*`, `/api/growth/*` are disjoint). `control_center.py` is already a thin fan-IN aggregator — reuse it; don't fork a second today-glue.
- **SRE/DevOps:** Control Center L1–L4 (health, stack graph, run timings, agent metrics) is the correct single-pane-of-glass. It's wasted while nav-OFF. Enable it; make it the canonical observe surface; point admin_dashboard's health link at it.
- **AI Agent Architect:** Agent Tools is **unique** — `/api/agents-ext` (permissions/hooks/checkpoints/code-exec) appears nowhere else. It is configuration of *agent capabilities*, not automation execution. Zero merge.
- **Business/GTM Lead:** All three are **internal** (admin/operator/dev). **None customer-facing** (customers live on `/app/customer*`). So this is purely internal-tooling hygiene — no revenue/pricing risk, low blast radius.

**Chairman verdict:** KEEP all three with clarified roles. ENABLE Control Center as canonical OBSERVE. RENAME the competing "Unified Dashboards." DEDUP shared render via the existing aggregator. Treat the second architecture graph (Explorer vs CC-L2) as a phase-2 consolidate.

---

## 2. What each page actually is (from code, not names)

### A. `/app/automation` → `frontend/automation.html` (3331 lines, ~32 tabs) — **ACT**
Tabs: 🏠 Aaj · 🚀 Launch · 🗓️ Schedule · 🤖 Agents · 🕷️ Scraping · 📥 Approvals · 📜 Events · 🌾 Harvester · 👥 Prospects · 📨 Cadence · 🧠 Sales Team AI · ⚙️ Processes · 🔁 Self-Improve · 🛠️ Code Upgrader · 🎯 RL Flywheel · ✍️ Drafters · 💰 Revenue Ops · 📈 Growth Lab · 🤝 ClientOps · 🔎 Research · 🎨 Content+ · 📬 Lifecycle · ♻️ ContentAuto · 🚀 FDE Deploy · 📞 Telephony · 🎯 Post-Call · 🎟️ Loyalty · 📊 NPS · 🔗 Webhooks · ⭐ Reviews · 📑 Client Reports · 🚦 Runtime Flags.
- **Purpose:** the action cockpit — you *run* harvests, *approve* tasks, *enroll* cadences, *deep-dive* prospects, toggle flags. `🏠 Aaj` = `today_overview` quick status; `🗓️ Schedule` = `/api/growth/infra/automation-health`.
- **Audience:** Admin / Operator. **In nav:** `🎛 Automation`.

### B. `/app/agent-tools` → `frontend/agent_tools.html` (259 lines, 14 sections) — **CONFIGURE/GOVERN**
Sections (all → `/api/agents-ext/*` + `/api/growth/upgrader/*`): 🔍 Codebase Search · 🩺 Diagnostics · 📝 Code Review · 🧠 Agent Recall · 📈 Trajectories · 🗳️ Consensus · 🔐 Permissions (tool ACL) · 🪝 Lifecycle Hooks · 🎭 Custom Agents · ⚡ Capacity · 💾 Checkpoints · 🚀 Batch · ⚠️ Code Exec (SA) · 🌐 Browser Fetch (SA).
- **Purpose:** manage *agent capabilities* — permissions, hooks, custom personas, checkpoints, dev/debug tools. **Not** workflow execution, **not** infra health.
- **Audience:** Developer / Super-Admin. **In nav:** `🛠 Agent Tools`. **Overlap with the other two: essentially none — UNIQUE.**

### C. `/app/control-center` → `frontend/control_center.html` (1676 lines, hash-routed 4 levels) — **OBSERVE**
Routes: `#/` L1 Executive · `#/stack` L2 Stack · `#/workflow` L3 Workflow · `#/agent` L4 Agent.
- **L1 Executive:** headline / problems / staff pulse / today's jobs / metrics (staff·jobs·runs·queue·heartbeat·llm ok-rate) / activation / eval-gate — via `GET /api/control-center/overview`, which fans IN over `today_overview + automation_health + llm_metrics + activation + eval_gate + flow_dispatch`.
- **L2 Stack (`#/stack`):** architecture graph (Sigma.js + ELK WebGL), iframe-embedded `control_center_graph.html`.
- **L3 Workflow:** per-node p50/p95 run timings + RCA (`/api/control-center/node-stats`, `/rca`).
- **L4 Agent:** per-agent rollup (`ok_rate`, `events_total`, `last_action`) via `team.team_status()` (`/api/control-center/agents/metrics`).
- **Audience:** Admin / SRE / Developer. **NOT in admin nav** — `CONTROL_CENTER` flag OFF (orphan). Read-only by design.

---

## 3. Duplication Matrix

| Feature / Widget / Data source | Automation | Agent Tools | Control Center | Also in | Duplicate? | Decision |
|---|---|---|---|---|---|---|
| `today_overview` (headline·problems·staff·jobs) | ✅ `🏠 Aaj` | — | ✅ L1 | dashboards (partial), admin_dashboard (partial) | **YES** (render only; backend shared) | Shared contract `/api/control-center/overview`; CC L1 = deep, Automation Aaj = quick + link |
| `automation_health` (jobs·queue·heartbeat·DLQ) | ✅ `🗓️ Schedule` | — | ✅ L1 metrics | admin_dashboard `loadAutomationHub` | **YES** (render only) | One source; CC = canonical view |
| `team_status` (agent roster/metrics) | ✅ `🤖 Agents` | — | ✅ L4 | `/app/team`, `/app/agents` | **YES** (render only) | CC L4 = metrics lens (read); Automation Agents = action lens (assign); keep both intents |
| Automation flags on/off | ✅ `🚦 Runtime Flags` | — | ✅ L1 `flags_off` | dashboards, admin_dashboard | Partial | Automation = toggle (act); CC = status (read) |
| Activation readiness | — | — | ✅ L1 | ✅ dashboards | **YES** | Canonicalize in CC; dashboards = phase-2 fold |
| Eval gate | — | — | ✅ L1 | ✅ dashboards | **YES** | Canonicalize in CC |
| Architecture graph | — | — | ✅ L2 Stack (Sigma+ELK) | ✅ `/app/explorer` (own engine) | **YES** (two engines) | CC L2 = canonical; Explorer phase-2 consolidate/relabel legacy |
| Agent memory / MCP keys | — | ✅ Recall | — | ✅ dashboards (cards) | Partial | Agent Tools = operate; dashboards = status |
| Run / approve / retry / harvest / enroll | ✅ ONLY | — | — (read-only) | — | No | **Automation UNIQUE** |
| Permissions · hooks · checkpoints · code-exec · code-review · diagnostics | — | ✅ ONLY | — | — | No | **Agent Tools UNIQUE** |
| Stack graph · run timings · per-agent ok_rate | — | — | ✅ ONLY | — | No | **Control Center UNIQUE** |

---

## 4. Final Decision Table

| Page / Route | Decision | Why |
|---|---|---|
| `/app/automation` | **KEEP** | Canonical ACT cockpit; unique run/approve surface. Minor: Aaj panel → shared contract. |
| `/app/agent-tools` | **KEEP** (clarify label/group) | Unique configure/govern surface; no merge. Group under "Developer/Ops". |
| `/app/control-center` | **KEEP + ENABLE + nav** | Canonical OBSERVE pane; flip `CONTROL_CENTER=1`, add sidebar link, dedup render first. |
| `/app/dashboards` ("Unified Dashboards") | **RENAME** → "Activation & Integrations"; phase-2 **MERGE into CC** | Stop two panes claiming "unified"; it's feature/integration status, not live health. |
| `/app/explorer` (Architecture Explorer) | **KEEP now, MOVE phase-2** | Two graph engines; CC L2 is canonical going forward. Do NOT delete (memory: untouched/don't rebuild). |
| admin_dashboard `#sec-health` + Automation Hub embed | **KEEP** as summary-with-link | Launchpad pattern is good; point health "→" at Control Center once enabled. |

**No page is REMOVED.** No route changes (so no redirects needed). Renames are title/label only — backward compatible.

---

## 5. Recommended Navigation (admin sidebar)

Group all of these under a single **`⚙️ Ops`** parent in `admin_dashboard.html`:

```
Admin Console
└── ⚙️ Ops
    ├── 🖥️ Control Center        OBSERVE (read-only)        Admin · SRE · Dev
    │     ├── L1 Executive   health · today · queue/heartbeat · LLM ok-rate · activation · eval-gate
    │     ├── L2 Stack       architecture graph (canonical; supersedes Explorer)
    │     ├── L3 Workflow    run timings · node p50/p95 · RCA
    │     └── L4 Agent       per-agent ok_rate · events · last action
    ├── 🎛️ Automation          ACT (run/approve/retry)      Admin · Operator
    ├── 🛠️ Agent Tools         CONFIGURE / GOVERN           Dev · Super-Admin
    ├── 🗺️ Architecture        (→ Control Center L2)        Dev          [legacy Explorer link]
    ├── 🔌 Activation & Integrations  (was "Unified Dashboards")   Admin
    └── 👥 AI Staff Team        roster (customer-framed)     Admin
```

**Role visibility:**
- **Customer:** NONE (all internal; customers use `/app/customer*`).
- **Operator:** Automation (act) + Control Center (read).
- **Admin:** all of Ops.
- **Developer / Super-Admin:** Agent Tools + Control Center + Architecture graph.

---

## 6. Merge / Refactor Plan

**Shared component (the core of the "merge"):**
- Backend is already shared → `GET /api/control-center/overview` is the single fan-in contract. **Reuse it.**
- Extract one render function `renderTodayPanel(overview)` (headline/problems/staff/jobs) used by **both** `control_center.html` L1 and `automation.html` `🏠 Aaj`. Automation Aaj should call `/api/control-center/overview` instead of its own `automation-health + today` glue, OR at minimum consume the identical contract shape.
- `team_status` rollup: single fetch; CC L4 renders *metrics* (read), Automation Agents renders *actions* (assign/next-task). Same data, different lens — keep both, no double fetch path.
- Architecture graph: CC L2 (`control_center_graph.html`) is canonical; Explorer stays until phase-2.

**APIs to reuse (no new ones needed):** `/api/control-center/overview|agents/metrics|node-stats|rca|cost-rollup|route-hits` (already built + tested in `tests/test_control_center.py`).

**State/data model:** none new. The "shared model" is the `overview` contract already defined in `control_center.py::_defaults()` and mirrored in `control_center.html::blankOverview()`.

---

## 7. Implementation Checklist (phased, safe, additive)

**Phase 0 — Decision (this ADR). No code.** ✅

**Phase 1 — Enable + nav (LOW risk, additive only):**
- [ ] VPS `.env`: `CONTROL_CENTER=1` (nav-surface gate; API already admin-reachable).
- [ ] `frontend/admin_dashboard.html`: add `🖥️ Control Center` sidebar link; introduce `⚙️ Ops` group; regroup Automation / Agent Tools / Explorer / Team under it.
- [ ] Point admin_dashboard `#sec-health` "→" link at `/app/control-center`.
- Files: `frontend/admin_dashboard.html`, VPS `.env`. **No backend change → existing tests stay green.**

**Phase 2 — Dedup render (MEDIUM):**
- [ ] Make `automation.html` `🏠 Aaj` consume `/api/control-center/overview` contract (single source).
- [ ] Factor a shared `renderTodayPanel()` (inline JS include — project serves static HTML, no bundler).
- Files: `frontend/automation.html`, `frontend/control_center.html`. **Edit additively; do NOT parallel-edit the same large file (truncation risk).**

**Phase 3 — Reconcile extra panes (MEDIUM):**
- [ ] Rename `/app/dashboards` title `🎛️ Admin Dashboards`/"Unified Dashboards" → **"Activation & Integrations"**; update nav label. (Route unchanged → backward compatible.)
- [ ] Relabel Explorer nav as deep/legacy graph; decide fold-into-CC-L2.
- Files: `frontend/dashboards.html`, `frontend/admin_dashboard.html`, `frontend/explorer.html`.

**Tests to add/update:**
- [ ] `tests/test_control_center.py`: assert `/app/control-center` route → 200; assert overview honors `CONTROL_CENTER` flag in `nav_enabled`.
- [ ] Route smoke: `/app/automation`, `/app/agent-tools`, `/app/control-center` all 200 (prod_check route-count already guards).
- [ ] No contract change in Phase 1 → `test_billing_truth_2026` + existing suites unaffected.

---

## 8. Acceptance Criteria

- [ ] All three routes load 200, no JS/console errors.
- [ ] Control Center is reachable from the sidebar (no longer an orphan) when `CONTROL_CENTER=1`.
- [ ] No metric is rendered by two pages via two *different* code paths for the same decision — Aaj + CC L1 share one contract.
- [ ] **Automation** surface = execution/action intent only (run/approve/retry/schedule/flags-toggle).
- [ ] **Agent Tools** surface = capability/permission/governance only (already true).
- [ ] **Control Center** surface = read-only observe/health only (already true).
- [ ] Only **one** page brands itself the canonical health/observe pane (Control Center); "Unified Dashboards" renamed.
- [ ] `tests/test_control_center.py` + `prod_check.py` + billing-truth green.

---

## 9. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Flipping `CONTROL_CENTER=1` surfaces a page pulling `today_overview`/`team_status` | Low | API is `require_admin`; nav gate is frontend; aggregator never raises (partial data OK) |
| Two architecture graphs (Explorer + CC L2) confuse | Low | Phase-2 only; do NOT delete Explorer (memory: untouched/don't rebuild) |
| Large-file edits (`automation.html` 3331L, `control_center.html` 1676L) truncate on parallel edit | Med | Additive edits, one file at a time, Read-before-Edit (Windows = source of truth) |
| Renaming `/app/dashboards` breaks a deep link | Low | Title/label rename only — route unchanged, no redirect needed |
| First-route-wins shadowing | Low | All page-routes already distinct in `main.py`; no new routes added |

---

## 10. Final Recommended IA (one line each)

1. **Control Center** = OBSERVE → system health · stack graph · workflow timings · agent metrics (read-only single pane).
2. **Automation** = ACT → Mission Control run / approve / retry / schedule / flags-toggle.
3. **Agent Tools** = CONFIGURE/GOVERN → agent capabilities · permissions · hooks · checkpoints · code tools.
4. *(reconciled)* **Activation & Integrations** = feature/integration status (renamed from "Unified Dashboards"; phase-2 fold into Control Center).
5. *(reconciled)* **Architecture Explorer** = legacy graph; CC L2 canonical.

> Needs-product-decision (1): **fold `/app/dashboards` into Control Center (Phase-2) vs keep as a separate "Activation & Integrations" page.** Recommended: **rename now, fold later** — lowest risk, removes the "two unified panes" confusion immediately without a big refactor.
