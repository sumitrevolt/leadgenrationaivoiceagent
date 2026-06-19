# Spec — Agentic-Output Approval Cockpit (Sub-project D, V1 "bridge-first")

> Status: **APPROVED design** (brainstormed 2026-06-19). Free-stack · additive · never-raise · file-backed.
> Part of the "complete automation of both products" decomposition. This is sub-project **D** (Process-Engine Auto-Start + Agentic-Output Approval Bridge). V1 = the **bridge** half only; auto-start = V1.1 (separate spec).

## Why
The audit (`wtdmxifu5`) found the platform is "more built than automated": the 7-mode coordinator, sales_team, and FDE all produce real outputs that **rot in `data/*.jsonl` / in-memory** because nothing surfaces them for action. process_engine workflows pause at human breakpoints that already render in the Approvals tab, but the other agentic drafts have no home. D gives every agentic output **one human-in-the-loop cockpit** with **risk-tiered smart 1-click** action — without rebuilding any agent.

## Decisions (locked)
1. **Risk-tiered autonomy** — safe/reversible outputs are surfaced for 1-click; risky/external/irreversible (real outbound send, calls) stay draft-only by design (never in the approve path).
2. **Bridge-first V1** — surface + act on existing drafts. Scheduled auto-start of workflows is V1.1.
3. **Smart 1-click** — approve triggers the *bounded safe next-action* per stream (not a pure audit stamp, not a full real-send).
4. **No new flag** — cockpit is admin-gated and read-mostly; the "unset=off" flag-truth invariant stays intact. Bounded approve-actions reuse each target's existing gate.
5. **File-backed, read-on-each-request** — avoids the verified `self_improve` in-memory/per-process ApprovalQueue bug (web vs worker singletons differ).

## Scope
**IN (V1):** unified cockpit surfacing all agentic drafts + risk-tiered decide.
**OUT (→ V1.1):** `process_autostart` staff job (scheduled `start_run`), `PROCESS_AUTOSTART` flag, per-workflow input rotation. Documented in §8.

## Architecture (additive, no engine rewrites)
```
EXISTING draft sources (jsonl)              NEW thin approval layer             EXISTING UI (extend; no new tab)
sales_team → prospect_analyses/index.jsonl ┐
coordinator → coordination_runs.jsonl      ├─► approvals_bridge.py             ┐   automation.html #sec-approvals
fde.deploy → fde_deploys.jsonl  (NEW sink) │     • read-adapters (per source)  │   + new "Agent Drafts" card
code_upgrader → code_patches.jsonl         │     • status sidecar               ├─► apDraftsLoad() inside apLoad()
process_engine → process_runs/*.jsonl      ┘       (approval_decisions.jsonl)   │   pending count → existing badge
                                                   • decide()=stamp+safe-action ┘   render via draftBlocks()
                            GET  /api/growth/approvals/drafts
                            POST /api/growth/approvals/drafts/{source}/{id}/decide
```

## Components

### C1. `app/platform/approvals_bridge.py` (NEW — the only real new logic)
- `list_drafts(status_filter="pending") -> list[dict]` — merge read-adapters into uniform shape:
  `{source, id, title, body, created_at, status, meta}`. Each adapter wrapped try/except → `[]` on failure (one bad stream never breaks the cockpit).
- **Status sidecar** (generic, source files untouched): `data/approval_decisions.jsonl`, rows `{source, item_id, status, at, by}`, **collapse-to-latest** (the `code_upgrader.list_patches`/`set_status` pattern). `_status_for(source, item_id) -> "pending"|"approved"|"rejected"`; `_set_status(source, item_id, status, by)` appends a row.
- `decide(source, item_id, decision, by) -> dict` — append status row → fire the **bounded safe next-action** (per §C5) → `team.log_event`. Idempotent on latest status (double-approve = no-op). Never raises; bounded-action failure still stamps status (action is best-effort).
- **Read-adapters:**
  - `sales` → `sales_team.list_analyses()` (rows `{ts,pid,name,phone,niche,city,score,grade,md}`; body = read `data/prospect_analyses/<pid>.md` lazily/truncated).
  - `coordinator` → read+filter `data/coordination_runs.jsonl` → only `execute=False` AND mode ∈ {engineering, hierarchical, agentverse} (noise control).
  - `fde` → read `data/fde_deploys.jsonl` (new sink, §C2).
  - (`code_upgrader`, `process`, `self_improve` already surface via existing `apLoad()` — D does not duplicate them; the new card is **only** for sales/coordinator/fde.)

### C2. FDE persistence (additive)
`app/agents/fde.py` `deploy()` currently returns an in-memory dict and writes nothing. Add an additive append of the report to `data/fde_deploys.jsonl` with a `status` field and an `id` (mirror `prospect_analyses/index.jsonl` shape). Never-raise around the write.

### C3. API (in `app/api/growth.py`, placed after the process/upgrader block ~line 2312 to inherit `/api/growth` prefix + `require_admin`)
- `GET /api/growth/approvals/drafts` → `{drafts:[...], counts:{by_source, pending}}`.
- `POST /api/growth/approvals/drafts/{source}/{id}/decide` body `{decision: "approve"|"reject"}` → `approvals_bridge.decide(...)`, stamps approver via `getattr(user,'email','admin')`.
- **Fresh path** (audit confirmed no collision with existing `/api/clientops/approvals`, `/api/customer/.../approvals`, `/api/growth/process/run/{id}/approve`, `/api/growth/selfimprove/approvals-pending`, `/api/growth/upgrader/patches/{id}/status`). Grep `@router` before adding (FastAPI first-route-wins).
- Auth: `require_admin` for read + sales/coordinator/fde decide. (code_upgrader apply path keeps its existing `require_super_admin` — D does not touch it.)

### C4. UI (`frontend/automation.html` — extend, do NOT add a tab)
- One new card inside existing `#sec-approvals` section.
- `apDraftsLoad()` called from inside existing `apLoad()` (~:2460), alongside `apContentList`/`apPatch`.
- Pending count rolled into the existing `#tab-approvals` badge (:2493).
- Render via existing `draftBlocks()` (:1130); Approve/Reject buttons copy the existing `apPatch` row pattern (:2487).

### C5. Approve-action mapping (smart 1-click, risk-tiered)
| Source | Approve → | Reject → | Auth |
|---|---|---|---|
| sales_team deep-dive | mark-reviewed + enqueue to existing 1-click-send (NOT auto-sent) | dismiss | require_admin |
| coordinator plan (exec=False) | push summary/next-action → `self_improve.add_task` (internal) | dismiss | require_admin |
| fde.deploy report | enable the disabled drip-journey (`fde.py:131` `enabled=False`→`True`) | dismiss | require_admin |
| code_upgrader patch | existing approve→apply (UNCHANGED) | existing | require_super_admin |
| process breakpoint | existing approve→resume (UNCHANGED) | existing | require_admin |
| self_improve | existing (UNCHANGED) | existing | require_admin |

Risky real-send (rohan outreach at scale, swara calls) is **never** in the approve path — draft-only by design (must-stay-manual).

## Error handling
- Every read-adapter + the FDE write + every bounded action is try/except → degrade, never raise.
- `decide()` idempotent on latest status; missing/corrupt jsonl → treated as empty.
- One failing stream returns `[]` for that source only; the cockpit still renders the rest.

## Testing
- Unit: status sidecar collapse-to-latest; `decide()` append + idempotent (double-approve no-op).
- Unit: each read-adapter parses its format + tolerates a missing file.
- Unit: approve-action per source triggers the correct **bounded** call (monkeypatch `self_improve.add_task` / drip-enable / send-queue) and **asserts risky real-send is NOT called**.
- API: `GET` returns merged drafts; `POST decide` stamps status; RBAC enforced.
- Gates: `prod_check.py` + `cross_path_audit.py` green; targeted pytest.

## V1.1 preview (out of scope — separate spec)
`process_autostart` staff job via the standard 4-place + 2-registry pattern (`team_scheduler._run_job` elif + `scheduler_loop` IST window + `_last_ran` seed + `worker.py` `staff-process_autostart` beat mirror + `STAFF_JOBS` tuple + `automation_health.EXPECTED_GAP_MIN`), `PROCESS_AUTOSTART` flag (inert default), **idempotency dedup** via `list_runs()` (start_run has none today), and per-workflow input rotation (NICHE_ROTATION + city pool). Auto-started `lead_campaign`/`client_content` pause at their breakpoints **in this same cockpit**; `growth_audit` runs unattended (weekly).

## Duplicate-route / scheduler hazards (from audit — heed)
- New endpoints on a **fresh** `/api/growth/approvals/*` path; grep `@router` in growth.py first.
- UI: extend `apLoad()` + `#sec-approvals`; do NOT add a second tab or a second `apLoad`.
- (V1.1) new beat key MUST start `staff-`; job MUST be in `STAFF_JOBS`; same elif in `team_scheduler._run_job` so BOTH in-process + Celery paths fire.
