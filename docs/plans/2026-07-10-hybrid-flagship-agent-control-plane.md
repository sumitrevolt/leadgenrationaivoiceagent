# Hybrid Flagship Agent Control Plane — Phase 1

## Goal

Add a canonical, database-backed control-plane contract for Claude-managed engineering tasks while preserving the existing coordinator, process engine, Celery, free-AI routing, LLM Council, and guarded deployment path.

## Approach

Introduce a new `DevTask` aggregate and an additive admin router under `/api/dev-tasks`. The first slice is draft-safe: it creates/claims/heartbeats/records task evidence and exposes a configuration-driven model catalog plus cost admission decision, but it does not execute shell commands, mutate the shared worktree, auto-apply patches, or deploy production. Later phases will attach Celery worktree runners and the existing Hostinger approval gate.

## Risk tier and rollback

High-risk: new database migration, admin API, automation control-plane, and provider-cost policy. Rollback is `DEV_ORCHESTRATOR=0` plus container recreate; schema rollback is the named Alembic downgrade for migration 015; no existing route or compliance gate is changed.

## File ownership map

| Owner | Files | Responsibility |
|---|---|---|
| Main session | `app/models/dev_task.py`, `app/models/__init__.py`, `alembic/versions/015_add_dev_tasks.py` | DB aggregate and migration |
| Main session | `app/dev_control/registry.py`, `app/dev_control/service.py` | task state machine, model catalog, cost admission |
| Main session | `app/api/dev_tasks.py`, `app/main.py` | admin API mount and request/response contract |
| Main session | `tests/test_dev_control_plane.py` | contract, idempotency, budget, auth-independent service tests |
| Main session | `app/api/automation_flags.py` | safe default feature flag registry |

Shared files are edited sequentially by the main session only. No parallel agent may edit `app/main.py`, `app/worker.py`, `app/platform/team_scheduler.py`, or `app/api/growth.py`.

## Tasks

### 1. Contract tests (RED first)

Add pure service tests for allowed states, illegal transitions, idempotent task creation, lease expiry, model metadata, budget denial, and sensitive-data local-only routing. Run:

`.venv\\Scripts\\python.exe -m pytest tests\\test_dev_control_plane.py -x -q`

Expected initial result: import/attribute failures because the new service does not exist.

### 2. Database aggregate and migration

Create `DevTask` with task identity, objective/customer scope, priority, state, model/fallback metadata, budget/usage fields, worktree/branch ownership, dependencies, acceptance criteria, retry/lease timestamps, evidence, approval/deployment fields, and timestamps. Add migration 015 with nullable/additive columns and a downgrade that drops only the new table. Register the model in `app.models` so Alembic metadata sees it.

### 3. Control-plane service

Implement a framework-light state machine with explicit transition validation, idempotency key handling, lease claim/heartbeat/release, structured worker report validation, provider/model registry metadata, and cost admission. Model IDs are configuration-driven; unverified flagship IDs are aliases disabled unless an endpoint/model is configured. The default catalog includes local-vLLM/Ollama and existing providers only; GLM/MiniMax/Kimi/DeepSeek/Qwen entries require explicit environment configuration.

### 4. Admin API and flag

Add `/api/dev-tasks` admin routes for create, list, claim, heartbeat, report, transition, and routing preview. Add `DEV_ORCHESTRATOR` to the existing automation flag registry with default OFF. API responses never expose secrets, raw prompts, customer PII, or provider credentials.

### 5. Verification

Run the focused service/API tests, migration chain 001→015 on isolated SQLite, Ruff on changed Python files, `scripts/prod_check.py`, `scripts/check_secrets.py`, duplicate-route grep, and `git diff --check`. Record exact evidence in `progress.md`. No commit, push, VPS migration, or deploy occurs without a later explicit user instruction.

## Deferred phases

Phase 2 adds provider-pinned gateway adapters and per-task token/cost ledger. Phase 3 adds Celery worktree execution with ownership locks and artifact reports. Phase 4 adds tmux observation windows and restart reconciliation. Phase 5 adds staged deployment and human production approval. Phase 6 connects Product One delivery evidence and customer notifications. Each phase gets its own migration/tests/rollback evidence; no phase may bypass `AUTO_APPLY_PATCH=0` or the existing production approval gate.

## Self-review

- Every Phase 1 requirement maps to a task above.
- No unverified provider model ID is enabled by default.
- No task executes shell commands, sends messages, calls leads, changes billing, or deploys.
- Database rollback, flag rollback, auth boundary, idempotency, lease recovery, budget denial, and secret scanning are explicitly covered.

## Phase 2 execution contract

`app/dev_control/gateway.py` provides provider-pinned, local-first invocation with configuration-disabled flagship skipping, bounded candidate fallback, budget admission, and structured token/cost evidence. `tests/test_dev_gateway.py` covers sensitive-local routing, unconfigured flagship skipping, provider failure, and budget stop. This phase still does not execute shell commands, create worktrees, apply patches, commit, deploy, or send customer messages.

## Phases 3-6 + gate upgrade (2026-07-10, this session)

Phase 2 completion + Phases 3-6 + an enterprise invariant gate were implemented
draft-safe and verified on a real Linux Python runtime (the broken project `.venv`
that blocked earlier loops was side-stepped with a hermetic venv).

- **Routing fix (Phase 2 defect):** `route_preview` is now a planner (returns the
  ideal escalation order incl. unconfigured flagships + an honest `effective_provider`),
  and the gateway is the sole enforcer that skips unconfigured/over-budget providers.
  This made the previously-dead "skip unconfigured flagship" gateway path live — the
  Phase-2 pytest that Codex never actually ran was failing; it now passes.
- **Phase 2 ledger:** `DevTaskUsage` table (migration 016) + `app/dev_control/usage.py`
  records per-attempt provider/model/token/cost evidence and rolls actuals onto DevTask.
- **Phase 3:** `app/dev_control/runner.py` (draft-only) + `locks.py` (file-ownership) +
  `app/tasks/dev_worker.py` (INERT unless DEV_ORCHESTRATOR+DEV_WORKER_ENABLED). Produces
  a REVIEW-ONLY patch proposal artifact; `apply_patch` unconditionally refuses.
- **Phase 4:** `app/dev_control/reconcile.py` — DB-is-truth lease reclaim (expired →
  requeue under a retry cap, else fail) + read-only status snapshot + `scripts/dev_control_status.py`.
- **Phase 5:** `app/dev_control/deploy.py` — staged promotion + human production-approval
  gate with a fail-closed token. Code NEVER executes a deploy (manual Hostinger runbook).
- **Phase 6:** `app/dev_control/delivery.py` — completion → delivery evidence + per-customer
  AutomationLog attribution; customer notification is a human-sent DRAFT (ban-safe).
- **Enterprise gate:** `scripts/dev_control_gate.py` enforces 8 hard invariants and is wired
  into `scripts/prod_check.py`. New API lifecycle endpoints on `/api/dev-tasks/*` and an admin
  cockpit at `/app/dev-control`. New gate flags registered in `AUTOMATION_FLAGS`.

Nothing auto-applies a patch, commits, deploys, or messages a customer. All new
behaviour is OFF by default and reachable only after the operator sets the flags.
