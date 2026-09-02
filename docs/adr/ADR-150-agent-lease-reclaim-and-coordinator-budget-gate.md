# ADR-150 — Agent-task lease reclaim + coordinator budget gate

**Date:** 2026-07-31
**Status:** Accepted (code-present, INERT — no flag flipped, not deployed)
**Branch:** `claude/agent-orchestration-integration-80ceed`
**Supersedes / relates:** ADR-148, ADR-149 (external agent orchestrator/runner); ADR-131 (skill registry)

## Context

The user asked to apply https://github.com/andyrewlee/awesome-agent-orchestrators to this
platform. That repository is a **curated link list of ~200 third-party orchestrators**, not a
library — there is nothing importable in it, and every entry orchestrates *coding agents*
(dev-time), which is a different plane from our revenue-bearing 31-agent runtime workforce.

We therefore mined it for *patterns* and checked each against our own code. Full mapping with
file:line evidence: `docs/superpowers/specs/2026-07-31-agent-orchestrator-gap-analysis-design.md`.

Coverage turned out near-total — worktree-isolated parallel agents, merge queue + ownership
conflict, swarm coordination, self-improving loops, scheduled task runners, budget/cost/
permission/checkpoint primitives and an owner assistant all already exist. Two mechanisms did
not.

## Decision

Port two patterns in-repo, additive and INERT by default. Vendor nothing.

### 1. `agent_task_queue.reap_stale_leases()` — terminal close-out of expired leases

`claim_next()` implements an atomic claim with optimistic locking, and `agent_runtime.py:730`
calls the result a lease. But `stale_tasks()` is **observe-only by design** ("Paperclip
philosophy: surface stuck tasks, don't auto-fix") and its only consumers are an Office HQ
snapshot and a badge count. A worker that dies between `claim_next()` and `complete()`/`fail()`
strands its task in `claimed`/`running` **forever** — no agent can ever pick it up, and the
work is silently dropped.

`reap_stale_leases()` marks the expired lease `failed` with
`lease_expired_after_N_attempts` and surfaces it for re-assignment. The transition re-asserts
the same optimistic-lock predicate as `claim_next` (`id` + `checkout_version` + current
status), so a reap cannot clobber a worker that finished legitimately mid-scan. Default is
`dry_run=True`. **No Alembic migration** — `checkout_version` (already bumped on every claim,
`claim_next:150`) is recorded in the reason for diagnostics.

**It is deliberately NOT a requeue**, and this was the design's one real hazard. The first
draft requeued to `pending` under an attempt cap, mirroring
`app/dev_control/reconcile.py:42-60`. That is unsafe *here*, for two reasons that
`reconcile.py` does not share:

- `complete()` (`:197-215`) and `fail()` (`:236-246`) filter on `id` + `status` only —
  **neither guards on `checkout_version`**. So a slow-but-alive worker whose lease was
  requeued keeps running; a second agent claims the same row; and the original's late
  `complete()` silently overwrites the second run. Bumping `checkout_version` on requeue does
  not fix this, precisely because those two writers ignore it.
- These leases wrap genuinely side-effecting work: `agent_runtime._durable_open`
  (`:717-736`) opens one for **every** runtime action, and `team_scheduler.py:309-333` opens
  one for **every** scheduled routine job. A double-run is therefore customer-visible, not
  queue hygiene.

Terminal-fail makes the safety property provable instead of assumed: once reaped the row is
`failed`, so `claim_next` will not offer it and the original worker's late
`complete()`/`fail()` no longer matches the claimed/running filter. Re-assignment stays a
human decision — which is also the more faithful reading of "surface, don't auto-fix".
Regression test: `test_a_reaped_task_cannot_be_reclaimed_or_overwritten`.

"Surface, don't auto-fix" **remains the default**: the reclaim is gated by
`AGENT_TASK_LEASE_REAP` (unset ⇒ INERT) and wired as scheduler job `task_lease_reap` at
hourly `:05`.

### Adding a scheduled job means SIX registries, not one

The first draft registered three and was wrong. Independent review caught `JOB_META`; comparing
against `social_drain`/`sales_autopilot` then caught two more. Locked in by
`test_job_is_registered_in_every_registry` so this cannot silently regress:

| Registry | File | Consequence if missing |
|---|---|---|
| `STAFF_JOBS` | `app/tasks/staff_jobs.py` | Celery `run_staff_job` won't dispatch it; DLQ retry can't parse it |
| `beat_schedule` | `app/worker.py` | **Job never fires in production** — see below |
| `_last_ran` + dispatch + trigger | `app/platform/team_scheduler.py` | In-process scheduler can't run it |
| `JOB_META` | `app/platform/scheduler_config.py` | `set_enabled`/`run_now`/`list_jobs` reject it as `unknown job` → no admin pause button, no manual run, no dashboard row; and `run_due()` recovery filters on it, so a dead `scheduler_loop` is never caught up |
| `EXPECTED_GAP_MIN` | `app/platform/automation_health.py` | No dead-man overdue detection |
| `JOB_INFO` | `app/platform/today_overview.py` | Admin "Aaj" view has no Hinglish label (guarded by `test_job_info_covers_every_scheduled_job`) |

Plus the flag itself in `AUTOMATION_FLAGS`.

**The serious one was `beat_schedule`.** Production runs `celery -A app.worker beat` with
`RUN_IN_PROCESS_SCHEDULER=0` in **both** `app` and `scheduler` (verified by `docker inspect` +
`printenv` on the live host, 2026-07-31). The in-process `scheduler_loop` where the `:05`
trigger lives therefore **never executes in production**. Had this shipped as drafted, the job
would have been dead in prod while every dashboard reported it registered — precisely the fault
`call_kpi_digest` hit ("was in-process-only → dead on Celery topology", audit 2026-07-04). Both
paths are now wired.

Deliberately NOT added to `RUN_DUE_EXCLUDE`: the job is light, idempotent and sends nothing, so
recovery auto-enqueue is desirable.

Correction to an earlier draft of this ADR: `:05` is **not** an unoccupied slot — `ops` already
triggers on the same `now.minute >= 5` condition (`team_scheduler.py:1435`). That is not a
collision; both are awaited sequentially inside one tick, which is the established pattern here
(`reply_triage` and `product_one_health` likewise share `>= 20`). The original claim was simply
wrong and is corrected so nobody relies on it.

### 2. Coordinator consults the budget governor

`agent_budget.check()` enforces a per-agent daily token ceiling with soft-alert/hard-stop
tiers, but was called in exactly one place: `agents/staff.py:1436`. The coordinator's
`fan_out` / `coordinate_agentverse` / `debate` / `council` paths therefore issued one LLM call
per agent per round with **no daily ceiling** — `_llm_rate_ok()` (`coordinator.py:182`) caps
burst-per-minute, not the day's total.

On a free-provider-only stack this is a real risk, not a theoretical one: a known landmine is
*"Groq TPD content-heavy days pe khatam"* (CLAUDE.md §7). A runaway swarm can exhaust the
day's free quota and degrade the **voice path**, which is revenue-bearing.

`_run_agent` now consults `agent_budget.check(agent)` on the **draft/LLM branch only** and
returns `mode="skipped"` instead of calling the LLM when the agent is over budget. The
`execute` tool branch is untouched — it already ran under `staff`'s governance and
double-gating it would change side-effecting behaviour. The check is wrapped in the module's
defensive `try/except` and **fails OPEN**, consistent with §5's fail-open rule for meters.

This is INERT by construction: `check()` short-circuits to `allowed=True` while
`AGENT_BUDGET_ENABLED` is off, which is the default. No flag was flipped.

## Rejected

- **Vendoring any listed tool** (gastown, ralph-*, paperclip, skillfold, …) — free-stack
  mandate, supply-chain risk, none speak our stack.
- **A skill lockfile** (skillfold) — dev-time only, zero runtime or revenue effect. (Not
  because ADR-131 covers it: ADR-131 pins *our own* skills via git, whereas skillfold pins
  *third-party* skill revisions. Different problem, still not one we have.)
- **Another cockpit/kanban/TUI surface** — contradicts the ops-cockpit IA decision; we already
  have `/app/automation`, `/app/office`, `/app/control-center`.
- **Any flag flip, commit, push or deploy** — WS-1 is explicitly "out of scope: flag flips";
  CLAUDE.md §8 requires the user to ask.

## Consequences

- **What actually changes on deploy — the honest version.** An earlier draft of this ADR said
  the release was "a behavioural no-op by construction". That is **wrong** and is retracted.
  Adding `staff-task-lease-reap-hourly` to `beat_schedule` means production dispatches one
  Celery task per hour **regardless of the flag**, and `_run_job`'s `finally` block writes an
  `automation_health.record_run` heartbeat and an `automation_log_service.log_event` row on
  every invocation, *before* the flag is ever consulted. So the deploy adds: one hourly task,
  one heartbeat, one AutomationLog row. What is INERT is the **reaping behaviour** — no row in
  `agent_tasks` is read or written while `AGENT_TASK_LEASE_REAP` is unset.
  This is the established convention for a gated job here (`obsidian_push` is documented the
  same way: "`_run_job` heartbeats daily; job body no-ops unless `OBSIDIAN_SYNC=1`"), and the
  hourly heartbeat is what keeps `EXPECTED_GAP_MIN=180` satisfied so the dead-man does not
  false-page for a deliberately-off job. But "adds an hourly no-op tick and its bookkeeping" is
  the accurate claim, not "changes nothing".
- The coordinator budget gate **is** a true no-op until `AGENT_BUDGET_ENABLED=1`: `check()`
  returns at `agent_budget.py:117` before any file or Redis access.
- Reaping behaviour changes in production only when the owner sets `AGENT_TASK_LEASE_REAP=1`.
- When armed, a dead worker's task is resolved as `failed` with a stated reason instead of
  sitting in `claimed` forever, so the Office HQ stuck-count becomes an actionable work list
  rather than a monotonically growing number. It does **not** auto-retry; re-assignment is
  the owner's call.
- **Precondition before arming `AGENT_BUDGET_ENABLED=1`:** `agent_budget.check()` is sync and
  reaches Redis via `_get_today_usage` → `agent_cost_tracker.agent_today`
  (`agent_budget.py:98-102`). `coordinator.fan_out` runs N agents concurrently, so once the
  flag is live that becomes N blocking calls inside the event loop per swarm. Today it
  short-circuits at `agent_budget.py:117` before touching Redis, so it is free while INERT.
  Arming it should come with the `asyncio.to_thread` + deadline treatment CLAUDE.md §4
  requires for exactly this shape. (`staff.py:1436` calls it the same sync way — the fix
  belongs at the `check()` boundary, for both callers, not in the coordinator alone.)
- No migration, no new routes, no customer mutation, no sends. Compliance gates untouched;
  calling stays HARD OFF.

## Evidence

Measured on base `dfaac8e8` (= `origin/main`). An earlier lane reported "242 passed" against
`ff949ae`, which is **4 commits behind** main; that number was discarded, not carried forward.

- Focused + regression, 17 suites → **275 passed, 9 skipped, 0 failed**
- `scripts/prod_check.py` → `ALL CHECKS PASSED`, 1216 routes, automation 0 gaps
- `scripts/check_secrets.py` → `no secrets detected`
- `ruff check` on every touched file → clean
- Pre-commit (black/isort/ruff/bandit/detect-secrets) → all green
- No route decorators added

**One full-suite failure, proven pre-existing, NOT a regression from this change:**
`tests/test_owner_email_canary.py::test_cross_process_os_lock_blocks_second_claim` fails
identically on a clean `dfaac8e8` worktree with none of this change applied. It spawns a child
process that must re-import the app and signal readiness within 10s; app import alone takes
~9-15s on this Windows machine, so the deadline is marginal here. Baseline evidence was
produced by re-running the same node on a detached clean checkout — not by assuming.
