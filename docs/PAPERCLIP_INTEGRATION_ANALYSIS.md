# PAPERCLIP × LEADGEN — Capability Differential & Integration Decision

> Research date: 2026-08-19 · Upstream: `github.com/paperclipai/paperclip` (MIT, branch `master`, latest release `v2026.817.0` published 2026-08-18) · LeadGen prod baseline: `6d278975` (healthy at research time)
> Rule obeyed: **only the highest-value NON-DUPLICATE capability is adopted natively.** No second scheduler, no second task system, no second dashboard, no vendored dependency.

## 1. What Paperclip actually is (verified from source)

Node/TypeScript pnpm-workspace monorepo: `server/` (Fastify-style API, Postgres, vitest), `ui/` (React), `packages/adapters/*` (CLI/gateway adapters), `cli/`, `docker/`. Docs tree (`docs/docs.json` navigation + `docs/agents-runtime.md`) describes: heartbeat runtime (timer/assignment/on_demand/automation wakeups, coalescing, session resume), agent adapters (claude_local, codex_local, opencode_local, cursor, pi_local, hermes_local/gateway, openclaw_gateway, process, http), company-scoped multi-tenancy, task manager with approvals/reviews/routines, org chart, goals-and-projects hierarchy (`company → team → agent`, statuses `planned/active/achieved/cancelled`), costs-and-budgets, activity log, importing/exporting, skills store, tool connections with credential bindings (`company_secret_bindings`), workspaces (managed worktree services, signed login handoff, readiness contract — PR #11671).

Recent issue evidence (open PRs #11678/#11679/#11261): adapter/config bugs exist (duplicate credential binding 500, misleading `oauth_challenge`, grok-local conflicting CLI flags). Project is actively developed (~11.6k PRs/issues) with strong CI (Greptile 5/5 gates, token-gates, per-adapter test suites).

**Honest takeaway:** Paperclip is a *generic multi-company agent-workforce control plane*. LeadGen is a *vertical business SaaS with an embedded workforce*. The overlap is the control-plane layer — and LeadGen already built most of it natively (`app/agents/harness/`, Owner OS, approvals, audit, budgets). Only a few concepts are genuinely missing.

## 2. Capability differential — 10 highest-value capabilities

Ranked by (value to LeadGen) × (gap size) × (duplication risk inverted). Evidence column cites LeadGen grep/read results from 2026-08-19.

| # | Paperclip capability | LeadGen current state (evidence) | Gap | Verdict |
|---|---|---|---|---|
| 1 | **Goal hierarchy as first-class records** (`api/goals-and-projects`: company→team→agent levels, statuses planned/active/achieved/cancelled, goals→projects/tasks links) | `goal` exists only as FREE-TEXT strings: `AgentTask.goal`/`goal_text` (app/models/agent_task.py:30,36), coordination `goal: str` fields (app/api/agents.py:79-264), mission `parent_goal_id` (app/api/dev_tasks.py:584). No goals table, no status lifecycle, no level, no goal→task linkage, no goals API anywhere (`grep goal app/api` → zero routers) | **LARGE** — the "why" tree is untracked | **ADOPT** (this task) |
| 2 | **Heartbeat protocol with coalescing** (timer/assignment/on_demand/automation wakeups; merge duplicate wakeups) | Per-agent Celery beat schedules + self-improve loop + staff_bus events (parallel work in flight); harness per-run lifecycle. No unified "wakeup merge" semantics across all wake sources | MEDIUM | **BRIDGE later** (thin concept over existing scheduler; NOT now — risks duplicating scheduler work) |
| 3 | **Per-agent monthly budget windows with hard stop** | Harness `stop.py` has per-RUN budgets (max_iterations/max_usd/max_tokens/max_wall_clock_s); no per-agent PERIOD budget ledger | MEDIUM | **BRIDGE later** (needs billing-meter discipline, §5 fail-open rule) |
| 4 | **Activity log / attention feed** (issue_thread_interaction → inbox rows; approvals/reviews/failed-runs surfaces) | agent_events + SSE stream, audit JSONL, approval drafts — exists natively; parallel agent is adding task→staff_bus events (task_bridge.py) | SMALL | **KEEP EXISTING** (parallel work closes the rest) |
| 5 | **Approvals** (approvals inbox, request_confirmation, reviews) | `approvals_bridge.py` + risk_approve PM-03 + `/internal/dsh/approval-proposals` + Owner OS Approvals tab — exists | NONE | **KEEP EXISTING** |
| 6 | **Adapter normalization** (11 adapters incl. OpenClaw/Codex/Hermes gateways) | In-process Python agents + harness shadow adapters + OmniRoute (Buzz/Codex). DSH ADR-179/181-183 already settled: external runtimes restricted to hardened container only | NONE (decided) | **KEEP EXISTING / REJECT** (ADR-179 precedent; adapter bugs in Paperclip prove maturity risk) |
| 7 | **Skills store + runtime skill injection** | `.claude/skills` (~103) + `data/skills_extra` (~181) + thousand-engineers skill; runtime injection = persona text into DSH (closure untouched) | SMALL | **KEEP EXISTING** |
| 8 | **Cost reporting (per run, per agent)** | llm_calls.jsonl + llm_metrics + agent_task cost columns (cost_tokens_in/out, cost_usd, provider) | SMALL | **KEEP EXISTING** (columns already on AgentTask) |
| 9 | **Company-scoped isolation (multi-company boards)** | Customer isolation = client_id on tasks/tenant middleware; LeadGen is ONE company serving customers — different model | N/A | **REJECT** (does not map; would add a fake axis) |
| 10 | **Importing/exporting agent configs, projects+workspaces (repo dirs)** | Single-repo workforce; Buzz worktrees; per-client mini-sites. Repo-workspace model does not fit single-VPS architecture | SMALL | **REJECT for now** (backlog candidate) |

**Decision: ADOPT #1 — Goal Hierarchy natively** (module + model + API + UI + tests). Non-duplicate: no goals table/API/UI exists; tasks keep their own fields (no schema change to AgentTask); goals LINK to tasks advisory-style via goal_id list — read-only interop with the parallel agent's task work.

## 3. What we did NOT build (and why — anti-duplicate proof)

- ❌ No second scheduler (Celery beat remains THE scheduler — §5)
- ❌ No second task system (agent_task_queue remains THE queue; parallel task_bridge work untouched)
- ❌ No vendored Paperclip dependency (Node/TS, Postgres-specific, pnpm — incompatible with free-stack Python)
- ❌ No new dashboard page (Goals live inside existing Owner OS tab — UI-saath rule, no 4th dashboard)
- ❌ No changes to `app/platform/agent_task_queue.py` or `staff_bus/*` (parallel agent's files — collision avoided)

## 4. Integration record

| Component | File | What |
|---|---|---|
| Model | `app/models/agent_goal.py` | `agent_goals` table (additive, create_all boot-created) |
| Module | `app/platform/goals.py` | create/get/update/list/link_task/task_goal_lookup |
| API | `app/api/goals.py` | `/api/goals` (admin-only via require_admin) |
| UI | `frontend/owner_os.html` | "Goals" tab in existing Owner OS |
| Migration | `alembic/versions/024_add_agent_goals.py` | Alembic-only envs (`DB_CREATE_ALL=0`), idempotent, 021/023 pattern |
| Tests | `tests/test_goals_hierarchy.py` | 10 tests — module + API contract (wired-fixture sqlite pattern), ALL green 2026-08-19 |
| Docs | `docs/PAPERCLIP_INTEGRATION_ANALYSIS.md` | this file |

Verification evidence (2026-08-19 ~11:25 IST): ruff clean (5 files) · `pytest tests/test_goals_hierarchy.py` = 10/10 passed · `import app.main` OK with goals routes registered (5 routes inside `_IncludedRouter`, matches(FULL) for GET /api/goals verified) · `scripts/prod_check.py` clean for this change (only failures = parallel agent's BOM'd scripts/ci files, flagged to #build) · `check_secrets.py` clean (7 files) · prod `/health` healthy `6d278975` (no deploy — integration unshipped).

**Outcome classification: `PAPERCLIP_PARTIALLY_INTEGRATED`** — Paperclip's goal-hierarchy pattern adopted natively (concept ADOPT, zero external dependency); everything else in the differential proven KEEP EXISTING or REJECT with evidence above.

## 5. Follow-ups (parked, NOT this task)

1. Heartbeat coalescing semantics (BRIDGE #2) — needs scheduler-touch, separate gate.
2. Per-agent period budget ledger (BRIDGE #3) — billing-meter discipline review first.
3. Paperclip importing/exporting (backlog).
4. Upstream watch: Paperclip adapters still maturing (credential/flag bugs above) — re-evaluate only if LeadGen ever needs an external-CLI runtime beyond DSH boundaries.
